"""Standalone scientific SVG from measured windows; uses an existing matplotlib."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    summary = json.loads((ROOT / 'records/phase-02-steady-summary.json').read_text(encoding='utf-8'))
    assert summary['status'] == 'validated'
    plt.rcParams.update({'svg.fonttype': 'none', 'font.size': 10, 'axes.spines.top': False,
                         'axes.spines.right': False, 'svg.hashsalt': 'ledger-steady-v1'})
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), constrained_layout=True)
    unit = next(r['host_gib'] for r in summary['window_rows'])
    xs = [unit * n for n in range(1, 7)]
    for ax, metric, label in zip(axes, ['waf', 'erase_per_gib'], ['WAF (physical / host)', 'Block erases / host GiB']):
        ax.axvspan(xs[2], xs[-1], color='#e9eee8', label='Terminal assessment' if metric == 'waf' else None)
        for pattern, color, marker in [('sequential', '#226653', 'o'), ('random', '#ae592b', 's')]:
            vals = summary['window_arms'][pattern]
            ax.errorbar(xs, [v[metric]['mean'] for v in vals], yerr=[v[metric]['sample_sd'] for v in vals],
                        color=color, marker=marker, capsize=3, linewidth=1.8, label=pattern.title())
        ax.set_xlabel('Cumulative host overwrite (GiB)')
        ax.set_ylabel(label)
        ax.set_xticks(xs, [f'{x:.1f}' for x in xs])
        ax.grid(axis='y', alpha=.2)
        ax.set_xlim(0, xs[-1] + unit/3)
    axes[0].legend(frameon=False, fontsize=8, loc='center right')
    fig.suptitle('Same FEMU profile / 70% logical fill / 4 KiB / QD1 / 3 replicates', fontsize=11)
    fig.savefig(ROOT / 'results/phase-02-steady-convergence.svg', metadata={'Date': None})
    output = ROOT / 'results/phase-02-steady-convergence.svg'
    output.write_bytes(('\n'.join(line.rstrip() for line in output.read_text(encoding='utf-8').splitlines())+'\n').encode())
    plt.close(fig)
    print('Measured window plot exported; bars show sample SD, not confidence intervals.')
