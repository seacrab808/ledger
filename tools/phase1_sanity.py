"""One fresh 16 MiB FEMU correctness run. Not E0; shuts its own VM down afterwards."""
import datetime as dt
import hashlib
import json
import os
import resource
import socket
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

work = Path.home() / 'ledger'
if work.is_symlink() or work.resolve() != work.absolute():
    raise SystemExit('Workspace boundary failed')
sys.path.insert(0, str(work))
from tools.validate_config import audit, device_argument
from tools.qmp_metrics import snapshot, delta_metrics

art = work / 'artifacts'
env = os.environ.copy()
env.update(json.loads((art / 'deps/environment.json').read_text()))
config_file = work / 'configs/femu/blackbox-small.json'
config = json.loads(config_file.read_text())
geometry = audit(config)
assert config['guest'] == {'ram_mib': 2048, 'vcpus': 2}
assert geometry['raw_bytes'] == 4 * 1024**3 and geometry['exposed_bytes'] == 3 * 1024**3
assert config['sanity_plan']['write_bytes'] == 16 * 1024**2
source = work / 'external/FEMU'
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, env=env, text=True).strip()
assert commit == config['femu_commit']
run_id = 'P1-SANITY-001-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
run_dir = art / 'runs' / run_id
run_dir.mkdir(parents=True, exist_ok=False)
qemu = art / 'build-femu/qemu-system-x86_64'
images = art / 'images'
overlay = run_dir / 'boot.qcow2'
subprocess.run([str(qemu.parent / 'qemu-img'), 'create', '-f', 'qcow2', '-F', 'qcow2', '-b',
                str(images / 'phase1.qcow2'), str(overlay)], env=env, check=True, capture_output=True)
with socket.socket() as listener:
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
qmp = run_dir / 'qmp.sock'
cpus = sorted(os.sched_getaffinity(0))[:6]
command = [str(qemu), '-name', 'ledger-phase1,debug-threads=on', '-machine', 'q35,accel=kvm',
           '-cpu', 'host', '-smp', '2', '-m', '2048', '-nodefaults', '-display', 'none',
           '-serial', 'file:' + str(run_dir / 'serial.log'),
           '-drive', 'file=' + str(overlay) + ',if=virtio,format=qcow2,cache=none',
           '-device', device_argument(config),
           '-netdev', 'user,id=net0,hostfwd=tcp:127.0.0.1:' + str(port) + '-:22',
           '-device', 'virtio-net-pci,netdev=net0', '-qmp', 'unix:' + str(qmp) + ',server=on,wait=off']


def limits():
    os.nice(10)
    os.sched_setaffinity(0, cpus)
    resource.setrlimit(resource.RLIMIT_AS, (12 * 1024**3, 12 * 1024**3))


def memory():
    return {line.split(':')[0]: int(line.split()[1]) * 1024
            for line in Path('/proc/meminfo').read_text().splitlines()}


def swap():
    return {line.split()[0]: int(line.split()[1]) for line in Path('/proc/vmstat').read_text().splitlines()
            if line.startswith(('pswpin ', 'pswpout '))}


stop = threading.Event()
samples = []
phase = 'boot'
hz = os.sysconf('SC_CLK_TCK')
started = time.monotonic()
host_before = memory()
swap_before = swap()
start_utc = dt.datetime.now(dt.timezone.utc).isoformat()
log = (run_dir / 'qemu.log').open('w')
vm = subprocess.Popen(command, cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT, preexec_fn=limits)


def monitor():
    previous = None
    while not stop.wait(0.5):
        try:
            status = {}
            for line in Path(f'/proc/{vm.pid}/status').read_text().splitlines():
                if line.startswith(('VmRSS:', 'VmSize:', 'VmLck:')):
                    status[line.split(':')[0]] = int(line.split()[1]) * 1024
            fields = Path(f'/proc/{vm.pid}/stat').read_text().split(')', 1)[1].split()
            ticks = int(fields[11]) + int(fields[12])
            now = time.monotonic()
            cpu = (ticks - previous[1]) / hz / (now - previous[0]) * 100 if previous else None
            samples.append({'elapsed_seconds': now - started, 'phase': phase, **status, 'cpu_percent_one_core': cpu})
            previous = now, ticks
        except (OSError, ValueError):
            return


thread = threading.Thread(target=monitor, daemon=True)
thread.start()
ssh_base = ['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=3',
            '-o', 'StrictHostKeyChecking=accept-new', '-o', 'UserKnownHostsFile=' + str(images / 'known_hosts'),
            '-o', 'ControlMaster=no', '-o', 'ControlPath=none', '-i', str(images / 'femu-guest-key'),
            '-p', str(port), 'femu@127.0.0.1']


def guest(command, script=None, timeout=30):
    result = subprocess.run([*ssh_base, command], input=script, capture_output=True, env=env, timeout=timeout)
    if result.returncode:
        (run_dir / 'guest-error.log').write_bytes(result.stderr)
        raise RuntimeError('Guest command failed; inspect guest-error.log')
    return result.stdout


