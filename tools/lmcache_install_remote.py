"""Install exactly resolved wheels in the experiment venv, avoiding retained wheel caches."""
import json
from pathlib import Path
import subprocess
import hashlib
import time
import importlib.metadata
from urllib.parse import urlsplit

BASE = Path('/home/miruware/ledger/artifacts/lmcache-runtime')
lock = json.loads((BASE/'runtime.lock.json').read_text())
python = str(BASE/'venv/bin/python')
packages = sorted(lock['packages'], key=lambda x: x['wheel_bytes'], reverse=True)
# Large wheels individually; small wheels together. No dependency resolution/build.
groups = [[p] for p in packages]
for group in groups:
    item=group[0]
    try:
        if importlib.metadata.version(item['name'])==item['version']:
            continue  # Resume only the exact wheel-pinned installed version.
    except importlib.metadata.PackageNotFoundError:
        pass
    wheel=BASE/'wheels'/Path(urlsplit(item['url']).path).name
    ready=wheel.with_suffix(wheel.suffix+'.ready')
    deadline=time.monotonic()+3600
    while not ready.exists():
        if time.monotonic()>deadline:raise RuntimeError('Verified wheel relay timeout')
        time.sleep(.25)
    digest=hashlib.sha256()
    with wheel.open('rb') as src:
        while data:=src.read(2**20):digest.update(data)
    if digest.hexdigest()!=item['sha256']:raise RuntimeError('Transferred wheel hash mismatch')
    subprocess.run([python, '-m', 'pip', 'install', '--no-deps', '--no-cache-dir',
                    '--only-binary=:all:', str(wheel)], check=True)
    ready.unlink()
    wheel.unlink()
subprocess.run([python, '-m', 'pip', 'check'], check=True)
subprocess.run([python, '-c',
    'import torch,lmcache.cuda_ops,vllm; print(torch.__version__,vllm.__version__); '
    'print(torch.cuda.get_device_name(0))'], check=True)
(BASE/'install-complete.json').write_text(json.dumps({'status':'installed-and-imported',
    'lmcache':'0.5.5','vllm':'0.28.0','torch':'2.13.0'}))
