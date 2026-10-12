"""Existing FS adapter single-key vs list API; real KV bytes, component-only."""
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

BASE=Path('/home/miruware/ledger/artifacts/lmcache-runtime')
OUT=BASE/'batch-02-results'
OUT.mkdir(exist_ok=False)
(OUT/'source.py').write_bytes(Path(__file__).read_bytes())
from lmcache.v1.distributed.l2_adapters import fs_l2_adapter as fs
import aiofiles.threadpool.binary as binary

events=[]
original_write=binary.AsyncBufferedIOBase.write
async def write(self,data):
    result=await original_write(self,data)
    if str(OUT) in str(self.name):events.append({'type':'write','bytes':result})
    return result
binary.AsyncBufferedIOBase.write=write
original_read=fs._async_readinto_full
async def read(f,buf):
    result=await original_read(f,buf);events.append({'type':'read','bytes':result});return result
fs._async_readinto_full=read

def wait_store(adapter,ids):
    deadline=time.monotonic()+30;done={}
    while len(done)<len(ids):
        done.update(adapter.pop_completed_store_tasks())
        if time.monotonic()>deadline:raise RuntimeError('Store completion timeout')
        time.sleep(.001)
    return done

def wait_load(adapter,ids):
    deadline=time.monotonic()+30;done={}
    while len(done)<len(ids):
        for id in ids:
            if id not in done:
                value=adapter.query_load_result(id)
                if value is not None:done[id]=value
        if time.monotonic()>deadline:raise RuntimeError('Load completion timeout')
        time.sleep(.001)
    return done

rows=[]
for chunk in [64,128,256]:
    paths=sorted((BASE/'native-01-results'/('cache-'+str(chunk))).glob('*.data'))[:8]
    if not paths:raise RuntimeError('No measured native KV objects')
    keys=[fs._filename_to_object_key(p.name) for p in paths]
    payload=[p.read_bytes() for p in paths]
    hashes=[hashlib.sha256(p).hexdigest() for p in payload]
    for repeat in range(3):
        modes=['single','batch'] if repeat%2==0 else ['batch','single']
        for mode in modes:
            cache=OUT/f'{chunk}-{repeat}-{mode}'
            adapter=fs.FSL2Adapter(fs.FSL2AdapterConfig(base_path=str(cache),use_odirect=False))
            try:
                objects=[SimpleNamespace(byte_array=bytearray(p)) for p in payload]
                events.clear();start=time.monotonic()
                if mode=='batch':ids=[adapter.submit_store_task(keys,objects)]
                else:ids=[adapter.submit_store_task([k],[o]) for k,o in zip(keys,objects)]
                completed=wait_store(adapter,ids);write_seconds=time.monotonic()-start;write_events=list(events)
                if not all(v.is_successful() for v in completed.values()):raise RuntimeError('Native write failed')
                dest=[SimpleNamespace(byte_array=bytearray(len(p))) for p in payload]
                events.clear();start=time.monotonic()
                if mode=='batch':ids=[adapter.submit_load_task(keys,dest)]
                else:ids=[adapter.submit_load_task([k],[o]) for k,o in zip(keys,dest)]
                loaded=wait_load(adapter,ids);read_seconds=time.monotonic()-start
                passed=all(x.popcount()==(len(keys) if mode=='batch' else 1) for x in loaded.values()) and [hashlib.sha256(x.byte_array).hexdigest() for x in dest]==hashes
                rows.append({'chunk':chunk,'repeat':repeat,'mode':mode,'objects':len(keys),
                             'payload_bytes':sum(map(len,payload)),'write_seconds':write_seconds,
                             'read_seconds':read_seconds,'write_events':write_events,'read_events':list(events),
                             'hash_correctness':passed,'cache_condition':'OS page-cache warm; no global cache drop'})
                (OUT/'result.json').write_text(json.dumps(rows,indent=2))
                if not passed:raise RuntimeError('Native read hash mismatch')
            finally:adapter.close()
