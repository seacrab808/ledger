"""Project-local preparation on the authorized shared host; bounded owned child."""
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import urllib.request
import venv

ROOT = Path('/home/miruware/ledger').resolve()
BASE = ROOT / 'artifacts/kv-screen'
BASE.mkdir(parents=True, exist_ok=True)
for d in ('home', 'tmp', 'cache', 'models'):
    (BASE / d).mkdir(exist_ok=True)
env = dict(os.environ, HOME=str(BASE/'home'), TMPDIR=str(BASE/'tmp'),
           XDG_CACHE_HOME=str(BASE/'cache'), PIP_CACHE_DIR=str(BASE/'cache/pip'),
           CMAKE_BUILD_PARALLEL_LEVEL='2', MAKEFLAGS='-j2',
           CMAKE_ARGS='-DGGML_CUDA=OFF -DGGML_OPENMP=OFF -DGGML_BLAS=OFF',
           OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='1')
os.environ.update(env) # venv/ensurepip bootstrap must also inherit project-local TMPDIR/HOME

def limits():
    os.nice(10)
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    resource.setrlimit(resource.RLIMIT_AS, (12*1024**3, 12*1024**3))

python = BASE/'venv/bin/python'
if not python.exists():
    venv.EnvBuilder(with_pip=True).create(BASE/'venv')
archive = BASE/'llama_cpp_python-0.3.36.tar.gz'
if not archive.exists():
    urllib.request.urlretrieve('https://files.pythonhosted.org/packages/ec/e9/e7de2b0463ea3ffbf0ede6cb21b58c1258a8f6521aae45ca773a59fe7cf3/llama_cpp_python-0.3.36.tar.gz', archive)
assert hashlib.sha256(archive.read_bytes()).hexdigest() == '832db0699007f1be95a7e41ef12e88926b02ba836461e36a36372db2760c1a2e'
marker = BASE/'build-started.json'
if marker.exists():
    raise SystemExit('Preparation already launched; inspect existing log, do not duplicate.')
log = open(BASE/'build.log', 'xb')
p = subprocess.Popen([str(python), '-m', 'pip', 'install', str(archive)],
                     cwd=BASE, env=env, stdout=log, stderr=subprocess.STDOUT,
                     start_new_session=True, preexec_fn=limits)
marker.write_text(json.dumps({'pid':p.pid, 'status':'started', 'jobs':2, 'nice':10}))
print(json.dumps({'status':'build-started', 'pid':p.pid}))
