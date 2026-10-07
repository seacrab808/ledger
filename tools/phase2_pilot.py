"""Approved six-run pilot on the existing lab installation; no source/config patch."""
import datetime as dt
import hashlib
import json
import os
import resource
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

work = Path.home() / 'ledger'
if work.is_symlink() or work.resolve() != work.absolute():
    raise SystemExit('Workspace boundary failed')
sys.path.insert(0, str(work))
from tools.validate_config import audit, device_argument
from tools.qmp_metrics import snapshot, delta_metrics, namespace, KEYS


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


art = work / 'artifacts'
env = os.environ.copy()
env.update(json.loads((art / 'deps/environment.json').read_text()))
cfg_path = work / 'configs/femu/blackbox-small.json'
plan_path = work / 'configs/experiments/phase2-pilot.json'
cfg, plan = json.loads(cfg_path.read_text()), json.loads(plan_path.read_text())
geom = audit(cfg)
assert geom['raw_bytes'] == 4 * 1024**3 and geom['exposed_bytes'] == 3 * 1024**3
assert cfg['guest'] == {'ram_mib': 2048, 'vcpus': 2}
assert plan['region_bytes'] == (geom['exposed_bytes'] * 7 // 10 // 4096) * 4096
assert plan['measurement_bytes'] == 2 * plan['region_bytes']
assert len(plan['runs']) == 6 and all(sum(r['pattern'] == p for r in plan['runs']) == 3 for p in ['sequential', 'random'])
source = work / 'external/FEMU'
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, env=env, text=True).strip()
assert commit == cfg['femu_commit']
assert not subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], cwd=source, env=env, text=True).strip()
assert os.access('/dev/kvm', os.R_OK | os.W_OK)
mem_available = next(int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
assert mem_available >= 12 * 1024**3, 'Insufficient host memory headroom'
assert shutil.disk_usage(work).free >= 5 * 1024**3, 'Insufficient disk headroom'
with open('/dev/kvm', 'rb'):
    pass
for proc in Path('/proc').glob('[0-9]*'):
    try:
        if (proc / 'exe').resolve() == art / 'build-femu/qemu-system-x86_64':
            raise SystemExit('An existing project QEMU is active; refusing second VM')
    except (OSError, PermissionError):
        pass

batch_id = 'P2-PILOT-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
batch_dir = art / 'runs' / batch_id
batch_dir.mkdir(parents=True, exist_ok=False)
(batch_dir / 'executed-config.json').write_bytes(cfg_path.read_bytes())
(batch_dir / 'executed-plan.json').write_bytes(plan_path.read_bytes())
qemu = art / 'build-femu/qemu-system-x86_64'
images = art / 'images'
cpus = sorted(os.sched_getaffinity(0))[:6]
batch = {'status': 'running', 'batch_id': batch_id, 'start_utc': utc(), 'femu_commit': commit,
         'project_commit_at_run': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=work, text=True).strip(),
         'project_dirty_at_run': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=work, text=True).strip()),
         'config_sha256': digest(cfg_path), 'plan_sha256': digest(plan_path),
         'runner_sha256': digest(work / 'tools/phase2_pilot.py'), 'qemu_sha256': digest(qemu),
         'config': cfg, 'plan': plan, 'runs': [], 'qemu_cpu_affinity': cpus,
         'limits': {'guest_mib': 2048, 'vcpus': 2, 'nice': 10, 'address_space_gib': 12, 'simultaneous_vms': 1},
         'host': {'kernel': os.uname().release, 'logical_cpus': os.cpu_count(),
                  'mem_available_before_bytes': mem_available,
                  'phase1_host_record': 'records/lab-preflight-current.json',
                  'phase1_guest_record': 'records/phase-01-guest.json'},
         'fill_ratio_logical': plan['region_bytes'] / geom['exposed_bytes'],
         'live_fraction_raw': plan['region_bytes'] / geom['raw_bytes']}
progress = art / 'phase2-progress.json'
batch_start = time.monotonic()


def limits():
    os.nice(10)
    os.sched_setaffinity(0, cpus)
    resource.setrlimit(resource.RLIMIT_AS, (12 * 1024**3, 12 * 1024**3))


