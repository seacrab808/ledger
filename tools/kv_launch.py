"""Upload reviewed inputs and launch a single bounded sequential screening batch."""
import base64
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.remote_probe import ssh_command

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True,help='Private authorized SSH alias; not stored in public records')
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    resume=args.resume
    files={n:base64.b64encode((ROOT/n).read_bytes()).decode() for n in
           ['tools/kv_screen.py','configs/experiments/kv-screen.json']}
    provenance={'local_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                'local_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT))}
    controller='''import datetime as dt,json,os,platform,resource,subprocess,sys,time
from pathlib import Path
root=Path('/home/miruware/ledger'); base=root/'artifacts/kv-screen'
env=dict(os.environ,HOME=str(base/'home'),TMPDIR=str(base/'tmp'),XDG_CACHE_HOME=str(base/'cache'),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1')
status=base/'batch-status.json'
def update(**data):
 status.write_text(json.dumps(dict(timestamp_utc=dt.datetime.now(dt.timezone.utc).isoformat(),**data),indent=2))
def limits():
 os.nice(10); os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2])
 resource.setrlimit(resource.RLIMIT_AS,(12*1024**3,12*1024**3))
queue=[('smoke',42,'append')]+[('screen',seed,pattern) for seed in (42,43,44) for pattern in ('append','retry','edit','session_end')]
done=[]
for mode,seed,pattern in queue:
 name='smoke' if mode=='smoke' else f'{pattern}-{seed}'
 record=root/'results/kv_lifecycle'/name/'run.json'
 if record.exists():
  assert json.loads(record.read_text())['status']=='passed'
  done.append(name); continue
 update(status='running',current=name,completed=done)
 with open(base/f'{name}.log','xb') as log:
  p=subprocess.Popen([str(base/'venv/bin/python'),str(root/'tools/kv_screen.py'),'--root',str(root),'--mode',mode,'--seed',str(seed),'--pattern',pattern],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,preexec_fn=limits)
  deadline=time.monotonic()+1200
  while p.poll() is None:
   if time.monotonic()>deadline:
    p.terminate(); p.wait(timeout=30); update(status='failed',current=name,completed=done,reason='20-minute run ceiling'); sys.exit(1)
   # Bounded total disk budget over this experiment's owned artifacts/results.
   size=0
   try:
    for folder in (base,root/'results/kv_lifecycle'):
     for f in folder.rglob('*'):
      if f.is_file(): size+=f.stat().st_size
   except FileNotFoundError:
    pass # owned cache cleanup can race read-only resource sampling
   if size>10*1024**3:
    p.terminate(); p.wait(timeout=30); update(status='failed',current=name,completed=done,reason='10 GiB disk budget'); sys.exit(1)
   time.sleep(2)
  if p.returncode:
   update(status='failed',current=name,completed=done,exit_code=p.returncode); sys.exit(p.returncode)
 done.append(name)
update(status='passed',completed=done)
'''
    script=f'''import base64,json,subprocess
from pathlib import Path
root=Path('/home/miruware/ledger').resolve(); base=root/'artifacts/kv-screen'
if (base/'batch-started.json').exists():
 if not {resume!r}: raise SystemExit('Batch exists; use explicit resume after inspecting owned controller')
 old=json.loads((base/'batch-started.json').read_text())
 proc=Path('/proc')/str(old['pid'])
 if proc.exists(): assert (proc/'stat').read_text().split()[2]=='Z', 'Controller still active'
 for n in ('batch-started.json','batch-status.json','controller.log'):
  p=base/n
  if p.exists(): p.rename(base/('du-race-'+n))
for name,data in {files!r}.items():
 p=root/name; assert p.resolve().is_relative_to(root); p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(base64.b64decode(data))
controller=base/'controller.py'; controller.write_text({controller!r})
prov={provenance!r}
prov['remote_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
prov['remote_dirty']=bool(subprocess.check_output(['git','status','--porcelain'],cwd=root))
prov['dependencies']=subprocess.check_output([str(base/'venv/bin/python'),'-m','pip','freeze'],text=True).splitlines()
prov['host_kernel']=subprocess.check_output(['uname','-r'],text=True).strip()
prov['host_cpu']=next(x.split(':',1)[1].strip() for x in Path('/proc/cpuinfo').read_text().splitlines() if x.startswith('model name'))
prov['host_mem_total_kib']=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemTotal:')))
out=root/'results/kv_lifecycle'; out.mkdir(parents=True,exist_ok=True)
provenance_file=out/('resume-provenance.json' if {resume!r} else 'batch-provenance.json')
assert not provenance_file.exists() or not {resume!r}
provenance_file.write_text(json.dumps(prov,indent=2))
log=open(base/'controller.log','xb')
p=subprocess.Popen(['python3','-I',str(controller)],cwd=base,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(base/'batch-started.json').write_text(json.dumps({{'pid':p.pid}}))
print(json.dumps({{'status':'started','pid':p.pid}}))
'''
    r=subprocess.run([*ssh_command(args.host,'wsl'),'python3','-I','-'],input=script.encode(),capture_output=True,timeout=60)
    (ROOT/'results/private/kv-launch-output.json').write_bytes(r.stdout)
    if r.returncode:
        (ROOT/'results/private/kv-launch-error.log').write_bytes(r.stderr)
    print(r.stdout.decode()); raise SystemExit(r.returncode)

if __name__=='__main__': main()
