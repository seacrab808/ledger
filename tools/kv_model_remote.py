"""Download one pinned small model inside ledger, with checksum verification."""
import hashlib
import json
from pathlib import Path
import urllib.request

p=Path('/home/miruware/ledger/artifacts/kv-screen/models/qwen2.5-0.5b-instruct-q4_k_m.gguf')
p.parent.mkdir(parents=True,exist_ok=True)
if not p.exists():
    urllib.request.urlretrieve('https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/9217f5db79a29953eb74d5343926648285ec7e67/qwen2.5-0.5b-instruct-q4_k_m.gguf',p)
h=hashlib.sha256(p.read_bytes()).hexdigest()
assert h=='74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db'
print(json.dumps({'status':'verified','model_sha256':h,'bytes':p.stat().st_size}))