result = {'status': 'failed', 'run_id': run_id, 'start_utc': start_utc,
          'femu_commit': commit, 'project_commit_at_run': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=work, text=True).strip(),
          'project_dirty_at_run': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=work, text=True).strip()),
          'config_sha256': hashlib.sha256(config_file.read_bytes()).hexdigest(), 'seed': 1,
          'qemu_cpu_affinity': cpus, 'qemu_nice': 10, 'qemu_address_space_limit_bytes': 12 * 1024**3}
try:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if vm.poll() is not None:
            raise RuntimeError('QEMU exited before guest boot; inspect qemu.log')
        try:
            guest('true', timeout=5)
            break
        except (RuntimeError, subprocess.TimeoutExpired):
            time.sleep(2)
    else:
        raise RuntimeError('Guest SSH readiness timeout')
    identity_code = (work / 'tools/guest_identity.py').read_bytes()
    identity = json.loads(guest('python3 -I -', identity_code))
    (run_dir / 'guest-identity.json').write_text(json.dumps(identity, indent=2))
    result['guest'] = identity
    before = snapshot(qmp)
    if any(before['reply']['return']['namespaces'][0]['counters'][k] for k in
           ('host-write-pages', 'nand-write-pages', 'gc-write-pages', 'block-erases')):
        raise RuntimeError('Fresh device counters are not zero')
    (run_dir / 'before.json').write_text(json.dumps(before, indent=2))
    phase = 'idle'
    time.sleep(5)
    phase = 'fio'
    fio_start = dt.datetime.now(dt.timezone.utc).isoformat()
    fio_command = ('sudo -n fio --name=phase1 --filename=' + identity['target'] +
        ' --rw=write --bs=4096 --size=16777216 --offset=0 --ioengine=libaio --direct=1'
        ' --iodepth=1 --numjobs=1 --verify=crc32c --do_verify=1 --verify_fatal=1'
        ' --randseed=1 --output-format=json --output=/home/femu/phase1-fio.json')
    guest(fio_command, timeout=90)
    fio_end = dt.datetime.now(dt.timezone.utc).isoformat()
    fio = json.loads(guest('cat /home/femu/phase1-fio.json'))
    (run_dir / 'fio.json').write_text(json.dumps(fio, indent=2))
    after = snapshot(qmp)
    (run_dir / 'after.json').write_text(json.dumps(after, indent=2))
    delta = delta_metrics(before['reply'], after['reply'])
    job = fio['jobs'][0]
    if job['error'] or job['write']['io_bytes'] != 16777216 or job['read']['io_bytes'] != 16777216:
        raise RuntimeError('fio byte totals/data verification failed')
    expected = {'host-write-pages': 4096, 'nand-write-pages': 4096, 'gc-write-pages': 0, 'block-erases': 0}
    if delta['native_counter_deltas'] != expected:
        raise RuntimeError('Unexpected counter delta')
    result.update({'status': 'passed', 'guest_boot': 'passed', 'namespace_recognition': 'passed',
                   'fio': fio, 'fio_start_utc': fio_start, 'fio_end_utc': fio_end,
                   'fio_command': fio_command, 'native_before': before, 'native_after': after,
                   'metrics': delta, 'geometry_audit': geometry, 'data_verification': 'crc32c-passed'})
    phase = 'after'
    time.sleep(2)
except Exception as exc:
    result['error'] = str(exc)
finally:
    phase = 'shutdown'
    if vm.poll() is None:
        try:
            guest('sudo -n poweroff', timeout=10)
        except Exception:
            pass
        try:
            vm.wait(timeout=20)
        except subprocess.TimeoutExpired:
            vm.terminate()
            try:
                vm.wait(timeout=5)
            except subprocess.TimeoutExpired:
                vm.kill()
                vm.wait()
    stop.set()
    thread.join(timeout=2)
    log.close()
    result['end_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
    result['qemu_exit_code'] = vm.returncode
    result['qemu_stopped'] = vm.poll() is not None
    result['resources'] = {'samples': samples,
        'rss_peak_bytes': max((s.get('VmRSS', 0) for s in samples), default=0),
        'locked_peak_bytes': max((s.get('VmLck', 0) for s in samples), default=0),
        'host_mem_available_before_bytes': host_before['MemAvailable'],
        'host_mem_available_after_bytes': memory()['MemAvailable'],
        'host_swap_page_deltas': {k: swap()[k] - v for k, v in swap_before.items()},
        'cpu_percent_basis': '100% = one logical CPU; samples at 0.5 second intervals',
        'cpu_mean_by_phase': {p: statistics.mean(vals) for p in ['idle', 'fio', 'boot']
             if (vals := [s['cpu_percent_one_core'] for s in samples if s['phase'] == p and s['cpu_percent_one_core'] is not None])}}
    (run_dir / 'result.json').write_text(json.dumps(result, indent=2))
    (art / 'latest-phase1-run.txt').write_text(str(run_dir.relative_to(work)))
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['status'] == 'passed' else 1)
