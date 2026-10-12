"""Collect small native evidence through an existing private SSH alias."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.remote_probe import ssh_command

def collect(host,label,directory):
    code='''import pathlib,json,hashlib,platform,subprocess
b=pathlib.Path('/home/miruware/ledger/artifacts/lmcache-runtime')
o=b/DIRECTORY
result={'status':json.loads((b/(LABEL+'.status.json')).read_text()),'files':{},'cache_inventory':{}}
for p in o.iterdir():
 if p.is_file() and p.suffix in ('.json','.jsonl','.log','.py'):
  data=p.read_bytes()
  if len(data)>8*2**20:raise RuntimeError('Unexpectedly large text artifact')
  result['files'][p.name]={'text':data.decode(),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
for p in o.glob('cache*'):
 if p.is_dir():
  result['cache_inventory'][p.name]={'directory_allocated_bytes':p.stat().st_blocks*512,'files':[{'name':q.name,'bytes':q.stat().st_size,'allocated_bytes':q.stat().st_blocks*512,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in p.glob('*.data')]}
result['host']={'kernel':platform.release(),'machine':platform.machine(),'python':platform.python_version()}
print(json.dumps(result))
'''.replace('DIRECTORY',repr(directory)).replace('LABEL',repr(label))
    run=subprocess.run([*ssh_command(host,'wsl'),'python3','-I','-'],input=code,
                       text=True,encoding='utf-8',capture_output=True,timeout=90)
    if run.returncode:raise SystemExit('Collection failed; private SSH diagnostics omitted')
    value=json.loads(run.stdout)
    output=ROOT/'results/lmcache_native'/label
    output.mkdir(exist_ok=False)
    for name,artifact in value['files'].items():
        if Path(name).name!=name:raise ValueError('Invalid file name')
        (output/name).write_text(artifact.pop('text'),encoding='utf-8',newline='')
    (output/'manifest.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
    print(json.dumps({'collected':label,'status':value['status']['status'],'text_files':len(value['files'])}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--label',required=True);p.add_argument('--directory',required=True)
    a=p.parse_args();collect(a.host,a.label,a.directory)
