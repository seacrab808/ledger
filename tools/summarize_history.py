"""Validate real history-control windows and compare an archived matched horizon."""
import csv
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.qmp_metrics import delta_metrics, namespace, KEYS
from tools.validate_config import audit
from tools.summarize_steady import convergence
ROOT = Path(__file__).resolve().parents[1]

def windows(run, count, history):
    stages = run['stages'][history+1:]
    assert len(stages) == count*2
    rows=[]
    for i in range(count):
        a,b=stages[2*i:2*i+2]
        m=delta_metrics(a['before']['reply'],b['after']['reply'])
        host=m['host_page_covered_bytes']/1024**3
        rows.append({'pattern':run['pattern'],'seed':run['seed'],'history_passes':history,'window':i+1,
                     'host_gib':host,'physical_gib':m['modeled_physical_write_bytes']/1024**3,
                     'waf':m['waf_pages'],**m['native_counter_deltas'],
                     'erase_per_gib':m['block_erases']/host,'runtime_seconds':a['wall_seconds']+b['wall_seconds']})
    return rows

def rates(rows):
    host=sum(r['host_gib'] for r in rows)
    return {'host_gib':host,'physical_gib':sum(r['physical_gib'] for r in rows),
            'waf':sum(r['physical_gib'] for r in rows)/host,
            'erase_per_gib':sum(r['block-erases'] for r in rows)/host}

