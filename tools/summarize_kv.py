"""Derive screening tables from runtime records; never infer physical NAND bytes."""
import csv
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]

def summarize(run):
    objects=run['objects']; requests=run['requests']
    stored_bytes=sum(o['serialized_record_bytes'] for o in objects)
    stored_tokens=sum(o['persisted_tokens'] for o in objects)
    native_bytes=sum(o['native_state_bytes'] for o in objects)
    scores_bytes=sum(o['scores_bytes'] for o in objects)
    useful_records=[o for o in objects if o['reuse_count']>0]
    unique_record_bytes=sum(o['serialized_record_bytes'] for o in useful_records)
    unique_tokens=sum(o['max_reused_prefix_tokens'] for o in objects)
    saved=sum(q['disk_prefill_tokens_skipped'] for q in requests)
    assert saved==sum(o['saved_prefill_tokens'] for o in objects)
    assert 0<=unique_tokens<=stored_tokens and 0<=unique_record_bytes<=stored_bytes
    assert all(0<=o['max_reused_prefix_tokens']<=o['persisted_tokens'] for o in objects)
    return {'pattern':run['pattern'],'seed':run['seed'],'requests':len(requests),
            'persisted_record_bytes':stored_bytes,'unique_ever_used_record_bytes':unique_record_bytes,
            'native_state_bytes':native_bytes,'serialized_scores_array_bytes':scores_bytes,
            'scores_array_fraction_of_record_bytes':scores_bytes/stored_bytes,
            'never_used_record_bytes_at_horizon':stored_bytes-unique_record_bytes,
            'record_ever_used_ratio':unique_record_bytes/stored_bytes,
            'persisted_token_instances':stored_tokens,'unique_reused_token_instances':unique_tokens,
            'horizon_unused_token_instances':stored_tokens-unique_tokens,
            'token_instance_utilization':unique_tokens/stored_tokens,
            'horizon_unused_token_ratio':1-unique_tokens/stored_tokens,
            'disk_saved_prefill_tokens':saved,'reuse_events':sum(o['reuse_count'] for o in objects),
            'resident_saved_prefill_tokens':sum(q['resident_prefill_tokens_skipped'] for q in requests),
            'serialized_bytes_per_disk_saved_token':stored_bytes/saved if saved else None,
            'runtime_seconds':sum(q['runtime_seconds'] for q in requests),
            'peak_rss_bytes':run['peak_rss_bytes'],'cpu_seconds':run['cpu_seconds'],
            'capacity_evictions':sum(o['removal']=='EVICTED_BEFORE_REUSE' for o in objects)}

def write_csv(path,rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def main():
    base=ROOT/'results/kv_lifecycle'
    smoke=json.loads((base/'smoke/run.json').read_text()); assert all(smoke['smoke_checks'].values())
    paths=[base/f'{p}-{seed}/run.json' for seed in (42,43,44) for p in ('append','retry','edit','session_end')]
    runs=[json.loads(p.read_text()) for p in paths]
    assert len({r['config_hash'] for r in runs})==1 and all(r['status']=='passed' for r in runs)
    rows=[summarize(r) for r in runs]
    write_csv(base/'summary.csv',rows)
    aggregates=[]
    fields=[k for k in rows[0] if k not in ('pattern','seed')]
    for p in ('append','retry','edit','session_end'):
        subset=[r for r in rows if r['pattern']==p]
        aggregates.append({'pattern':p,'n':len(subset),'metrics':{k:{'mean':statistics.mean(r[k] for r in subset),'sample_sd':statistics.stdev(r[k] for r in subset)} for k in fields if all(r[k] is not None for r in subset)}})
    reasons=[]
    for run in runs:
        totals={}
        for o in run['objects']:
            # Every object can still contain a never-used tail after a partial hit.
            n=o['persisted_tokens']-o['max_reused_prefix_tokens']
            reason=o['removal'] or 'HORIZON_END_NOT_PROVEN_INVALID'
            row=totals.setdefault(reason,{'pattern':run['pattern'],'seed':run['seed'],'reason':reason,'horizon_unused_token_instances':0,'never_used_whole_record_bytes':0})
            row['horizon_unused_token_instances']+=n
            if not o['reuse_count']: row['never_used_whole_record_bytes']+=o['serialized_record_bytes']
        reasons.extend(totals.values())
    write_csv(base/'reason_breakdown.csv',reasons)
    lookup_rows=[]
    for path,run in zip(paths,runs):
        events=[json.loads(line) for line in (path.parent/'events.jsonl').read_text().splitlines()]
        requests={q['request_id']:q for q in run['requests']}
        objects={o['object_id']:o for o in run['objects']}
        resident={event['request_id']:event['resident_lcp'] for event in events if event['event']=='REQUEST_START'}
        for event in events:
            if event['event']!='DISK_READ':continue
            q=requests[event['request_id']];o=objects[event['object_id']]
            prefix=0
            for x,y in zip(o['token_ids'],q['prompt_token_ids']):
                if x!=y:break
                prefix+=1
            lookup_rows.append({'pattern':run['pattern'],'seed':run['seed'],'request_id':q['request_id'],
                'object_id':o['object_id'],'disk_state_prefix_tokens':prefix,
                'resident_prefix_tokens':resident[q['request_id']],
                'restored':q['loaded_object_id'] is not None,'disk_saved_prefill_tokens':q['disk_prefill_tokens_skipped']})
    write_csv(base/'lookup_analysis.csv',lookup_rows)
    final={'status':'validated','kind':'controlled-synthetic-full-state-screening',
           'run_count':12,'smoke_checks':smoke['smoke_checks'],'aggregates':aggregates,
           'rows':rows,'reasons':reasons,'lookup_analysis':lookup_rows,
           'lookup_summary':{'disk_reads':len(lookup_rows),'restored':sum(r['restored'] for r in lookup_rows),
                'not_restored_and_disk_lcp_not_better_than_resident':sum(not r['restored'] and r['disk_state_prefix_tokens']<=r['resident_prefix_tokens'] for r in lookup_rows)},
           'screening_reuse_positive_control':all(r['disk_saved_prefill_tokens']>0 for r in rows if r['pattern']=='append'),
           'chunk_replay_status':'designed-not-executed',
           'pure_kv_useful_bytes':None,'physical_bytes':None,'erase':None,
           'limitations':['Record-level ever-used bytes include the unused tail and non-KV state; not fine-grained KV byte utilization.',
                          'Token-instance utilization counts each persisted version separately and unions reuse ranges within that version.',
                          'All synthetic sessions end at a declared finite horizon; horizon-unused is not infinite-future dead.',
                          'Native pop-on-lookup can remove a record without load_state; edit/retry are not automatically semantic invalidation.',
                          'No real trace, chunk backend, batching, crash recovery or physical storage experiment was measured.']}
    (ROOT/'records/kv-screen-summary.json').write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Validated 12 measured runs; tables and summary generated.')

if __name__=='__main__': main()
