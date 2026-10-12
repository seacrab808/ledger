"""Paired token replay of immutable synthetic traces; analytical references only."""
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]

def lcp(a,b):
    for i,(x,y) in enumerate(zip(a,b)):
        if x!=y:return i
    return min(len(a),len(b))

def percentile(values,p):
    if not values:return None
    v=sorted(values);position=(len(v)-1)*p;lo=int(position);hi=min(lo+1,len(v)-1)
    return v[lo]+(v[hi]-v[lo])*(position-lo)

def distribution(values):
    return {'n':len(values),'min':min(values) if values else None,'max':max(values) if values else None,
            'mean':statistics.mean(values) if values else None,
            **{f'p{int(p*100)}':percentile(values,p) for p in (.5,.9,.95)}}

def savings(prefix,prompt,c=None):
    assert 0<=prefix<=prompt and prompt>0
    if c is not None:prefix=prefix//c*c
    return min(prefix,prompt-1)

def replay(run,events,chunks):
    objects=run['objects']; by_request={o['request_id']:o for o in objects}
    by_id={o['object_id']:o for o in objects}
    reads={e['request_id']:e for e in events if e['event']=='DISK_READ'}
    starts={e['request_id']:e for e in events if e['event']=='REQUEST_START'}
    history=[];queries=[];request_rows=[]
    native_rows=[]
    for q in run['requests']:
        assert q['prompt_tokens']==len(q['prompt_token_ids'])
        candidates=[o for o in history if o['session_id']==q['session_id']]
        source=max(enumerate(candidates),key=lambda pair:(lcp(pair[1]['token_ids'],q['prompt_token_ids']),pair[0]))[1] if candidates else None
        prefix=lcp(source['token_ids'],q['prompt_token_ids']) if source else 0
        oracle=savings(prefix,q['prompt_tokens'])
        row={'pattern':run['pattern'],'seed':run['seed'],'request_id':q['request_id'],
             'session_id':q['session_id'],'action':q['action'],'prompt_tokens':q['prompt_tokens'],
             'prior_same_session_snapshot':bool(candidates),'retained_source_object_id':source['object_id'] if source else None,
             'retained_source_tokens':source['persisted_tokens'] if source else 0,
             'lcp_tokens':prefix,'oracle_saved_tokens':oracle,
             'oracle_recomputed_prompt_tokens':q['prompt_tokens']-oracle,
             'last_logit_refresh_tokens':int(prefix==q['prompt_tokens'] and prefix>0)}
        queries.append(row)
        read=reads.get(q['request_id']); native_prefix=lcp(by_id[read['object_id']]['token_ids'],q['prompt_token_ids']) if read else 0
        resident=starts[q['request_id']]['resident_lcp']
        for c in chunks:
            native_candidate=savings(native_prefix,q['prompt_tokens'],c)
            native_restored=bool(q['loaded_object_id'])
            # Reproduce observed retention/restore decisions, never repair pop semantics.
            native_saved=native_candidate if native_restored else 0
            if not native_restored and read:assert native_prefix<=resident
            native_rows.append({'pattern':run['pattern'],'seed':run['seed'],'request_id':q['request_id'],
                'chunk_size':c,'selected_disk_lcp_tokens':native_prefix,'resident_lcp_tokens':resident,
                'observed_restored':native_restored,'native_reference_saved_tokens':native_saved})
        history.append(by_request[q['request_id']])
    assert len(history)==len(objects)
    assert all(len(o['token_ids'])==o['persisted_tokens'] for o in objects)
    summary=[];object_rows=[]
    for c in chunks:
        used={o['object_id']:0 for o in objects};counts={o['object_id']:0 for o in objects}
        chunk_total=oracle_total=loss_total=boundary_total=tail_loss_total=0
        for q in queries:
            chunk=savings(q['lcp_tokens'],q['prompt_tokens'],c)
            loss=q['oracle_saved_tokens']-chunk
            covered_prefix=min(q['lcp_tokens'],q['retained_source_tokens']//c*c)
            covered_savings=savings(covered_prefix,q['prompt_tokens'])
            tail_loss=q['oracle_saved_tokens']-covered_savings
            boundary_loss=covered_savings-chunk
            assert loss==tail_loss+boundary_loss
            assert 0<=loss<c
            chunk_total+=chunk;oracle_total+=q['oracle_saved_tokens'];loss_total+=loss
            boundary_total+=boundary_loss;tail_loss_total+=tail_loss
            oid=q['retained_source_object_id']
            if chunk:
                used[oid]=max(used[oid],chunk);counts[oid]+=1
                assert used[oid]<=by_id[oid]['persisted_tokens']//c*c
            request_rows.append({**q,'chunk_size':c,'chunk_saved_tokens':chunk,
                'boundary_recomputed_tokens':boundary_loss,'unpersisted_tail_recomputed_tokens':tail_loss,
                'total_chunk_recomputed_tokens':loss,'chunk_recomputed_prompt_tokens':q['prompt_tokens']-chunk})
        stored=unique=tail=0
        for o in objects:
            amount=o['persisted_tokens']//c*c
            unique+=used[o['object_id']];stored+=amount;tail+=o['persisted_tokens']-amount
            object_rows.append({'pattern':run['pattern'],'seed':run['seed'],'object_id':o['object_id'],
                'chunk_size':c,'stored_token_instances':amount,'unique_used_token_instances':used[o['object_id']],
                'horizon_unused_token_instances':amount-used[o['object_id']],
                'unpersisted_tail_tokens':o['persisted_tokens']-amount,'reuse_events':counts[o['object_id']]})
        assert stored+tail==sum(o['persisted_tokens'] for o in objects)
        summary.append({'pattern':run['pattern'],'seed':run['seed'],'chunk_size':c,
            'requests':len(queries),'noninitial_requests':sum(q['prior_same_session_snapshot'] for q in queries),
            'prompt_tokens':sum(q['prompt_tokens'] for q in queries),'oracle_saved_tokens':oracle_total,
            'chunk_saved_tokens':chunk_total,'boundary_recomputed_tokens':boundary_total,
            'unpersisted_tail_recomputed_tokens':tail_loss_total,'total_chunk_recomputed_tokens':loss_total,
            'total_loss_fraction_of_oracle':loss_total/oracle_total if oracle_total else None,
            'boundary_loss_fraction_of_oracle':boundary_total/oracle_total if oracle_total else None,
            'total_loss_tokens_per_noninitial_request':loss_total/sum(q['prior_same_session_snapshot'] for q in queries),
            'stored_token_instances':stored,'unique_used_token_instances':unique,
            'horizon_unused_token_instances':stored-unique,'unpersisted_tail_tokens':tail,
            'token_instance_utilization':unique/stored if stored else None,
            'reuse_events':sum(counts.values()),'native_reference_saved_tokens':sum(r['native_reference_saved_tokens'] for r in native_rows if r['chunk_size']==c)})
    return queries,request_rows,object_rows,summary,native_rows

def write_csv(path,rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def main():
    started=dt.datetime.now(dt.timezone.utc).isoformat();clock=time.perf_counter()
    config=json.loads((ROOT/'configs/experiments/kv-chunk-replay.json').read_text())
    out=ROOT/'results/kv_chunk_replay';out.mkdir(exist_ok=False)
    queries=[];request_rows=[];objects=[];summary=[];native=[];inputs=[]
    # Verify every original record byte before analysis.
    manifest=json.loads((ROOT/'records/kv-screen-artifacts.json').read_text())
    for f in manifest['files']:
        assert hashlib.sha256((ROOT/f['path']).read_bytes()).hexdigest()==f['sha256'],f['path']
    for pattern in config['patterns']:
        for seed in config['seeds']:
            folder=ROOT/f'results/kv_lifecycle/{pattern}-{seed}'
            for name in ('run.json','events.jsonl'):
                p=folder/name;inputs.append({'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
            run=json.loads((folder/'run.json').read_text())
            events=[json.loads(line) for line in (folder/'events.jsonl').read_text().splitlines()]
            a,b,c,d,e=replay(run,events,config['chunk_sizes'])
            queries+=a;request_rows+=b;objects+=c;summary+=d;native+=e
    distributions=[]
    for p in config['patterns']+['all']:
        q=[r for r in queries if p=='all' or r['pattern']==p]
        distributions.append({'pattern':p,'all_requests':distribution([r['lcp_tokens'] for r in q]),
            'noninitial_requests':distribution([r['lcp_tokens'] for r in q if r['prior_same_session_snapshot']])})
    write_csv(out/'lcp_requests.csv',queries)
    write_csv(out/'paired_requests.csv',request_rows)
    write_csv(out/'object_accounting.csv',objects)
    write_csv(out/'seed_summary.csv',summary)
    write_csv(out/'native_reference.csv',native)
    aggregate=[]
    for p in config['patterns']:
        for c in config['chunk_sizes']:
            rows=[r for r in summary if r['pattern']==p and r['chunk_size']==c]
            metrics={k:{'mean':statistics.mean(r[k] for r in rows),'sample_sd':statistics.stdev(r[k] for r in rows)}
                     for k in rows[0] if k not in ('pattern','seed','chunk_size') and all(r[k] is not None for r in rows)}
            aggregate.append({'pattern':p,'chunk_size':c,'n':3,'metrics':metrics})
    pooled=[]
    for c in config['chunk_sizes']:
        rows=[r for r in summary if r['chunk_size']==c]; oracle=sum(r['oracle_saved_tokens'] for r in rows)
        loss=sum(r['total_chunk_recomputed_tokens'] for r in rows)
        pooled.append({'chunk_size':c,'oracle_saved_tokens':oracle,'chunk_saved_tokens':oracle-loss,
                      'boundary_recomputed_tokens':sum(r['boundary_recomputed_tokens'] for r in rows),
                      'unpersisted_tail_recomputed_tokens':sum(r['unpersisted_tail_recomputed_tokens'] for r in rows),
                      'total_chunk_recomputed_tokens':loss,'total_loss_fraction_of_oracle':loss/oracle,
                      'stored_token_instances':sum(r['stored_token_instances'] for r in rows),
                      'unique_used_token_instances':sum(r['unique_used_token_instances'] for r in rows),
                      'horizon_unused_token_instances':sum(r['horizon_unused_token_instances'] for r in rows),
                      'unpersisted_tail_tokens':sum(r['unpersisted_tail_tokens'] for r in rows)})
    paired=[]
    for p in config['patterns']:
        for high in (128,256,512):
            changes=[]
            for seed in config['seeds']:
                low=next(r for r in summary if r['pattern']==p and r['seed']==seed and r['chunk_size']==64)
                big=next(r for r in summary if r['pattern']==p and r['seed']==seed and r['chunk_size']==high)
                changes.append(big['total_chunk_recomputed_tokens']-low['total_chunk_recomputed_tokens'])
            paired.append({'pattern':p,'comparison':f'{high}->64','saved_additional_tokens_mean':statistics.mean(changes),'sample_sd':statistics.stdev(changes)})
    result={'status':'validated','evidence_kind':'synthetic-token-trace analytical replay',
            'started_at_utc':started,'ended_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'analysis_runtime_seconds':time.perf_counter()-clock,'config':config,'inputs':inputs,
            'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'git_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)),
            'analysis_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'request_count':len(queries),'noninitial_request_count':sum(q['prior_same_session_snapshot'] for q in queries),
            'distributions':distributions,'aggregate':aggregate,'pooled':pooled,'paired':paired,
            'native_saved_tokens_all_sizes':sum(r['native_reference_saved_tokens'] for r in native),
            'max_persisted_snapshot_tokens':max(o['persisted_tokens'] for p in config['patterns'] for seed in config['seeds'] for o in json.loads((ROOT/f'results/kv_lifecycle/{p}-{seed}/run.json').read_text())['objects']),
            'kv_bytes':None,'physical_bytes':None,'latency':None,'batching_effect':None}
    (ROOT/'records/kv-chunk-replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'requests':len(queries),'noninitial':result['noninitial_request_count'],'pooled':pooled},indent=2))

if __name__=='__main__':main()
