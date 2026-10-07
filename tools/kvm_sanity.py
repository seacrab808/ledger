"""Read-only account checks and bounded KVM open/API/empty-VM check."""
import datetime as dt
import fcntl
import grp
import json
import os
import subprocess


def collect():
    outputs = {}
    for name, command in [('id', ['id']), ('groups', ['groups']),
                          ('kvm_device', ['ls', '-l', '/dev/kvm'])]:
        run = subprocess.run(command, capture_output=True, text=True, timeout=10)
        outputs[name] = {'exit_code': run.returncode, 'stdout': run.stdout.strip()}
    groups = [grp.getgrgid(gid).gr_name for gid in os.getgroups()]
    checks = {'captured_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'fresh_ssh_connection_required': True, 'kvm_group_in_execution_session': 'kvm' in groups,
              'kvm_readable': os.access('/dev/kvm', os.R_OK),
              'kvm_writable': os.access('/dev/kvm', os.W_OK),
              'kvm_open_success': False, 'kvm_api_version': None,
              'empty_vm_create_success': False}
    try:
        fd = os.open('/dev/kvm', os.O_RDWR | os.O_CLOEXEC)
        try:
            checks['kvm_open_success'] = True
            checks['kvm_api_version'] = fcntl.ioctl(fd, 0xAE00, 0)
            vmfd = fcntl.ioctl(fd, 0xAE01, 0)
            os.close(vmfd)
            checks['empty_vm_create_success'] = True
        finally:
            os.close(fd)
    except OSError as exc:
        checks['error'] = str(exc)
    checks['passed'] = all(checks[k] for k in ('kvm_group_in_execution_session', 'kvm_readable',
                                               'kvm_writable', 'kvm_open_success', 'empty_vm_create_success')) and checks['kvm_api_version'] == 12
    return {'public_checks': checks, 'private_command_output': outputs}


if __name__ == '__main__':
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