def run_one(spec, index):
    run_dir = batch_dir / f'{index:02d}-{spec["pattern"]}-{spec["seed"]}'
    run_dir.mkdir(exist_ok=False)
    overlay = run_dir / 'boot.qcow2'
    subprocess.run([str(qemu.parent / 'qemu-img'), 'create', '-f', 'qcow2', '-F', 'qcow2', '-b',
                    str(images / 'phase1.qcow2'), str(overlay)], env=env, check=True, capture_output=True)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    qmp = run_dir / 'qmp.sock'
    command = [str(qemu), '-name', 'ledger-phase2,debug-threads=on', '-machine', 'q35,accel=kvm',
               '-cpu', 'host', '-smp', '2', '-m', '2048', '-nodefaults', '-display', 'none',
               '-serial', 'file:' + str(run_dir / 'serial.log'),
               '-drive', 'file=' + str(overlay) + ',if=virtio,format=qcow2,cache=none',
               '-device', device_argument(cfg), '-netdev', 'user,id=net0,hostfwd=tcp:127.0.0.1:' + str(port) + '-:22',
               '-device', 'virtio-net-pci,netdev=net0', '-qmp', 'unix:' + str(qmp) + ',server=on,wait=off']
    ssh = ['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=3',
           '-o', 'StrictHostKeyChecking=accept-new', '-o', 'UserKnownHostsFile=' + str(images / 'known_hosts'),
           '-o', 'ControlMaster=no', '-o', 'ControlPath=none', '-o', 'ControlPersist=no',
           '-i', str(images / 'femu-guest-key'), '-p', str(port), 'femu@127.0.0.1']
    log = (run_dir / 'qemu.log').open('w')
    vm = subprocess.Popen(command, cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT, preexec_fn=limits)
    result = {**spec, 'index': index, 'start_utc': utc(), 'status': 'failed',
              'artifact_dir': str(run_dir.relative_to(work)), 'stages': []}

    def guest(cmd, script=None, timeout=30):
        completed = subprocess.run([*ssh, cmd], input=script, capture_output=True, env=env, timeout=timeout)
        if completed.returncode:
            (run_dir / 'guest-error.log').write_bytes(completed.stderr)
            raise RuntimeError('Guest command failed; inspect private guest-error.log')
        return completed.stdout

    def stable_snapshot():
        previous = snapshot(qmp)
        for _ in range(20):
            time.sleep(0.2)
            current = snapshot(qmp)
            if namespace(previous['reply']) == namespace(current['reply']):
                return current
            previous = current
        raise RuntimeError('Native state did not stabilize after completed fio')

    def stage(name, pattern, byte_budget, seed):
        if time.monotonic() - batch_start > plan['max_batch_seconds']:
            raise RuntimeError('Batch time limit reached')
        save(progress, {'batch_id': batch_id, 'completed_runs': len(batch['runs']), 'run': spec,
                        'stage': name, 'updated_utc': utc(), 'vm_pid': vm.pid})
        before = stable_snapshot()
        cmd = ('sudo -n fio --name=phase2 --filename=' + identity['target'] +
               ' --rw=' + ('write' if pattern == 'sequential' else 'randwrite') +
               ' --bs=4096 --size=' + str(plan['region_bytes']) + ' --io_size=' + str(byte_budget) +
               ' --offset=0 --ioengine=libaio --direct=1 --iodepth=1 --numjobs=1'
               ' --norandommap=1 --random_generator=tausworthe64'
               ' --randrepeat=1 --randseed=' + str(seed) +
               ' --end_fsync=1 --output-format=json --output=/home/femu/phase2-fio.json')
        start = utc()
        clock = time.monotonic()
        guest(cmd, timeout=plan['timeout_per_fio_seconds'])
        elapsed = time.monotonic() - clock
        fio = json.loads(guest('cat /home/femu/phase2-fio.json'))
        after = stable_snapshot()
        metrics = delta_metrics(before['reply'], after['reply'])
        job = fio['jobs'][0]
        if job['error'] or job['write']['io_bytes'] != byte_budget or job['read']['io_bytes']:
            raise RuntimeError('fio error or completed byte mismatch')
        if metrics['host_page_covered_bytes'] != byte_budget or metrics['native_counter_deltas']['nand-write-pages'] != byte_budget // 4096:
            raise RuntimeError('NVMe host/NAND user bytes do not equal completed fio bytes')
        item = {'name': name, 'pattern': pattern, 'seed': seed, 'command': cmd, 'start_utc': start,
                'end_utc': utc(), 'wall_seconds': elapsed, 'fio_job_runtime_ms': job['job_runtime'],
                'fio_completed_bytes': byte_budget, 'fio': fio, 'before': before, 'after': after, 'metrics': metrics}
        result['stages'].append(item)
        save(run_dir / (name + '.json'), item)
        save(run_dir / 'result.json', result)
        return item

    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if vm.poll() is not None:
                raise RuntimeError('QEMU exited before guest boot')
            try:
                guest('true', timeout=5)
                break
            except (RuntimeError, subprocess.TimeoutExpired):
                time.sleep(2)
        else:
            raise RuntimeError('Guest boot timeout')
        identity = json.loads(guest('python3 -I -', (work / 'tools/guest_identity.py').read_bytes()))
        result['guest'] = identity
        zero = stable_snapshot()
        if any(namespace(zero['reply'])['counters'][key] for key in KEYS):
            raise RuntimeError('Fresh process counters are not zero')
        result['fresh_zero'] = zero
        stage('fill', 'sequential', plan['region_bytes'], plan['preconditioning']['seed'])
        warm = stage('precondition', 'random', plan['region_bytes'], plan['preconditioning']['seed'])
        counters = warm['metrics']['native_counter_deltas']
        if counters['gc-write-pages'] <= 0 or counters['block-erases'] <= 0:
            raise RuntimeError('GC/erase gate failed; stop without changing config')
        result['gc_gate'] = 'passed'
        baseline = namespace(warm['after']['reply'])
        result['initial_observed_state'] = baseline
        if batch['runs'] and baseline != batch['runs'][0]['initial_observed_state']:
            raise RuntimeError('Observed preconditioning states differ; stop and investigate')
        for window in range(plan['measurement_windows']):
            stage('measurement-' + str(window + 1), spec['pattern'], plan['region_bytes'], spec['seed'] + 1000 * window)
        measurement = [s for s in result['stages'] if s['name'].startswith('measurement-')]
        result['metrics'] = delta_metrics(measurement[0]['before']['reply'], measurement[-1]['after']['reply'])
        result['fio_completed_bytes'] = sum(s['fio_completed_bytes'] for s in measurement)
        result['runtime_seconds'] = sum(s['wall_seconds'] for s in measurement)
        result['fio_job_runtime_ms'] = sum(s['fio_job_runtime_ms'] for s in measurement)
        result['erase_per_gib'] = result['metrics']['block_erases'] / (result['fio_completed_bytes'] / 1024**3)
        assert result['fio_completed_bytes'] == plan['measurement_bytes']
        assert result['metrics']['host_page_covered_bytes'] == plan['measurement_bytes']
        result['status'] = 'passed'
    except Exception as exc:
        result['error'] = str(exc)
    finally:
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
        log.close()
        result['qemu_stopped'] = vm.poll() is not None
        result['qemu_exit_code'] = vm.returncode
        result['end_utc'] = utc()
        save(run_dir / 'result.json', result)
        # Only this fresh overlay is removed, after stopping its owned VM.
        assert overlay.resolve().is_relative_to(batch_dir.resolve())
        overlay.unlink()
        result['boot_overlay_removed_after_shutdown'] = True
    return result


try:
    for index, spec in enumerate(plan['runs'], 1):
        record = run_one(spec, index)
        batch['runs'].append(record)
        save(batch_dir / 'result.json', batch)
        if record['status'] != 'passed':
            raise RuntimeError(record.get('error', 'Run failed'))
    batch['status'] = 'passed'
except Exception as exc:
    batch['status'] = 'failed'
    batch['error'] = str(exc)
finally:
    batch['end_utc'] = utc()
    batch['wall_seconds'] = time.monotonic() - batch_start
    save(batch_dir / 'result.json', batch)
    save(progress, {'status': batch['status'], 'completed_runs': len(batch['runs']), 'batch_id': batch_id,
                    'updated_utc': utc(), 'error': batch.get('error')})
    (art / 'latest-phase2-run.txt').write_text(str(batch_dir.relative_to(work)))
print(json.dumps(batch, indent=2))
raise SystemExit(0 if batch['status'] == 'passed' else 1)
