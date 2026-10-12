"""Summarize native observations; reject invalid performance interpretation."""
import csv
import hashlib
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'results/lmcache_native/native-01'

def lcp(a,b):
    count=0
    for x,y in zip(a,b):
        if x!=y:break
        count+=1
    return count

def summarize():
    baseline=json.loads((SOURCE/'baseline.json').read_text())
    cold={(r['trace'],r['index']):r for r in baseline}
    traces=json.loads((SOURCE/'input.json').read_text())
    oracle={}
    for t in traces:
        past=[]
        for i,r in enumerate(t['requests']):
            tokens=r['prompt_token_ids'];oracle[t['id'],i]=max([lcp(tokens,p) for p in past],default=0);past.append(tokens)
    checks=json.loads((SOURCE/'correctness.json').read_text())
    coverage=json.loads((SOURCE/'coverage.json').read_text())['objects']
    manifest=json.loads((SOURCE/'manifest.json').read_text())
    result={'status':'runtime-complete' if all(c['passed'] for c in checks) else 'runtime-complete-correctness-failed',
            'valid_performance_claim':all(c['passed'] for c in checks),'requests_per_arm':len(baseline),
            'checks_passed':sum(c['passed'] for c in checks),'checks_total':len(checks),
            'limits':manifest['status'],'seed_level':[],'overall':[],
            'measurement_scope':'controlled synthetic archived token IDs; native MP filesystem backend; buffered page-cache condition; one-token request wall time, not isolated GPU prefill time',
            'not_measured':{'physical_NAND_bytes':None,'FS_metadata_write_bytes':None,'metadata_only_RAM_bytes':None,'kernel_syscall_count':None,'isolated_prefill_seconds':None},
            'partial_chunk':'Pinned MP token_hasher discards partial chunks; partial-tail saving option from V1 is not supported by this MP path.'}
    for c in [64,128,256]:
        rows=json.loads((SOURCE/f'{c}.json').read_text())
        io=[json.loads(line) for line in (SOURCE/f'io-{c}.jsonl').read_text().splitlines()]
        for t in traces:
            rr=[r for r in rows if r['trace']==t['id']]
            ee=[e for e in io if e.get('request') and e['request']['trace']==t['id']]
            saved=sum(cold[r['trace'],r['index']]['forward_tokens']-r['forward_tokens'] for r in rr)
            host=sum(r['prompt_tokens'] for r in rr)
            oo=sum(oracle[r['trace'],r['index']] for r in rr)
            reads=[e for e in ee if e['type']=='read'];writes=[e for e in ee if e['type']=='write']
            distinct_reads={e['file']:e['bytes'] for e in reads}
            inventory=[f for f in manifest['cache_inventory'][f'cache-{c}']['files'] if f['name'].endswith('@'+t['id']+'.data')]
            stored={f['name']:f['bytes'] for f in inventory}
            used=sum(stored[k] for k in distinct_reads if k in stored)
            stored_bytes=sum(stored.values())
            covered=[x for x in coverage if x['chunk']==c and x['trace']==t['id']]
            consumed=sum(x['derived_unique_consumed_bytes'] for x in covered)
            v={'trace':t['id'],'chunk':c,'requests':len(rr),'prompt_tokens':host,'oracle_LCP_tokens':oo,
               'prefill_tokens_saved':saved,'actual_forward_tokens':sum(r['forward_tokens'] for r in rr),
               'recompute_vs_LCP_tokens':oo-saved,'saved_token_fraction':saved/host,
               'disk_write_bytes':sum(e['bytes'] for e in writes),'disk_read_bytes':sum(e['bytes'] for e in reads),
               'file_write_operations':len(writes),'file_read_operations':len(reads),
               'stored_unique_bytes':stored_bytes,'read_at_least_once_unique_bytes':used,
               'unique_read_fraction':used/stored_bytes if stored_bytes else None,
               'unused_unique_bytes':stored_bytes-used,'repeated_read_operations':len(reads)-len(distinct_reads),
               'derived_unique_consumed_bytes':consumed,
               'derived_unique_consumed_fraction':consumed/stored_bytes if stored_bytes else None,
               'derived_never_consumed_bytes':stored_bytes-consumed,
               'chunk_reuse_events':sum(x['reuse_requests'] for x in covered),
               'metadata_file_count':len(inventory),'filename_UTF8_bytes':sum(len(f['name'].encode()) for f in inventory),
               'payload_header_bytes':0,'request_wall_mean_ms':statistics.mean(r['seconds'] for r in rr)*1000,
               'baseline_wall_mean_ms':statistics.mean(cold[r['trace'],r['index']]['seconds'] for r in rr)*1000,
               'native_read_total_ms':sum(e['seconds'] for e in reads)*1000,
               'native_write_total_ms':sum(e['seconds'] for e in writes)*1000}
            result['seed_level'].append(v)
        selected=[v for v in result['seed_level'] if v['chunk']==c]
        totals={k:sum(v[k] for v in selected) for k in ['prompt_tokens','oracle_LCP_tokens','prefill_tokens_saved','actual_forward_tokens','recompute_vs_LCP_tokens','disk_write_bytes','disk_read_bytes','file_write_operations','file_read_operations','stored_unique_bytes','read_at_least_once_unique_bytes','unused_unique_bytes','derived_unique_consumed_bytes','derived_never_consumed_bytes','chunk_reuse_events','metadata_file_count','filename_UTF8_bytes']}
        by_seed=[]
        for seed in [42,43,44]:
            group=[v for v in selected if v['trace'].endswith('-'+str(seed))]
            by_seed.append({'seed':seed,**{k:sum(v[k] for v in group) for k in totals},'request_wall_mean_ms':sum(v['request_wall_mean_ms']*v['requests'] for v in group)/sum(v['requests'] for v in group)})
        means={k:{'mean':statistics.mean(v[k] for v in by_seed),'sample_SD':statistics.stdev(v[k] for v in by_seed)} for k in [*totals,'request_wall_mean_ms']}
        result['overall'].append({'chunk':c,**totals,'seed_summary':means,
                                  'request_wall_mean_ms':statistics.mean(r['seconds'] for r in rows)*1000,
                                  'unique_read_fraction':totals['read_at_least_once_unique_bytes']/totals['stored_unique_bytes']})
    result['provenance']={'model_lock':'external/lmcache-model.lock.json','runtime_lock':'external/lmcache-runtime.lock.json',
                          'executed_source_sha256':hashlib.sha256((SOURCE/'source.py').read_bytes()).hexdigest(),
                          'input_sha256':hashlib.sha256((SOURCE/'input.json').read_bytes()).hexdigest(),
                          'coverage_sha256':hashlib.sha256((SOURCE/'coverage.json').read_bytes()).hexdigest(),
                          'fixed_arm_order':['baseline',64,128,256],'asynchronous_write_gap_seconds':.3,
                          'project_commit_at_launch':'6328a98','working_tree_dirty_at_launch':True}
    result['quality']={'greedy_identical':sum(c['greedy_identical'] for c in checks),
                       'common_top20_logprob_within_limit':sum(c['max_abs_logprob_difference']<=.05 for c in checks),
                       'max_abs_logprob_difference':max(c['max_abs_logprob_difference'] for c in checks),
                       'top20_key_set_mismatches':sum(not c['keys_identical'] for c in checks),
                       'interpretation':'All fixed greedy/common-logprob limits passed; stricter top20-key-set gate failed in 14 cases. Preserve both; do not declare full correctness or relax retrospectively.'}
    result['baseline_wall_mean_ms']=statistics.mean(r['seconds'] for r in baseline)*1000
    batch=ROOT/'results/lmcache_native/batch-02/result.json'
    if batch.exists():result['batch_component']=json.loads(batch.read_text())
    out=ROOT/'records/lmcache-native-summary.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (ROOT/'results/lmcache_native/seed-summary.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=result['seed_level'][0]);writer.writeheader();writer.writerows(result['seed_level'])
    print(json.dumps({'status':result['status'],'checks_passed':result['checks_passed'],'checks_total':len(checks),'overall':result['overall']},ensure_ascii=False,indent=2))

if __name__=='__main__':summarize()
