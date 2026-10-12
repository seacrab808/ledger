"""Fetch only small KV records from ledger; never transfer model/cache files."""
import base64
import argparse
import io
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.remote_probe import ssh_command

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True,help='Private authorized SSH alias')
    args=parser.parse_args()
    script='''import base64,io,tarfile
from pathlib import Path
root=Path('/home/miruware/ledger'); folder=root/'results/kv_lifecycle'
buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w:gz') as t:
 for p in folder.rglob('*'):
  if p.is_file() and p.suffix in ('.json','.jsonl'):
   assert p.stat().st_size<5*1024**2
   t.add(p,arcname=str(p.relative_to(root)),recursive=False)
print(base64.b64encode(buf.getvalue()).decode())
'''
    r=subprocess.run([*ssh_command(args.host,'wsl'),'python3','-I','-'],input=script.encode(),capture_output=True,timeout=60)
    if r.returncode: raise RuntimeError('Fetch failed; SSH stderr intentionally private')
    data=base64.b64decode(r.stdout)
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        for m in t.getmembers():
            p=(ROOT/m.name).resolve()
            assert m.isfile() and p.is_relative_to(ROOT/'results/kv_lifecycle')
            contents=t.extractfile(m).read()
            if p.exists(): assert p.read_bytes()==contents, 'Existing record must not be overwritten'
            else: p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(contents)
    print('Fetched small append-only evidence; no model/state files copied.')

if __name__=='__main__': main()
