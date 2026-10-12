"""Bounded native MP correctness gate; no library source or new policy changes."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

BASE = Path('/home/miruware/ledger/artifacts/lmcache-runtime')
OUT = BASE/'mp-smoke-02-results'

def worker(mode):
    import torch
    torch.set_num_threads(2)
    torch.set_num_interop_threads(2)
    torch.cuda.set_per_process_memory_fraction(3*2**30/torch.cuda.get_device_properties(0).total_memory)
    from vllm.model_executor.models.qwen2 import Qwen2ForCausalLM
    events = []
    original = Qwen2ForCausalLM.forward
    def forward(self, *args, **kwargs):
        ids = args[0] if args else kwargs.get('input_ids')
        if ids is not None: events.append(ids.numel())
        return original(self, *args, **kwargs)
    Qwen2ForCausalLM.forward = forward
    from vllm import LLM, SamplingParams
    options = dict(model=str(BASE/'model'), dtype='float16', max_model_len=1024,
                   max_num_seqs=1, max_num_batched_tokens=1024, enforce_eager=True,
                   kv_cache_memory_bytes=128*2**20, enable_prefix_caching=False,
                   gpu_memory_utilization=3*2**30/torch.cuda.get_device_properties(0).total_memory,
                   disable_log_stats=True, seed=42, compilation_config={'mode':0})
    if mode == 'cached':
        state = json.loads((OUT/'config.json').read_text())
        options['kv_transfer_config'] = {
            'kv_connector':'LMCacheMPConnector', 'kv_role':'kv_both',
            'kv_connector_module_path':'lmcache.integration.vllm.lmcache_mp_connector',
            'kv_connector_extra_config':{'lmcache.mp.host':'tcp://127.0.0.1',
                                         'lmcache.mp.port':state['port'],
                                         'lmcache.mp.isolated_ipc':True}}
    llm = LLM(**options)
    trace = json.loads((BASE/'append-42-run.json').read_text())
    cases = [('warm',trace['requests'][12]['prompt_token_ids']),
             ('exact',trace['requests'][12]['prompt_token_ids']),
             ('extended',trace['requests'][16]['prompt_token_ids']),
             ('truncated',trace['requests'][12]['prompt_token_ids'][:200])]
    params = SamplingParams(temperature=0,max_tokens=1,ignore_eos=True,logprobs=20)
    rows = []
    for name, tokens in cases:
        events.clear(); start = time.monotonic()
        output = llm.generate([{'prompt_token_ids':tokens}],params,use_tqdm=False)[0].outputs[0]
        rows.append({'name':name,'prompt_tokens':len(tokens),'forward_tokens':sum(events),
                     'seconds':time.monotonic()-start,'output_tokens':output.token_ids,
                     'logprobs':{str(k):v.logprob for k,v in output.logprobs[0].items()}})
        (OUT/(mode+'.json')).write_text(json.dumps(rows,indent=2))
        time.sleep(1)  # allow native asynchronous disk persistence, not timed latency
    (OUT/(mode+'.done')).write_text('complete')
    # Native background threads may retain the interpreter. Parent owns cleanup.
    os._exit(0)

def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0)); return s.getsockname()[1]

def stop(p):
    if p.poll() is None:
        p.terminate()
        try: p.wait(timeout=10)
        except subprocess.TimeoutExpired: p.kill(); p.wait()

def parent():
    OUT.mkdir(exist_ok=False)
    (OUT/'source.py').write_bytes(Path(__file__).read_bytes())
    port, http = free_port(), free_port()
    cache = OUT/'cache'; cache.mkdir()
    command = [str(BASE/'venv/bin/lmcache'),'server','--host','127.0.0.1','--port',str(port),
               '--http-host','127.0.0.1','--http-port',str(http),'--chunk-size','128',
               '--max-workers','1','--isolated-ipc','--l1-size-gb','0.125','--no-l1-use-lazy',
               '--l2-adapter',json.dumps({'type':'fs','base_path':str(cache),'use_odirect':False}),
               '--l2-store-policy','skip_l1','--eviction-policy','LRU','--disable-observability']
    (OUT/'config.json').write_text(json.dumps({'port':port,'http_port':http,'server_command':command,
                                             'chunk':128,'native_store_policy':'skip_l1'},indent=2))
    server = None
    try:
        for mode in ('baseline','cached'):
            if mode == 'cached':
                server_log = (OUT/'server.log').open('w')
                server = subprocess.Popen(command,stdout=server_log,stderr=subprocess.STDOUT)
                deadline = time.monotonic()+90
                while True:
                    if server.poll() is not None: raise RuntimeError('Native MP server failed')
                    try:
                        with socket.create_connection(('127.0.0.1',http),timeout=1): break
                    except OSError:
                        if time.monotonic()>deadline: raise RuntimeError('MP startup timeout')
                        time.sleep(1)
            with (OUT/(mode+'.log')).open('w') as log:
                p = subprocess.Popen([sys.executable,__file__,mode],stdout=log,stderr=subprocess.STDOUT)
                try:
                    code = p.wait(timeout=180)
                    if code: raise RuntimeError(mode+' failed')
                finally: stop(p)
        baseline = json.loads((OUT/'baseline.json').read_text())
        cached = json.loads((OUT/'cached.json').read_text())
        checks = []
        for cold, hot in zip(baseline,cached):
            common = cold['logprobs'].keys() & hot['logprobs'].keys()
            error = max(abs(cold['logprobs'][k]-hot['logprobs'][k]) for k in common)
            passed = cold['output_tokens']==hot['output_tokens'] and cold['logprobs'].keys()==hot['logprobs'].keys() and error<=.05
            checks.append({'name':hot['name'],'max_abs_logprob_difference':error,'passed':passed})
        result = {'status':'passed' if all(x['passed'] for x in checks) else 'failed-correctness',
                  'baseline':baseline,'cached':cached,'checks':checks,
                  'disk_files':[{'name':p.name,'bytes':p.stat().st_size} for p in cache.glob('*.data')]}
        (OUT/'result.json').write_text(json.dumps(result,indent=2))
    except Exception as e:
        (OUT/'failure.json').write_text(json.dumps({'status':'failed','error':str(e)}))
        raise
    finally:
        if server: stop(server)

if __name__=='__main__':
    if len(sys.argv)>1: worker(sys.argv[1])
    else: parent()
