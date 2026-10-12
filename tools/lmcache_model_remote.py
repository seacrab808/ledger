"""Download a small, revision-pinned model only into the bounded project artifacts."""
import hashlib
import json
from pathlib import Path
import urllib.request

BASE=Path('/home/miruware/ledger/artifacts/lmcache-runtime')
REPO='Qwen/Qwen2.5-0.5B-Instruct'
REV='7ae557604adf67be50417f59c2c2f167def9a775'
model=BASE/'model';model.mkdir(exist_ok=True)
allowed={'config.json','generation_config.json','model.safetensors',
         'tokenizer.json','tokenizer_config.json','vocab.json','merges.txt'}
tree=json.load(urllib.request.urlopen(f'https://huggingface.co/api/models/{REPO}/tree/{REV}',timeout=30))
records=[]
for entry in tree:
    name=entry.get('path')
    if name not in allowed:continue
    target=model/name
    if target.exists():raise RuntimeError('Existing model file; no overwrite')
    temp=model/(name+'.part')
    digest=hashlib.sha256();length=0
    url=f'https://huggingface.co/{REPO}/resolve/{REV}/{name}'
    with urllib.request.urlopen(url,timeout=120) as src,temp.open('xb') as out:
        while data:=src.read(2**20):
            out.write(data);digest.update(data);length+=len(data)
    if length!=entry['size']:raise RuntimeError('Model size mismatch')
    if entry.get('lfs') and digest.hexdigest()!=entry['lfs']['oid']:
        raise RuntimeError('Model LFS hash mismatch')
    temp.rename(target)
    records.append({'file':name,'bytes':length,'sha256':digest.hexdigest(),'url':url})
(BASE/'model-provenance.json').write_text(json.dumps({'repo':REPO,'revision':REV,'files':records},indent=2))
print('Downloaded and verified',len(records),'model files.')
