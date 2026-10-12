"""Compact scientific screening plot, with explicit correctness qualification."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['svg.hashsalt']='ledger-native-screening'

ROOT=Path(__file__).resolve().parents[1]
r=json.loads((ROOT/'records/lmcache-native-summary.json').read_text(encoding='utf-8'))
v=r['overall'];x=[str(a['chunk']) for a in v]
fig,axes=plt.subplots(2,2,figsize=(9,6),layout='constrained')
color=['#19647e','#28afb0','#e39b35']
items=[('Actual forward tokens saved',[a['prefill_tokens_saved'] for a in v],'tokens'),
       ('File payload written',[a['disk_write_bytes']/2**20 for a in v],'MiB'),
       ('Native file operations',[a['file_read_operations']+a['file_write_operations'] for a in v],'read + write calls'),
       ('One-token request wall time',[a['request_wall_mean_ms'] for a in v],'ms')]
for ax,(title,values,unit) in zip(axes.flat,items):
    errors=[a['seed_summary']['request_wall_mean_ms']['sample_SD'] for a in v] if unit=='ms' else None
    ax.bar(x,values,color=color,yerr=errors,capsize=4 if errors else 0)
    ax.set(title=title,xlabel='Chunk tokens',ylabel=unit)
    ax.spines[['top','right']].set_visible(False)
    for i,y in enumerate(values):ax.text(i,y+(errors[i] if errors else 0)+max(values)*.03,f'{y:,.1f}' if unit=='ms' else f'{y:,.0f}',ha='center',fontsize=9)
    ax.set_ylim(0,max(values)*1.25)
    if unit=='ms':
        ax.axhline(r['baseline_wall_mean_ms'],linestyle='--',color='#555',label='Cold baseline')
        ax.legend(fontsize=8)
fig.suptitle('LMCache MP filesystem: controlled synthetic paired screening\n14/792 top-20 key-set checks failed; greedy outputs all identical',fontsize=12)
dest=ROOT/'docs/assets/lmcache-native-screening.svg'
dest.parent.mkdir(parents=True,exist_ok=True)
fig.savefig(dest,metadata={'Date':None});fig.savefig(dest.with_suffix('.png'),dpi=160)
dest.write_text('\n'.join(line.rstrip() for line in dest.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8',newline='\n')
print('Saved native screening figure.')
