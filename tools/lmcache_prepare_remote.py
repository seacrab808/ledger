"""Project-local bounded dependency resolution, without installing inference packages."""
import json
import os
from pathlib import Path
import resource
import subprocess
import venv

BASE = Path('/home/miruware/ledger/artifacts/lmcache-runtime')
BASE.mkdir(exist_ok=True)
for name in ('home', 'tmp', 'cache', 'hf', 'cuda', 'torch'):
    (BASE / name).mkdir(exist_ok=True)
os.environ.update(HOME=str(BASE/'home'), TMPDIR=str(BASE/'tmp'),
                  XDG_CACHE_HOME=str(BASE/'cache'), PIP_CACHE_DIR=str(BASE/'cache/pip'),
                  HF_HOME=str(BASE/'hf'), CUDA_CACHE_PATH=str(BASE/'cuda'),
                  TORCH_HOME=str(BASE/'torch'), TRITON_CACHE_DIR=str(BASE/'cache/triton'),
                  TORCH_EXTENSIONS_DIR=str(BASE/'cache/extensions'),
                  OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', MAX_JOBS='2',
                  PYTHONDONTWRITEBYTECODE='1', PIP_DISABLE_PIP_VERSION_CHECK='1')
os.nice(10)
os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
resource.setrlimit(resource.RLIMIT_AS, (12*2**30, 12*2**30))
if not (BASE/'venv/bin/python').exists():
    venv.EnvBuilder(with_pip=True).create(BASE/'venv')
python = str(BASE/'venv/bin/python')
subprocess.run([python, '-m', 'pip', 'install', '--no-cache-dir', 'pip==25.3'],
               check=True, stdout=subprocess.DEVNULL)
with (BASE/'resolve.log').open('w') as log:
    r = subprocess.run([python, '-m', 'pip', 'install', '--dry-run', '--ignore-installed',
                        '--only-binary=:all:', '--no-cache-dir', '--report', str(BASE/'resolve.json'),
                        'vllm==0.28.0', 'lmcache==0.5.5'], stdout=log, stderr=subprocess.STDOUT)
print(json.dumps({'status': r.returncode, 'report_exists': (BASE/'resolve.json').exists(),
                  'affinity': sorted(os.sched_getaffinity(0))}))
