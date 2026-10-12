"""Transfer remaining small verified wheels in one bounded spool archive."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile
from urllib.parse import urlsplit
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.lmcache_relay import remote, copy

def run(host):
    base=ROOT/'artifacts/lmcache-relay'
    installed=json.loads((base/'installed.json').read_text())
    canonical=lambda x:re.sub('[-_.]+','-',x).lower()
    installed={canonical(k):v for k,v in installed.items()}
    lock=json.loads((ROOT/'external/lmcache-runtime.lock.json').read_text())
    todo=[x for x in lock['packages'] if installed.get(canonical(x['name']))!=x['version']]
    if any(x['wheel_bytes']>5*2**20 for x in todo):raise RuntimeError('Use individual relay for large files')
    def fetch(item):
        p=base/Path(urlsplit(item['url']).path).name
        if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:
            p.rename(p.with_suffix('.partial-backup'))
        if not p.exists():
            with urllib.request.urlopen(item['url'],timeout=60) as src,p.open('xb') as out:
                while data:=src.read(2**20):out.write(data)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:
            raise RuntimeError('Small wheel hash mismatch')
        return p
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        paths=list(pool.map(fetch,todo))
    archive=base/'remaining-wheels.tar'
    with tarfile.open(archive,'w') as tar:
        for p in paths:tar.add(p,arcname=p.name)
    target='/home/miruware/ledger/artifacts/lmcache-runtime/wheels/remaining-wheels.tar'
    copy(host,archive,target)
    code=f'''import pathlib,tarfile,json,hashlib
b=pathlib.Path('/home/miruware/ledger/artifacts/lmcache-runtime')
allowed={{pathlib.Path(x['url']).name:x['sha256'] for x in json.loads((b/'runtime.lock.json').read_text())['packages']}}
p=pathlib.Path({target!r})
with tarfile.open(p) as tar:
 for item in tar:
  if not item.isfile() or item.name!=pathlib.Path(item.name).name or item.name not in allowed:raise RuntimeError('Invalid spool member')
  data=tar.extractfile(item).read()
  if hashlib.sha256(data).hexdigest()!=allowed[item.name]:raise RuntimeError('Spool hash mismatch')
  dest=b/'wheels'/item.name
  if not dest.exists():dest.write_bytes(data)
  dest.with_suffix(dest.suffix+'.ready').write_text('verified spool')
p.unlink()
print('Verified small-wheel spool')
'''
    print(remote(host,code),'files',len(paths),'MiB',sum(p.stat().st_size for p in paths)/2**20)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',required=True);a=p.parse_args();run(a.host)
