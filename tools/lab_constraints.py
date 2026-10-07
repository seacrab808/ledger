"""Read-only shared-server constraints. Does not create directories or change access."""
import datetime as dt
import grp
import importlib.util
import json
import os
import resource
import shutil
import stat
import subprocess
from pathlib import Path


def collect():
    device = Path('/dev/kvm')
    info = device.stat() if device.exists() else None
    groups = os.getgroups()
    expected = Path.home() / 'ledger'
    dependencies = ["pkg-config", "libglib2.0-dev", "libfdt-dev", "libpixman-1-dev",
                    "zlib1g-dev", "libdw-dev", "libaio-dev", "libslirp-dev",
                    "libnuma-dev", "ninja-build", "python3-venv", "flex", "bison",
                    "cloud-image-utils"]
    packages = {}
    for package in dependencies:
        result = subprocess.run(['dpkg-query', '-W', '-f=${Status} ${Version}', package],
                                capture_output=True, text=True, timeout=10)
        packages[package] = result.stdout.strip() if result.returncode == 0 else 'not-installed'
    return {
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "kvm_mode": stat.filemode(info.st_mode) if info else None,
        "kvm_group": grp.getgrgid(info.st_gid).gr_name if info else None,
        "current_account_in_device_group": info.st_gid in groups if info else False,
        "kvm_readable": os.access(device, os.R_OK), "kvm_writable": os.access(device, os.W_OK),
        "memlock_limit_bytes": list(resource.getrlimit(resource.RLIMIT_MEMLOCK)),
        "workspace_exists": expected.exists(), "workspace_is_directory": expected.is_dir(),
        "workspace_is_symlink": expected.is_symlink(),
        "workspace_resolves_to_expected_path": expected.resolve() == expected.absolute(),
        "workspace_entries": sorted(p.name for p in expected.iterdir()) if expected.is_dir() else [],
        "workspace_disk_free_bytes": shutil.disk_usage(Path.home()).free,
        "python_venv_importable": importlib.util.find_spec('venv') is not None,
        "python_ensurepip_importable": importlib.util.find_spec('ensurepip') is not None,
        "packages": packages,
        "interpretation": "Read-only inspection; no packages, groups, permissions or host settings changed."
    }


if __name__ == '__main__':
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
