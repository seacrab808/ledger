"""User-space Phase 1 dependencies/source only. Never installs system packages."""
import datetime as dt
import hashlib
import json
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path

work = Path.home() / 'ledger'
if not work.is_dir() or work.is_symlink() or work.resolve() != work.absolute():
    raise SystemExit('Workspace boundary check failed')
os.umask(0o077)
art = work / 'artifacts'
deps = art / 'deps'
prefix = deps / 'root'
debs = deps / 'debs'
logs = art / 'logs'
for folder in [prefix, debs, logs, art / 'tmp', art / 'cache', art / 'home']:
    folder.mkdir(parents=True, exist_ok=True)
env = os.environ.copy()
env.update({'HOME': str(art / 'home'), 'TMPDIR': str(art / 'tmp'),
            'XDG_CACHE_HOME': str(art / 'cache'), 'PIP_CACHE_DIR': str(art / 'cache/pip'),
            'PYTHONNOUSERSITE': '1',
            'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_TERMINAL_PROMPT': '0'})


def run(label, command, cwd=work, timeout=300):
    (logs / 'preparation-progress.txt').write_text(label + '\n')
    with (logs / (label + '.log')).open('w') as output:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        raise SystemExit('Failed at ' + label + '; inspect artifacts/logs/' + label + '.log')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


lock = json.loads((work / 'external/femu.lock.json').read_text())
source = work / lock['checkout']
if not source.exists():
    run('source-clone', ['nice', '-n', '10', 'git', 'clone', '--filter=blob:none', '--no-checkout', lock['repository'], str(source)], timeout=600)
    run('source-checkout', ['git', 'checkout', '--detach', lock['commit']], cwd=source, timeout=600)
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, env=env, text=True).strip()
if head != lock['commit'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=source, env=env, text=True).strip():
    raise SystemExit('Pinned source mismatch or modified source')
packages = ['pkg-config', 'libglib2.0-dev', 'libglib2.0-dev-bin', 'libglib2.0-0',
            'libpcre3-dev', 'libpcre3', 'libpcre16-3', 'libpcre32-3', 'libpcrecpp0v5',
            'libpcre2-dev', 'libpcre2-8-0', 'libpcre2-16-0', 'libpcre2-32-0', 'libpcre2-posix3',
            'libffi-dev', 'libmount-dev', 'libblkid-dev', 'libselinux1-dev', 'libsepol-dev',
            'libslirp-dev', 'libslirp0', 'libfdt-dev', 'libfdt1', 'libpixman-1-dev', 'libpixman-1-0',
            'libnuma-dev', 'libnuma1', 'libaio-dev', 'libaio1', 'libcap-ng-dev', 'libattr1-dev',
            'zlib1g-dev', 'libdw-dev', 'libelf-dev', 'bison', 'flex', 'libfl2', 'libfl-dev',
            'm4', 'genisoimage']
apt = deps / 'apt'
for folder in [apt / 'lists/partial', apt / 'cache/archives/partial', apt / 'log', apt / 'empty']:
    folder.mkdir(parents=True, exist_ok=True)
(apt / 'sources.list').write_text('\n'.join([
    'deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://archive.ubuntu.com/ubuntu jammy main universe',
    'deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://archive.ubuntu.com/ubuntu jammy-updates main universe',
    'deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://security.ubuntu.com/ubuntu jammy-security main universe']) + '\n')
(apt / 'apt.conf').write_text('')
apt_options = ['-o', 'Dir::State=' + str(apt), '-o', 'Dir::State::lists=' + str(apt / 'lists'),
               '-o', 'Dir::State::status=/var/lib/dpkg/status', '-o', 'Dir::Cache=' + str(apt / 'cache'),
               '-o', 'Dir::Log=' + str(apt / 'log'), '-o', 'Dir::Etc::main=' + str(apt / 'apt.conf'),
               '-o', 'Dir::Etc::parts=' + str(apt / 'empty'),
               '-o', 'Dir::Etc::sourcelist=' + str(apt / 'sources.list'),
               '-o', 'Dir::Etc::sourceparts=' + str(apt / 'empty'),
               '-o', 'APT::Sandbox::User=' + pwd.getpwuid(os.getuid()).pw_name, '-o', 'Acquire::Languages=none']
run('local-apt-index', ['apt-get', *apt_options, 'update'], timeout=600)
run('deb-download', ['apt-get', *apt_options, 'download', *packages], cwd=debs, timeout=600)
manifest = []
for package in sorted(debs.glob('*.deb')):
    run('deb-extract-' + package.name.split('_')[0], ['dpkg-deb', '-x', str(package), str(prefix)])
    manifest.append({'file': package.name, 'sha256': sha(package), 'bytes': package.stat().st_size})
# Relocate only extracted dependency .pc metadata; upstream FEMU source stays unchanged.
pc_dirs = [prefix / 'usr/lib/x86_64-linux-gnu/pkgconfig', prefix / 'usr/share/pkgconfig']
for directory in pc_dirs:
    for pc in directory.glob('*.pc'):
        content = pc.read_text()
        content = content.replace('prefix=/usr\n', 'prefix=' + str(prefix / 'usr') + '\n')
        pc.write_text(content)
venv = work / '.venv'
if not (venv / 'bin/python').exists():
    run('python-venv', ['python3', '-m', 'venv', str(venv)])
run('python-build-tools', [str(venv / 'bin/python'), '-m', 'pip', 'install', 'meson==1.8.1', 'ninja==1.11.1.4', 'tomli==2.2.1'], timeout=300)
env.update({'PATH': str(venv / 'bin') + ':' + str(prefix / 'usr/bin') + ':' + env['PATH'],
            'PKG_CONFIG_PATH': ':'.join(map(str, pc_dirs)),
            'LD_LIBRARY_PATH': str(prefix / 'usr/lib/x86_64-linux-gnu'),
            'C_INCLUDE_PATH': str(prefix / 'usr/include'),
            'LIBRARY_PATH': str(prefix / 'usr/lib/x86_64-linux-gnu')})
# Persist an explicit, project-local environment; no shell startup files are edited.
(deps / 'environment.json').write_text(json.dumps({k: env[k] for k in
    ['HOME', 'TMPDIR', 'XDG_CACHE_HOME', 'PIP_CACHE_DIR', 'PATH', 'PKG_CONFIG_PATH',
     'LD_LIBRARY_PATH', 'C_INCLUDE_PATH', 'LIBRARY_PATH', 'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_NOSYSTEM', 'GIT_TERMINAL_PROMPT', 'PYTHONNOUSERSITE']}, indent=2))
glib = subprocess.check_output(['pkg-config', '--modversion', 'glib-2.0'], env=env, text=True).strip()
result = {'captured_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'status': 'dependencies-and-source-ready',
          'femu_commit': head, 'source_tracked_clean': True, 'system_package_install': False,
          'all_files_inside_ledger': True, 'glib_version': glib,
          'python_packages': subprocess.check_output([str(venv / 'bin/python'), '-m', 'pip', 'freeze'], env=env, text=True).splitlines(),
          'deb_packages': manifest, 'build_jobs_planned': 2, 'build': 'not-run'}
(art / 'preparation.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
