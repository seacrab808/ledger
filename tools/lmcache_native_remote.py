"""Paired native MP disk-backed trace comparison with observation-only hooks."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

BASE=Path('/home/miruware/ledger/artifacts/lmcache-runtime')
OUT=BASE/'native-01-results'

def server(chunk):
    import aiofiles.threadpool.binary as binary
    import lmcache.v1.distributed.l2_adapters.fs_l2_adapter as fs
    event_path=OUT/('io-'+chunk+'.jsonl')
    def emit(event):
        event['time']=time.time()
        try: event['request']=json.loads((OUT/'active.json').read_text())
        except (OSError,ValueError): event['request']=None
        with event_path.open('a') as f: f.write(json.dumps(event)+'\n')
    original_write=binary.AsyncBufferedIOBase.write
    async def write(self,data):
        start=time.monotonic(); result=await original_write(self,data)
        if str(OUT/('cache-'+chunk)) in str(self.name):
            emit({'type':'write','file':Path(self.name).name,'bytes':result,'seconds':time.monotonic()-start})
        return result
    binary.AsyncBufferedIOBase.write=write
    original_read=fs._async_readinto_full
    async def read(f,buf):
        start=time.monotonic(); result=await original_read(f,buf)
        emit({'type':'read','file':Path(f.name).name,'bytes':result,'seconds':time.monotonic()-start})
        return result
    fs._async_readinto_full=read
    from lmcache.cli.main import main
    sys.argv=json.loads((OUT/('server-'+chunk+'.json')).read_text())['command']
    main()

def inference(arm):
    import torch
    torch.set_num_threads(2);torch.set_num_interop_threads(2)
    torch.cuda.set_per_process_memory_fraction(3*2**30/torch.cuda.get_device_properties(0).total_memory)
    from vllm.model_executor.models.qwen2 import Qwen2ForCausalLM
    counts=[]; original=Qwen2ForCausalLM.forward
    def forward(self,*args,**kwargs):
        ids=args[0] if args else kwargs.get('input_ids')
        if ids is not None:counts.append(ids.numel())
        return original(self,*args,**kwargs)
    Qwen2ForCausalLM.forward=forward
    from vllm import LLM,SamplingParams
    options=dict(model=str(BASE/'model'),dtype='float16',max_model_len=1024,
                 max_num_seqs=1,max_num_batched_tokens=1024,enforce_eager=True,
                 kv_cache_memory_bytes=128*2**20,enable_prefix_caching=False,
                 gpu_memory_utilization=3*2**30/torch.cuda.get_device_properties(0).total_memory,
                 disable_log_stats=True,seed=42,compilation_config={'mode':0})
    if arm!='baseline':
        cfg=json.loads((OUT/('server-'+arm+'.json')).read_text())
        options['kv_transfer_config']={'kv_connector':'LMCacheMPConnector','kv_role':'kv_both',
            'kv_connector_module_path':'lmcache.integration.vllm.lmcache_mp_connector',
            'kv_connector_extra_config':{'lmcache.mp.host':'tcp://127.0.0.1','lmcache.mp.port':cfg['port'],
                                        'lmcache.mp.isolated_ipc':True}}
    llm=LLM(**options)
    params=SamplingParams(temperature=0,max_tokens=1,ignore_eos=True,logprobs=20)
    inputs=json.loads((BASE/'lmcache-inputs.json').read_text())
    # Prime model/kernel paths with a separate salt, excluded from measurements.
    llm.generate([{'prompt_token_ids':[1,2,3,4],'cache_salt':'warmup'}],params,use_tqdm=False)
    rows=[]
    for trace in inputs:
        for index,request in enumerate(trace['requests']):
            tag={'trace':trace['id'],'index':index,'arm':arm}
            temp=OUT/'active.tmp';temp.write_text(json.dumps(tag));temp.replace(OUT/'active.json')
            counts.clear(); start=time.monotonic()
            tokens=request['prompt_token_ids']
            result=llm.generate([{'prompt_token_ids':tokens,'cache_salt':trace['id']}],params,use_tqdm=False)[0].outputs[0]
            rows.append({**tag,'prompt_tokens':len(tokens),'forward_tokens':sum(counts),
                         'seconds':time.monotonic()-start,'output_tokens':result.token_ids,
                         'logprobs':{str(k):v.logprob for k,v in result.logprobs[0].items()}})
            (OUT/(arm+'.json')).write_text(json.dumps(rows,indent=2))
            time.sleep(.3)  # fixed async persistence gap outside timed inference
    (OUT/(arm+'.done')).write_text('complete')
    os._exit(0)

def stop(p):
    if p and p.poll() is None:
        p.terminate()
        try:p.wait(timeout=10)
        except subprocess.TimeoutExpired:p.kill();p.wait()

def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

def parent():
    OUT.mkdir(exist_ok=False);(OUT/'source.py').write_bytes(Path(__file__).read_bytes())
    (OUT/'input.json').write_bytes((BASE/'lmcache-inputs.json').read_bytes())
    children=[]
    try:
        for arm in ['baseline','64','128','256']:
            srv=None
            if arm!='baseline':
                request_port,http=port(),port();cache=OUT/('cache-'+arm);cache.mkdir()
                command=['lmcache','server','--host','127.0.0.1','--port',str(request_port),
                         '--http-host','127.0.0.1','--http-port',str(http),'--chunk-size',arm,
                         '--max-workers','1','--isolated-ipc','--l1-size-gb','0.125','--no-l1-use-lazy',
                         '--l2-adapter',json.dumps({'type':'fs','base_path':str(cache),'use_odirect':False}),
                         '--l2-store-policy','skip_l1','--eviction-policy','LRU','--disable-observability']
                (OUT/('server-'+arm+'.json')).write_text(json.dumps({'port':request_port,'command':command}))
                log=(OUT/('server-'+arm+'.log')).open('w')
                srv=subprocess.Popen([sys.executable,__file__,'server',arm],stdout=log,stderr=subprocess.STDOUT)
                children.append(srv);deadline=time.monotonic()+90
                while True:
                    if srv.poll() is not None:raise RuntimeError('Native server failed '+arm)
                    try:
                        with socket.create_connection(('127.0.0.1',http),timeout=1):break
                    except OSError:
                        if time.monotonic()>deadline:raise RuntimeError('Server startup timeout')
                        time.sleep(1)
            with (OUT/(arm+'.log')).open('w') as log:
                p=subprocess.Popen([sys.executable,__file__,'inference',arm],stdout=log,stderr=subprocess.STDOUT)
                children.append(p)
                try:
                    if p.wait(timeout=300):raise RuntimeError('Inference failed '+arm)
                finally:stop(p)
            stop(srv)
        baseline=json.loads((OUT/'baseline.json').read_text());checks=[]
        for arm in ['64','128','256']:
            rows=json.loads((OUT/(arm+'.json')).read_text())
            for cold,hot in zip(baseline,rows,strict=True):
                common=cold['logprobs'].keys()&hot['logprobs'].keys()
                error=max(abs(cold['logprobs'][k]-hot['logprobs'][k]) for k in common)
                checks.append({'arm':arm,'trace':hot['trace'],'index':hot['index'],
                               'greedy_identical':cold['output_tokens']==hot['output_tokens'],
                               'keys_identical':cold['logprobs'].keys()==hot['logprobs'].keys(),
                               'max_abs_logprob_difference':error,
                               'passed':cold['output_tokens']==hot['output_tokens'] and cold['logprobs'].keys()==hot['logprobs'].keys() and error<=.05})
        (OUT/'correctness.json').write_text(json.dumps(checks,indent=2))
        (OUT/'completed.json').write_text(json.dumps({'status':'completed','correctness_passed':all(x['passed'] for x in checks)}))
    except Exception as e:
        (OUT/'failure.json').write_text(json.dumps({'error':str(e)}));raise
    finally:
        for p in children:stop(p)

if __name__=='__main__':
    if len(sys.argv)==1:parent()
    elif sys.argv[1]=='server':server(sys.argv[2])
    else:inference(sys.argv[2])