def summarize(batch, archive):
    assert batch['status']=='passed' and len(batch['runs'])==2
    p=batch['plan']; assert p['measurement_windows']==8 and p['report_windows']==4
    assert p['preconditioning']['random_overwrite_passes']==3 and p['comparison']['near_relative_tolerance']==.01
    assert batch['config_sha256']==archive['config_sha256'] and batch['qemu_sha256']==archive['qemu_sha256']
    assert batch['config']==archive['config']
    for key in ['region_bytes','request_bytes','direct','iodepth','numjobs','ioengine','random_distribution','norandommap','random_generator']:
        assert p[key]==archive['plan'][key]
    geometry=audit(batch['config']); rows=[]; comparisons=[]
    assert [{k:r[k] for k in ['pattern','seed','replicate']} for r in batch['runs']]==p['runs']
    for run in batch['runs']:
        assert run['status']=='passed' and run['qemu_stopped'] and run['qemu_exit_code']==0
        assert run['seed']==42 and run['guest']['capacity_bytes']==geometry['exposed_bytes']
        assert all(namespace(run['fresh_zero']['reply'])['counters'][k]==0 for k in KEYS)
        stages=run['stages']; assert len(stages)==12
        assert [s['name'] for s in stages[:4]]==['fill','precondition','precondition-2','precondition-3']
        baseline=next(r for r in archive['runs'] if r['pattern']==run['pattern'] and r['seed']==42)
        assert namespace(stages[1]['after']['reply'])==baseline['initial_observed_state']
        assert run['initial_observed_state']==namespace(stages[3]['after']['reply'])
        assert run['initial_observed_state']==batch['runs'][0]['initial_observed_state']
        for i,s in enumerate(stages):
            if i: assert namespace(stages[i-1]['after']['reply'])==namespace(s['before']['reply'])
            expected_pattern='sequential' if i==0 else 'random' if i<4 else run['pattern']
            expected_seed=p['preconditioning']['seed'] if i<4 else 42+1000*(i-4)
            assert s['pattern']==expected_pattern and s['seed']==expected_seed
            assert s['command']==(baseline['stages'][i-2]['command'] if i>=4 else baseline['stages'][min(i,1)]['command'])
            if i>=4: assert s['name']=='measurement-'+str(i-3)
            assert s['metrics']==delta_metrics(s['before']['reply'],s['after']['reply'])
            m=s['metrics']; assert m['host_page_covered_bytes']==s['fio_completed_bytes']==p['region_bytes']
            assert s['fio']['jobs'][0]['write']['io_bytes']==p['region_bytes'] and s['fio']['jobs'][0]['error']==0
            assert s['fio']['jobs'][0]['read']['io_bytes']==0
            assert m['native_counter_deltas']['nand-write-pages']==p['region_bytes']//4096
            for option in ['--bs=4096','--direct=1 --iodepth=1 --numjobs=1','--norandommap=1',
                           '--randseed='+str(expected_seed),'--rw='+('write' if expected_pattern=='sequential' else 'randwrite')+' ']:
                assert option in s['command']
            for snap in [s['before'],s['after']]:
                ns=namespace(snap['reply']); c=ns['counters']; g=ns['geometry']
                assert g==namespace(baseline['fresh_zero']['reply'])['geometry']
                balance=c['nand-write-pages']+c['gc-write-pages']-c['block-erases']*g['pages-per-block']
                closed=(ns['line-counts']['full']+ns['line-counts']['victim'])*g['pages-per-line']
                assert 0<=balance<=geometry['raw_bytes']//4096 and closed<=balance<=closed+g['pages-per-line']
        assert stages[3]['metrics']['block_erases']>0 and stages[3]['metrics']['native_counter_deltas']['gc-write-pages']>0
        assert run['metrics']==delta_metrics(stages[4]['before']['reply'],stages[-1]['after']['reply'])
        assert run['fio_completed_bytes']==p['measurement_bytes']==sum(s['fio_completed_bytes'] for s in stages[4:])
        new=windows(run,4,3); old=windows(baseline,6,1)[:4]; rows+=old+new
        for r in old+new: assert r['host_gib']==p['report_window_bytes']/1024**3 and r['block-erases']>0
        a,b=rates(old[1:]),rates(new[1:])
        gates={str(h):{k:convergence([r[k] for r in data[1:]],p['convergence']) for k in ['waf','erase_per_gib']}
               for h,data in [(1,old),(3,new)]}
        pct={k:(b[k]/a[k]-1)*100 for k in ['waf','erase_per_gib']}
        comparisons.append({'pattern':run['pattern'],'seed':42,'one_pass_matched':a,'three_pass':b,
                            'first_report_window':{'one_pass':old[0],'three_pass':new[0],
                                'relative_difference_pct':{k:(new[0][k]/old[0][k]-1)*100 for k in ['waf','erase_per_gib']}},
                            'one_pass_archived_late':rates(windows(baseline,6,1)[-3:]),
                            'relative_difference_pct':pct,'convergence':gates,
                            'near':all(abs(v)<=100*p['comparison']['near_relative_tolerance'] for v in pct.values()),
                            'both_histories_converged':all(g['passed'] for hist in gates.values() for g in hist.values())})
    valid=all(c['both_histories_converged'] for c in comparisons)
    near=valid and all(c['near'] for c in comparisons)
    return {'status':'validated','batch_id':batch['batch_id'],'window_rows':rows,'comparisons':comparisons,
            'both_histories_converged':valid,'low_selected_history_sensitivity':near,
            'classification':'low-selected-history-sensitivity' if near else 'history-sensitive-or-inconclusive',
            'scope':'One paired seed per pattern, two selected histories, finite horizon; descriptive tolerance, not statistical equivalence or all-history invariance',
            'full_mapping_state_verified':False,'baseline_reused_not_rerun':True}

if __name__=='__main__':
    raw=ROOT/'records/phase-02-history.json'
    s=summarize(json.loads(raw.read_bytes()),json.loads((ROOT/'records/phase-02-steady.json').read_bytes()))
    s['input_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest()
    (ROOT/'records/phase-02-history-summary.json').write_bytes((json.dumps(s,ensure_ascii=False,indent=2)+'\n').encode())
    with (ROOT/'results/phase-02-history-windows.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(s['window_rows'][0])); w.writeheader();w.writerows(s['window_rows'])
    print(json.dumps({'classification':s['classification'],'comparisons':s['comparisons']},indent=2))
