"""Guest-only read-only identification before any raw NVMe I/O."""
import json
import os
import subprocess
from pathlib import Path


def output(command):
    return subprocess.check_output(command, text=True).strip()


devices = sorted(Path('/sys/class/nvme').glob('nvme[0-9]*'))
matches = [p for p in devices if (p / 'serial').read_text().strip() == 'LEDGER-PHASE1']
if len(matches) != 1:
    raise SystemExit('Expected exactly one FEMU serial')
ctrl = matches[0]
model = (ctrl / 'model').read_text().strip()
target = '/dev/' + ctrl.name + 'n1'
size = int(output(['sudo', '-n', 'blockdev', '--getsize64', target]))
tree = json.loads(output(['lsblk', '-J', '-b', '-o', 'NAME,PATH,TYPE,SIZE,MOUNTPOINTS', target]))
block = tree['blockdevices'][0]
if size != 3 * 1024**3 or block.get('children') or any(block.get('mountpoints') or []):
    raise SystemExit('Wrong capacity, partitions or mounts: refusing I/O')
if 'FEMU' not in model or block['type'] != 'disk':
    raise SystemExit('Not a FEMU disk')
if list((Path('/sys/class/block') / Path(target).name / 'holders').iterdir()):
    raise SystemExit('Device has holders')
partitions = output(['sudo', '-n', 'wipefs', '--no-act', '--noheadings', target])
if partitions:
    raise SystemExit('Existing signatures: refusing I/O')
record = {'target': target, 'serial': 'LEDGER-PHASE1', 'model': model, 'capacity_bytes': size,
          'namespace_count': 1, 'partition_and_mount_check': 'passed', 'signature_check': 'empty',
          'nvme_id_ctrl': json.loads(output(['sudo', '-n', 'nvme', 'id-ctrl', '/dev/' + ctrl.name, '-o', 'json'])),
          'nvme_id_ns': json.loads(output(['sudo', '-n', 'nvme', 'id-ns', target, '-o', 'json'])),
          'guest_kernel': output(['uname', '-r']),
          'guest_os': Path('/etc/os-release').read_text(), 'fio_version': output(['fio', '--version']),
          'guest_memory': Path('/proc/meminfo').read_text(), 'logical_cpus': os.cpu_count()}
print(json.dumps(record))
