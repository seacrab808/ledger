"""Relay revision-pinned model files through the same authorized project-only transport."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.lmcache_relay import copy, remote

def run(host):
    repo='Qwen/Qwen2.5-0.5B-Instruct';revision='7ae557604adf67be50417f59c2c2f167def9a775'
    root=ROOT/'artifacts/lmcache-model';root.mkdir(exist_ok=True)
    target='/home/miruware/ledger/artifacts/lmcache-runtime/model'
    remote(host,f'import pathlib;pathlib.Path({target!r}).mkdir(exist_ok=True)')
    allowed={'config.json','generation_config.json','model.safetensors','tokenizer.json',
             'tokenizer_config.json','vocab.json','merges.txt'}
    tree=json.load(urllib.request.urlopen(f'https://huggingface.co/api/models/{repo}/tree/{revision}'))
    provenance=[]
    for item in tree:
        name=item.get('path')
        if name not in allowed:continue
        path=root/name;url=f'https://huggingface.co/{repo}/resolve/{revision}/{name}'
        digest=hashlib.sha256();length=0
        if path.exists():raise RuntimeError('Existing local model relay file; preserve it')
        with urllib.request.urlopen(url,timeout=120) as src,path.open('xb') as out:
            while data:=src.read(2**20):out.write(data);digest.update(data);length+=len(data)
        if length!=item['size'] or (item.get('lfs') and digest.hexdigest()!=item['lfs']['oid']):
            raise RuntimeError('Local model checksum/size mismatch')
        dst=target+'/'+name
        if remote(host,f'import pathlib;print(pathlib.Path({dst!r}).exists())')=='True':
            raise RuntimeError('Existing remote model file; no overwrite')
        copy(host,path,dst)
        actual=remote(host,f"import hashlib,pathlib;h=hashlib.sha256();p=pathlib.Path({dst!r});f=p.open('rb');\nwhile data:=f.read(2**20):h.update(data)\nprint(h.hexdigest())")
        if actual!=digest.hexdigest():raise RuntimeError('Remote model checksum mismatch')
        provenance.append({'file':name,'bytes':length,'sha256':actual,'url':url})
        print('Verified model',name,flush=True)
    record={'repo':repo,'revision':revision,'files':provenance}
    path=ROOT/'external/lmcache-model.lock.json';path.write_text(json.dumps(record,indent=2)+'\n')
    remote(host,f"import pathlib;pathlib.Path('/home/miruware/ledger/artifacts/lmcache-runtime/model-provenance.json').write_text({json.dumps(record)!r})")

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',required=True);a=p.parse_args();run(a.host)
