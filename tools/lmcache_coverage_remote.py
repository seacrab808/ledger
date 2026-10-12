"""Derive consumed prefix coverage from measured forward savings and native keys."""
import json
from pathlib import Path
from lmcache.v1.multiprocess.token_hasher import TokenHasher
from lmcache.v1.distributed.l2_adapters.fs_l2_adapter import _filename_to_object_key

BASE=Path('/home/miruware/ledger/artifacts/lmcache-runtime')
OUT=BASE/'native-01-results'
traces={t['id']:t for t in json.loads((OUT/'input.json').read_text())}
cold={(r['trace'],r['index']):r for r in json.loads((OUT/'baseline.json').read_text())}
result=[]
for c in [64,128,256]:
    hasher=TokenHasher(c,'blake3')
    inventory={}
    for p in (OUT/f'cache-{c}').glob('*.data'):
        key=_filename_to_object_key(p.name)
        inventory[key.cache_salt,key.chunk_hash]={'file':p.name,'bytes':p.stat().st_size,'covered_tokens':0,'reuse_requests':0}
    for r in json.loads((OUT/f'{c}.json').read_text()):
        saved=cold[r['trace'],r['index']]['forward_tokens']-r['forward_tokens']
        tokens=traces[r['trace']]['requests'][r['index']]['prompt_token_ids']
        hashes=hasher.compute_chunk_hashes(tokens)
        for i,h in enumerate(hashes):
            used=max(0,min(c,saved-i*c))
            if used:
                entry=inventory[r['trace'],h]
                entry['covered_tokens']=max(entry['covered_tokens'],used)
                entry['reuse_requests']+=1
    for (trace,h),entry in inventory.items():
        if trace=='warmup':continue
        entry['derived_unique_consumed_bytes']=entry['covered_tokens']*(entry['bytes']//c)
        result.append({'chunk':c,'trace':trace,'hash':h.hex(),**entry})
path=OUT/'coverage.json'
if path.exists():raise RuntimeError('No overwrite of coverage evidence')
path.write_text(json.dumps({'method':'derived union of reused token-prefix ranges, native chunk hashes, measured forward token deltas, observed payload bytes/token; not byte-level model probes','objects':result},indent=2))
