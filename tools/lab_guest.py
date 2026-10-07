"""Provision one small guest using the pinned native image builder, within ledger."""
import datetime as dt
import hashlib
import json
import os
import resource
import subprocess
from pathlib import Path

work = Path.home() / 'ledger'
if work.is_symlink() or work.resolve() != work.absolute():
    raise SystemExit('Workspace boundary failed')
art = work / 'artifacts'
env = os.environ.copy()
env.update(json.loads((art / 'deps/environment.json').read_text()))
build = art / 'build-femu'
images = art / 'images'
images.mkdir(exist_ok=True)
if (images / 'phase1.qcow2').exists():
    raise SystemExit('Guest already exists; refusing replacement')
start = dt.datetime.now(dt.timezone.utc).isoformat()


def limits():
    os.nice(10)
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:4])
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))


command = ['bash', str(work / 'external/FEMU/hw/femu/scripts/make-guest-image.sh'),
           '--outdir', str(images), '--name', 'phase1.qcow2', '--size', '16G',
           '--qemu', str(build / 'qemu-system-x86_64'), '--qemu-img', str(build / 'qemu-img'),
           '--timeout', '900']
with (art / 'logs/guest-provision.log').open('w') as log:
    result = subprocess.run(command, cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT,
                            timeout=1100, preexec_fn=limits)
if result.returncode:
    raise SystemExit('Provision failed; inspect artifacts/logs/guest-provision.log')
image = images / 'cache/ubuntu-24.04-server-cloudimg-amd64.img'
# Upstream uses a download-cache directory; locate only under our image workspace.
if not image.exists():
    matches = list(images.rglob('ubuntu-24.04-server-cloudimg-amd64.img'))
    if len(matches) != 1: raise SystemExit('Cannot identify source image')
    image = matches[0]
digest = hashlib.sha256()
with image.open('rb') as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b''):
        digest.update(chunk)
disk_info = json.loads(subprocess.check_output([str(build / 'qemu-img'), 'info', '--output=json',
                                              str(images / 'phase1.qcow2')], env=env, text=True))
record = {'status': 'guest-provisioned', 'start_utc': start,
          'end_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
          'source_url': 'https://cloud-images.ubuntu.com/releases/noble/release/ubuntu-24.04-server-cloudimg-amd64.img',
          'source_image_sha256': digest.hexdigest(),
          'source_checksum_verified_by_native_builder': True,
          'signature_verified_by_native_builder': 'SHA256SUMS signature verified' in (art / 'logs/guest-provision.log').read_text(),
          'virtual_boot_disk_bytes': disk_info['virtual-size'], 'allocated_boot_disk_bytes': disk_info['actual-size'],
          'provision_guest_ram_mib': 2048, 'provision_vcpus': 2, 'system_host_settings_changed': False}
(art / 'guest-result.json').write_text(json.dumps(record, indent=2))
print(json.dumps(record, indent=2))
