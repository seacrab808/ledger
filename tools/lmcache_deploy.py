"""Deploy reviewed tools only inside the authorized ledger root; start bounded work."""
import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.remote_probe import ssh_command

def deploy(host, label, script, extra=()):
    paths = [ROOT/'tools/lmcache_resource_guard.py', script,
             ROOT/'external/lmcache-runtime.lock.json', *extra]
    payload = {p.name: base64.b64encode(p.read_bytes()).decode() for p in paths}
    code = '''import os,pathlib,json,base64,subprocess
b=pathlib.Path('/home/miruware/ledger/artifacts/lmcache-runtime')
payload=json.loads(PAYLOAD)
for name,data in payload.items():
 if pathlib.Path(name).name!=name:raise ValueError('bad path')
 target=b/('runtime.lock.json' if name=='lmcache-runtime.lock.json' else name)
 target.write_bytes(base64.b64decode(data))
label=LABEL
if (b/(label+'.status.json')).exists():raise RuntimeError('Existing experiment status; no overwrite')
env=os.environ.copy();env.update(HOME=str(b/'home'),TMPDIR=str(b/'tmp'),XDG_CACHE_HOME=str(b/'cache'),PIP_CACHE_DIR=str(b/'cache/pip'),HF_HOME=str(b/'hf'),CUDA_CACHE_PATH=str(b/'cuda'),TORCH_HOME=str(b/'torch'),TRITON_CACHE_DIR=str(b/'cache/triton'),TORCH_EXTENSIONS_DIR=str(b/'cache/extensions'),OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',MAX_JOBS='2',PYTHONDONTWRITEBYTECODE='1',PIP_DISABLE_PIP_VERSION_CHECK='1',CUDA_VISIBLE_DEVICES='0',VLLM_ENABLE_V1_MULTIPROCESSING='0',VLLM_CACHE_ROOT=str(b/'cache/vllm'),NUMBA_CACHE_DIR=str(b/'cache/numba'),PYTHONHASHSEED='0')
cuda=b/'venv/lib/python3.10/site-packages/nvidia/cu13'
env.update(CUDA_HOME=str(cuda),PATH=str(cuda/'bin')+':'+env['PATH'])
env['VLLM_USE_FLASHINFER_SAMPLER']='0'
env.update(LMCACHE_TRACK_USAGE='false',DO_NOT_TRACK='1',VLLM_NO_USAGE_STATS='1')
with (b/(label+'.guard.log')).open('w') as log:
 p=subprocess.Popen(['python3','-I',str(b/'lmcache_resource_guard.py'),'--label',label,str(b/'venv/bin/python'),str(b/SCRIPT)],env=env,cwd=b,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps({'started':True,'label':label,'guard_pid':p.pid}))
'''.replace('PAYLOAD',repr(json.dumps(payload))).replace('LABEL',repr(label)).replace('SCRIPT',repr(script.name))
    r = subprocess.run([*ssh_command(host,'wsl'),'python3','-I','-'], input=code,
                       text=True,encoding='utf-8',capture_output=True,timeout=40)
    if r.returncode: raise SystemExit('Deployment failed; private SSH output omitted')
    print(r.stdout)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--label',required=True);p.add_argument('--script',type=Path,required=True);p.add_argument('--extra',type=Path,action='append',default=[])
    a=p.parse_args();deploy(a.host,a.label,a.script,a.extra)
