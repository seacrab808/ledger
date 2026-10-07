"""Bounded, low-priority FEMU build using dependencies inside ledger only."""
import datetime as dt
import hashlib
import json
import os
import resource
import subprocess
import time
from pathlib import Path

work = Path.home() / 'ledger'
if work.is_symlink() or work.resolve() != work.absolute():
    raise SystemExit('Workspace boundary failed')
art = work / 'artifacts'
env = os.environ.copy()
env.update(json.loads((art / 'deps/environment.json').read_text()))
source = work / 'external/FEMU'
lock = json.loads((work / 'external/femu.lock.json').read_text())
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, env=env, text=True).strip()
if head != lock['commit']:
    raise SystemExit('Source pin changed')
build = art / 'build-femu'
build.mkdir(exist_ok=True)
logs = art / 'logs'
cpus = sorted(os.sched_getaffinity(0))[:2]


def limits():
    os.nice(10)
    os.sched_setaffinity(0, cpus)
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))


def run(label, command, timeout=1800):
    (logs / 'build-progress.txt').write_text(label)
    with (logs / (label + '.log')).open('w') as output:
        result = subprocess.run(command, cwd=build, env=env, stdout=output, stderr=subprocess.STDOUT,
                                timeout=timeout, preexec_fn=limits)
    if result.returncode:
        raise SystemExit('Failed at ' + label + '; inspect artifacts/logs/' + label + '.log')


start = dt.datetime.now(dt.timezone.utc).isoformat()
clock = time.monotonic()
configure = [str(source / 'configure'), '--enable-kvm', '--target-list=x86_64-softmmu',
             '--enable-slirp', '--disable-libnfs', '--disable-libiscsi', '--disable-curl',
             '--disable-docs', '--disable-gtk', '--disable-sdl', '--disable-vnc',
             '--python=' + str(work / '.venv/bin/python')]
run('configure', configure, timeout=600)
run('compile', ['ninja', '-j', '2', 'qemu-system-x86_64', 'qemu-img'], timeout=1800)
run('native-unit-tests', [str(build / 'pyvenv/bin/meson'), 'test', 'test-femu-nand-media',
                         'test-femu-pqueue', '--num-processes', '2', '--print-errorlogs'])
run('device-help', [str(build / 'qemu-system-x86_64'), '-device', 'help'], timeout=30)
run('femu-properties', [str(build / 'qemu-system-x86_64'), '-device', 'femu,help'], timeout=30)
if 'femu' not in (logs / 'device-help.log').read_text():
    raise SystemExit('FEMU registration missing')
dirty = subprocess.check_output(['git', 'diff', '--stat'], cwd=source, env=env, text=True).strip()
if dirty:
    raise SystemExit('Tracked FEMU source was modified')
result = {'status': 'build-passed', 'start_utc': start, 'end_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
          'runtime_seconds': time.monotonic() - clock, 'femu_commit': head,
          'source_tracked_clean': True, 'build_jobs': 2, 'build_nice': 10, 'build_cpu_affinity': cpus,
          'compiler': subprocess.check_output(['gcc', '-dumpfullversion'], text=True).strip(),
          'version': subprocess.check_output([str(build / 'qemu-system-x86_64'), '--version'], env=env, text=True).splitlines()[0],
          'native_unit_tests': 'passed', 'native_test_log': 'artifacts/build-femu/meson-logs/testlog.txt',
          'configure_options': [option.replace(str(work), '$LEDGER') for option in configure[1:]],
          'qemu_sha256': hashlib.sha256((build / 'qemu-system-x86_64').read_bytes()).hexdigest(),
          'qemu_img_sha256': hashlib.sha256((build / 'qemu-img').read_bytes()).hexdigest(),
          'system_packages_modified': False}
(art / 'build-result.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
