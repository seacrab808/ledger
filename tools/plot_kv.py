"""Static scientific screening figures from validated measured summaries."""
import json
from pathlib import Path

def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    root=Path(__file__).resolve().parents[1]
    data=json.loads((root/'records/kv-screen-summary.json').read_text())
    rows=data['rows']; aggregates=data['aggregates']
    out=root/'results/kv_lifecycle/figures'; out.mkdir(exist_ok=True)
    labels=[a['pattern'] for a in aggregates]
    fig,ax=plt.subplots(figsize=(7.5,4))
    used=[100*a['metrics']['token_instance_utilization']['mean'] for a in aggregates]
    sd=[100*a['metrics']['token_instance_utilization']['sample_sd'] for a in aggregates]
    ax.bar(labels,used,color='#287569',label='Unique reused token instances')
    ax.bar(labels,[100-u for u in used],bottom=used,color='#d5ae73',label='Unused at declared horizon')
    ax.errorbar(labels,used,yerr=sd,fmt='none',ecolor='black',capsize=4)
    ax.set(ylabel='Persisted token instances (%)',ylim=(0,105),title='Measured full-state screening: unique use, n=3')
    ax.legend(loc='upper center',bbox_to_anchor=(.5,-.15),ncol=1,frameon=False)
    fig.tight_layout(); fig.savefig(out/'01-token-use.svg',bbox_inches='tight'); plt.close(fig)
    reason_totals={}
    for r in data['reasons']: reason_totals[r['reason']]=reason_totals.get(r['reason'],0)+r['horizon_unused_token_instances']
    fig,ax=plt.subplots(figsize=(8,4)); names=list(reason_totals)
    ax.barh(names,[reason_totals[n] for n in names],color='#8c7057')
    ax.set(xlabel='Unused persisted token instances',title='Observed disposition, not inferred edit/chunk causes')
    fig.tight_layout();fig.savefig(out/'02-unused-disposition.svg');plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,4.5))
    for label in labels:
        r=[x for x in rows if x['pattern']==label]
        ax.scatter([x['persisted_record_bytes']/1024**2 for x in r],[x['disk_saved_prefill_tokens'] for x in r],label=label)
    ax.set(xlabel='Serialized state-record payload written (MiB)',ylabel='Disk-backed saved prefill tokens',title='Measured benefit vs serialized bytes; not NAND writes')
    ax.set_ylim(bottom=-1,top=max(1, max(r['disk_saved_prefill_tokens'] for r in rows)*1.1))
    ax.legend();fig.tight_layout();fig.savefig(out/'03-benefit-vs-bytes.svg');plt.close(fig)
    print('Three measured figures generated; no analytical predictions mixed in.')

if __name__=='__main__': main()
