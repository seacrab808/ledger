"""Native inference/restore correctness probe, never a replacement for the main comparison."""
import json
import os
from pathlib import Path
import time

BASE=Path('/home/miruware/ledger/artifacts/lmcache-runtime')
OUT=BASE/'smoke-03-results';OUT.mkdir(exist_ok=False)
(OUT/'source.py').write_bytes(Path(__file__).read_bytes())
config=json.loads((BASE/'lmcache-native.json').read_text())
trace=json.loads((BASE/'append-42-run.json').read_text())
events=[]
active=None
disks=[]

import torch
torch.set_num_threads(2)
torch.set_num_interop_threads(2)
torch.cuda.set_per_process_memory_fraction(3*2**30/torch.cuda.get_device_properties(0).total_memory,0)
from lmcache.v1.storage_backend.local_disk_backend import LocalDiskBackend
original_init=LocalDiskBackend.__init__
def disk_init(self,*args,**kwargs):
    original_init(self,*args,**kwargs);disks.append(self)
LocalDiskBackend.__init__=disk_init
original_write=LocalDiskBackend.write_file
original_read=LocalDiskBackend.read_file
def write(self, buffer, path):
    start=time.monotonic();value=original_write(self,buffer,path)
    events.append({'request':active,'type':'disk_write','bytes':len(buffer),'path':Path(path).name,'seconds':time.monotonic()-start})
    return value
def read(self,key,buffer,path):
    start=time.monotonic();value=original_read(self,key,buffer,path)
    events.append({'request':active,'type':'disk_read','bytes':len(buffer),'path':Path(path).name,'seconds':time.monotonic()-start})
    return value
LocalDiskBackend.write_file=write
LocalDiskBackend.read_file=read
from vllm.v1.worker.gpu_model_runner import GPUModelRunner
original_execute=GPUModelRunner.execute_model
def execute(self,scheduler_output,*args,**kwargs):
    if active:
        events.append({'request':active,'type':'scheduled_prefill','tokens':scheduler_output.total_num_scheduled_tokens})
    return original_execute(self,scheduler_output,*args,**kwargs)
GPUModelRunner.execute_model=execute
from vllm.model_executor.models.qwen2 import Qwen2ForCausalLM
original_forward=Qwen2ForCausalLM.forward
def forward(self,*args,**kwargs):
    input_ids=args[0] if args else kwargs.get('input_ids')
    if active and input_ids is not None:
        events.append({'request':active,'type':'actual_forward','tokens':input_ids.numel()})
    return original_forward(self,*args,**kwargs)
Qwen2ForCausalLM.forward=forward
from vllm import LLM,SamplingParams

chunk=128
cache=OUT/'cache';cache.mkdir()
settings={'chunk_size':chunk,'local_cpu':False,'max_local_cpu_size':.125,
          'local_disk':str(cache),'max_local_disk_size':.25,'save_unfull_chunk':False,
          'save_decode_cache':False,'use_layerwise':False,'enable_async_loading':False,
          'extra_config':{'disk_io_threads':2},'lmcache_instance_id':'ledger-smoke-01'}
path=OUT/'lmcache.json';path.write_text(json.dumps(settings));os.environ['LMCACHE_CONFIG_FILE']=str(path)
llm=LLM(model=str(BASE/'model'),dtype='float16',max_model_len=1024,
        max_num_seqs=1,max_num_batched_tokens=1024,enforce_eager=True,
        gpu_memory_utilization=3*2**30/torch.cuda.get_device_properties(0).total_memory,
        kv_cache_memory_bytes=128*2**20,enable_prefix_caching=False,
        disable_log_stats=True,seed=42,compilation_config={'mode':0},
        kv_transfer_config={'kv_connector':'LMCacheConnectorV1Dynamic','kv_role':'kv_both',
                            'kv_connector_module_path':'lmcache.integration.vllm.lmcache_connector_v1'})
params=SamplingParams(temperature=0,max_tokens=1,ignore_eos=True,logprobs=20)
cases=[('warm',trace['requests'][12]['prompt_token_ids']),
       ('exact',trace['requests'][12]['prompt_token_ids']),
       ('extended',trace['requests'][16]['prompt_token_ids']),
       ('truncated',trace['requests'][12]['prompt_token_ids'][:200]),
       ('cold-extended',trace['requests'][16]['prompt_token_ids']),
       ('cold-truncated',trace['requests'][12]['prompt_token_ids'][:200])]
rows=[]
for name,tokens in cases:
    if name.startswith('cold-'):
        for disk in disks:
            for key in list(disk.dict):disk.remove(key,force=True)
    active=name;start=time.monotonic()
    output=llm.generate([{'prompt_token_ids':tokens}],params,use_tqdm=False)[0]
    deadline=time.monotonic()+30
    while any(d.disk_worker.put_tasks for d in disks):
        if time.monotonic()>deadline:raise RuntimeError('Async writes did not drain')
        time.sleep(.005)
    result=output.outputs[0]
    row={'name':name,'prompt_tokens':len(tokens),'output_tokens':result.token_ids,
         'seconds':time.monotonic()-start,'logprobs':{str(k):v.logprob for k,v in result.logprobs[0].items()},
         'events':[x for x in events if x['request']==name]}
    rows.append(row);(OUT/'partial-results.json').write_text(json.dumps(rows,indent=2))
active=None
checks=[]
by_name={r['name']:r for r in rows}
for cached,cold in [('exact','warm'),('extended','cold-extended'),('truncated','cold-truncated')]:
    a,b=by_name[cached],by_name[cold]
    same_keys=set(a['logprobs'])==set(b['logprobs'])
    error=max(abs(a['logprobs'][k]-b['logprobs'][k]) for k in a['logprobs'] if k in b['logprobs'])
    correct=a['output_tokens']==b['output_tokens'] and same_keys and error<=.05
    checks.append({'cached':cached,'cold':cold,'greedy_identical':a['output_tokens']==b['output_tokens'],
        'top20_keys_identical':same_keys,'top20_logprob_max_abs_difference':error,'passed':correct})
actual=lambda name:sum(x['tokens'] for x in by_name[name]['events'] if x['type']=='actual_forward')
positive=actual('exact')<actual('warm') and any(x['type']=='disk_read' for x in by_name['exact']['events'])
(OUT/'result.json').write_text(json.dumps({'status':'passed' if positive and all(c['passed'] for c in checks) else 'failed',
    'positive_disk_reuse':positive,'correctness_checks':checks,
    'config':config,'settings':settings,'rows':rows,'torch':torch.__version__},indent=2))
print('Native smoke requests completed.')
