"""Observe native full-state disk cache without changing its policy.

Run only on the authorized physical lab host inside ledger. Synthetic completion
fixtures are not production conversation traces. Chunk replay remains design-only.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import time

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

def lcp(a,b):
    for i,(x,y) in enumerate(zip(a,b)):
        if x!=y: return i
    return min(len(a),len(b))

def fixtures(pattern,seed):
    """Distinct pattern/seed fixtures; exact resulting tokens are archived once."""
    r=random.Random(seed)
    topics={'append':['orchards','rainfall','bicycles','libraries'],
            'retry':['bridges','gardens','trains','maps'],
            'edit':['batteries','rivers','sensors','markets'],
            'session_end':['lamps','forests','boats','clocks','rooms','books','roads','birds']}[pattern]
    return [{'session':f'{pattern}-{seed}-{i}', 'topic':topic,
             'detail':r.randint(100,999),'turns':(1 if i<4 else 3) if pattern=='session_end' else 6}
            for i,topic in enumerate(topics)]

def main():
    import resource
    import llama_cpp
    import numpy as np
    from llama_cpp import Llama,LlamaDiskCache
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--mode',choices=['smoke','screen'],required=True)
    ap.add_argument('--seed',type=int,default=42)
    ap.add_argument('--pattern',choices=['append','retry','edit','session_end'],default='append')
    args=ap.parse_args()
    root=args.root.resolve()
    if root!=Path('/home/miruware/ledger').resolve(): raise ValueError('Unauthorized execution directory')
    config=json.loads((root/'configs/experiments/kv-screen.json').read_text())
    model=root/'artifacts/kv-screen/models'/config['model_file']
    assert hashlib.sha256(model.read_bytes()).hexdigest()==config['model_sha256']
    name='smoke' if args.mode=='smoke' else f'{args.pattern}-{args.seed}'
    out=root/'results/kv_lifecycle'/name
    out.mkdir(parents=True,exist_ok=False)
    cache_path=root/'artifacts/kv-screen'/f'cache-{name}'
    if cache_path.exists(): raise ValueError('Existing cache would invalidate fresh-state baseline')
    events=open(out/'events.jsonl','x',encoding='utf-8')
    records={}; requests=[]; context={'request':None}; key_ids={}
    start=dt.datetime.now(dt.timezone.utc).isoformat()
    def event(kind,**kw):
        events.write(json.dumps({'timestamp_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
                    'event':kind,'request_id':context.get('request'),
                    'session_id':context.get('session'),**kw})+'\n'); events.flush()
    def guard():
        rss=int(next(x.split()[1] for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmRSS:')))*1024
        if rss>config['runtime_rss_ceiling_bytes']: raise MemoryError('RSS budget exceeded')

    class Cache(LlamaDiskCache):
        def __getitem__(self,key):
            selected=self._find_longest_prefix_key(tuple(key))
            oid=key_ids.get(selected)
            try: value=super().__getitem__(key)
            except KeyError:
                event('CACHE_MISS'); raise
            context['looked_up']=oid
            event('DISK_READ',object_id=oid,reason='native_pop_on_lookup')
            records[oid]['removal']='CONSUMED_ON_LOOKUP'
            key_ids.pop(selected,None)
            return value
        def __setitem__(self,key,state):
            before=set(self.cache.iterkeys())
            previous=key_ids.get(tuple(key))
            super().__setitem__(key,state)
            after=set(self.cache.iterkeys())
            for k in before-after:
                oid=key_ids.pop(k,None)
                if oid:
                    records[oid]['removal']='EVICTED_BEFORE_REUSE'
                    event('EVICTED',object_id=oid,reason='native_capacity')
            if previous:
                records[previous]['removal']='OVERWRITTEN'
                event('INVALIDATED',object_id=previous,reason='observed_same_key_overwrite')
            oid=f'{name}-v{len(records):04d}'
            # DiskCache's actual Cache.size is serialized value-file size (not NAND bytes).
            db_key,raw=self.cache.disk.put(tuple(key))
            size,filename=self.cache._sql('SELECT size, filename FROM Cache WHERE key=? AND raw=?',(db_key,raw)).fetchone()
            assert filename and size>0, 'Expected file-backed serialized record'
            token_ids=state.input_ids[:state.n_tokens].tolist()
            records[oid]={'object_id':oid,'session_id':context['session'],'request_id':context['request'],
                          'serialized_record_bytes':size,'native_state_bytes':state.llama_state_size,
                          'scores_bytes':state.scores.nbytes,'input_ids_bytes':state.input_ids.nbytes,
                          'persisted_tokens':state.n_tokens,'token_ids':token_ids,
                          'max_reused_prefix_tokens':0,'reuse_count':0,'saved_prefill_tokens':0,
                          'removal':None,'key_hash':digest(list(key))}
            if tuple(key) in after: key_ids[tuple(key)]=oid
            else:
                records[oid]['removal']='EVICTED_BEFORE_REUSE'
                event('EVICTED',object_id=oid,reason='native_capacity_on_insert')
            event('CREATED',object_id=oid,token_start=0,token_end=state.n_tokens)
            event('PERSISTED',object_id=oid,persisted_bytes=size,token_count=state.n_tokens,
                  native_state_bytes=state.llama_state_size,key_hash=records[oid]['key_hash'])

    class Observed(Llama):
        def eval(self,tokens):
            guard()
            if context.get('before_sample'): context['prompt_eval_tokens']+=len(tokens)
            return super().eval(tokens)
        def sample(self,*a,**kw):
            if context.get('before_sample'):
                context['first_logits']=np.ctypeslib.as_array(self._ctx.get_logits(),shape=(self.n_vocab(),)).copy()
            context['before_sample']=False
            return super().sample(*a,**kw)
        def load_state(self,state):
            result=super().load_state(state)
            context['loaded']=context.get('looked_up')
            event('LOADED',object_id=context['loaded'],token_count=state.n_tokens)
            return result

    params=dict(model_path=str(model),n_ctx=config['n_ctx'],n_threads=config['n_threads'],n_threads_batch=config['n_threads_batch'],
                n_batch=config['n_batch'],n_gpu_layers=0,verbose=False,seed=args.seed,
                logits_all=False,no_perf=False)
    llm=Observed(**params)
    cache=Cache(cache_dir=str(cache_path),capacity_bytes=config['disk_cache_capacity_bytes'])
    llm.set_cache(cache)
    def complete(prompt,session,action):
        tokens=llm.tokenize(prompt.encode(),add_bos=True,special=False)
        if len(tokens)+config['max_tokens']>=config['n_ctx']: raise ValueError('Fixture exceeds frozen context')
        resident=llm.input_ids[:llm.n_tokens].tolist()
        context.clear(); context.update(request=f'{name}-r{len(requests):04d}',session=session,
            before_sample=True,prompt_eval_tokens=0,loaded=None,looked_up=None)
        event('REQUEST_START',action=action,prompt_token_ids=tokens,context_length=len(tokens),resident_lcp=lcp(resident,tokens))
        t=time.perf_counter()
        result=llm(tokens,max_tokens=config['max_tokens'],temperature=0.0,seed=args.seed)
        elapsed=time.perf_counter()-t
        skipped=len(tokens)-context['prompt_eval_tokens']
        assert 0<=skipped<=len(tokens)
        oid=context['loaded']
        if oid and skipped:
            record=records[oid]
            assert skipped<=lcp(record['token_ids'],tokens)
            record['max_reused_prefix_tokens']=max(record['max_reused_prefix_tokens'],skipped)
            record['reuse_count']+=1; record['saved_prefill_tokens']+=skipped
            event('REUSED',object_id=oid,token_start=0,token_end=skipped,actual_prefill_tokens_skipped=skipped)
        request={'request_id':context['request'],'session_id':session,'action':action,
                 'prompt_token_ids':tokens,'prompt_tokens':len(tokens),
                 'actual_prompt_eval_tokens':context['prompt_eval_tokens'],
                 'total_prefill_tokens_skipped':skipped,'disk_prefill_tokens_skipped':skipped if oid else 0,
                 'resident_prefill_tokens_skipped':0 if oid else skipped,
                 'loaded_object_id':oid,'runtime_seconds':elapsed,
                 'completion':result['choices'][0]['text'],
                 'completion_tokens':result['usage']['completion_tokens']}
        first_logits=context['first_logits'].copy()
        requests.append(request); event('REQUEST_END',**{k:v for k,v in request.items() if k not in ('request_id','session_id','prompt_token_ids','completion')})
        context['last_first_logits']=first_logits
        return request

    smoke=None
    if args.mode=='smoke':
        prompt='User: Explain how a bicycle works in two short sentences. '+('Mention the wheel and chain. '*12)+'\nAssistant:'
        plain=Llama(**params)
        native_first={}
        original_sample=plain.sample
        def capture_sample(*a,**kw):
            if 'logits' not in native_first:
                native_first['logits']=np.ctypeslib.as_array(plain._ctx.get_logits(),shape=(plain.n_vocab(),)).copy()
            return original_sample(*a,**kw)
        plain.sample=capture_sample
        tokens=plain.tokenize(prompt.encode(),add_bos=True,special=False)
        cold=plain(tokens,max_tokens=32,temperature=0.0,seed=args.seed)['choices'][0]['text']
        a=complete(prompt,'smoke','cold')
        llm.reset() # diagnostic only; screening never does per-request cold reset
        b=complete(prompt,'smoke','explicit_disk_restore_diagnostic')
        partial=prompt+' Please be concise.'
        plain.reset(); native_first.clear(); cold_partial=plain(plain.tokenize(partial.encode(),add_bos=True,special=False),max_tokens=32,temperature=0.0,seed=args.seed)['choices'][0]['text']
        cold_partial_logits=native_first['logits'].copy()
        llm.reset(); c=complete(partial,'smoke','partial_prefix_restore_diagnostic')
        observed_partial_logits=context['last_first_logits'].copy()
        native_cache_path=root/'artifacts/kv-screen/cache-smoke-native-control'
        native_cache=LlamaDiskCache(cache_dir=str(native_cache_path),capacity_bytes=config['disk_cache_capacity_bytes'])
        plain.set_cache(native_cache)
        for text in (prompt,prompt,partial):
            plain.reset(); native_first.clear()
            native_result=plain(plain.tokenize(text.encode(),add_bos=True,special=False),max_tokens=32,temperature=0.0,seed=args.seed)['choices'][0]['text']
        native_partial_logits=native_first['logits'].copy()
        relative_rms=float(np.linalg.norm(observed_partial_logits-cold_partial_logits)/np.linalg.norm(cold_partial_logits))
        max_abs=float(np.max(np.abs(observed_partial_logits-cold_partial_logits)))
        smoke={'cold_matches_observed':cold==a['completion'],'restored_matches_cold':cold==b['completion'],
               'partial_native_restore_matches_observed':native_result==c['completion'],
               'partial_native_restore_logits_match':bool(np.array_equal(native_partial_logits,observed_partial_logits)),
               'cold_prompt_eval_exact':a['actual_prompt_eval_tokens']==a['prompt_tokens'],
               'disk_restore_saves_tokens':b['disk_prefill_tokens_skipped']>0,
               'exact_restore_recomputes_final_token':b['actual_prompt_eval_tokens']==1,
               'partial_restore_saves_tokens':c['disk_prefill_tokens_skipped']>0}
        (out/'numerical-diagnostic.json').write_text(json.dumps({'partial_output_equals_cold':cold_partial==c['completion'],
            'cold_vs_restored_first_logit_relative_rms':relative_rms,'cold_vs_restored_first_logit_max_abs':max_abs,
            'native_vs_observed_first_logit_max_abs':float(np.max(np.abs(native_partial_logits-observed_partial_logits))),
            'note':'Instrumentation gate is identical native restore behavior, not bitwise equality across different quantized decode batch histories.'},indent=2)+'\n')
        native_cache.cache.close(); shutil.rmtree(native_cache_path)
        plain.close()
        if not all(smoke.values()): raise AssertionError(smoke)
    else:
        fs=fixtures(args.pattern,args.seed)
        history={f['session']:[] for f in fs}
        for turn in range(max(f['turns'] for f in fs)):
            for f in fs:
                if turn>=f['turns']: continue
                sid=f['session']; h=history[sid]; action='append'
                if args.pattern=='retry' and turn==3:
                    h.pop(); action='retry_previous_answer'
                else:
                    if args.pattern=='edit' and turn==3:
                        h[:]=h[:2]; h[0]=('user',f"Revise the {f['topic']} plan to prioritize safety instead of cost. Identifier {f['detail']}.")
                        action='edit_first_user_and_discard_later_context'
                    h.append(('user',f"Question {turn+1}: give a brief practical detail about {f['topic']} for case {f['detail']}. "+('Keep it understandable. '*(1+(args.seed+turn)%3))))
                prompt=f"Conversation identifier {sid}.\n"+'\n'.join(('User: ' if role=='user' else 'Assistant: ')+text for role,text in h)+'\nAssistant:'
                req=complete(prompt,sid,action)
                h.append(('assistant',req['completion']))
                if turn+1==f['turns']:
                    event('SESSION_END',reason='predeclared_synthetic_horizon_no_recovery_claim')
    guard()
    final={'status':'passed','mode':args.mode,'pattern':args.pattern,'seed':args.seed,
           'started_at_utc':start,'ended_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
           'config':config,'config_hash':digest(config),'fixture_hash':digest(fixtures(args.pattern,args.seed)) if args.mode=='screen' else None,
           'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           'backend_version':llama_cpp.__version__,'numpy_version':np.__version__,
           'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
           'cpu_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,
           'requests':requests,'objects':list(records.values()),'smoke_checks':smoke,
           'pure_kv_bytes':None,'physical_write_bytes':None,'block_erases':None,
           'trace_kind':'controlled-synthetic','owned_cache_retained':False}
    (out/'run.json').write_text(json.dumps(final,indent=2)+'\n')
    events.close(); cache.cache.close(); llm.close()
    assert cache_path.resolve().is_relative_to(root/'artifacts/kv-screen')
    shutil.rmtree(cache_path) # owned fresh run cache only, inside ledger
    print(json.dumps({'status':'passed','run':name,'requests':len(requests),'smoke':smoke,'peak_rss_bytes':final['peak_rss_bytes']}))

if __name__=='__main__': main()
