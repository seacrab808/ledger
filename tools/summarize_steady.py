"""Validate actual long-run windows and apply the preregistered plateau criterion."""
import argparse
import copy
import csv
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.qmp_metrics import delta_metrics, namespace
from tools.summarize_phase2 import summarize as validate_pilot, stats
from tools.validate_config import audit


def convergence(values, gate):
    mean = statistics.mean(values)
    spread = (max(values) - min(values)) / mean
    center = (len(values) - 1) / 2
    slope = sum((i - center) * (v - mean) for i, v in enumerate(values)) / sum((i - center)**2 for i in range(len(values)))
    relative_slope = abs(slope) / mean
    return {'values': values, 'relative_range': spread, 'abs_relative_slope_per_window': relative_slope,
            'passed': spread <= gate['max_relative_range'] and relative_slope <= gate['max_abs_relative_slope_per_window']}


def summarize(batch, pilot):
    assert batch['status'] == 'passed' and len(batch['runs']) == 6
    plan = batch['plan']
    assert plan['measurement_windows'] == 12 and plan['report_windows'] == 6
    assert plan['measurement_bytes'] == 12 * plan['region_bytes']
    assert batch['config_sha256'] == pilot['config_sha256'] and batch['qemu_sha256'] == pilot['qemu_sha256']
    geometry = audit(batch['config'])
    # A view of actual first-window data, not a synthetic measurement. Reuse the
    # original pilot integrity validator; never save this view as a new run.
    prefix = copy.deepcopy(batch)
    prefix['plan'] = copy.deepcopy(pilot['plan'])
    rows, steady_runs = [], []
    for i, run in enumerate(batch['runs']):
        measurements = run['stages'][2:]
        assert len(measurements) == 12
        assert run['initial_observed_state'] == pilot['runs'][i]['initial_observed_state']
        assert run['qemu_stopped'] and run['qemu_exit_code'] == 0
        assert sum(s['fio_completed_bytes'] for s in measurements) == plan['measurement_bytes'] == run['fio_completed_bytes']
        whole = delta_metrics(measurements[0]['before']['reply'], measurements[-1]['after']['reply'])
        assert whole == run['metrics']
        for k, stage in enumerate(measurements):
            assert stage['name'] == 'measurement-' + str(k + 1)
            assert stage['seed'] == run['seed'] + 1000 * k and stage['pattern'] == run['pattern']
            assert stage['fio_completed_bytes'] == plan['region_bytes']
            m = delta_metrics(stage['before']['reply'], stage['after']['reply'])
            assert m == stage['metrics']
            native = m['native_counter_deltas']
            assert native['host-write-pages'] * 4096 == stage['fio']['jobs'][0]['write']['io_bytes'] == stage['fio_completed_bytes']
            assert native['nand-write-pages'] == native['host-write-pages']
            assert stage['fio']['jobs'][0]['error'] == 0 and stage['fio']['jobs'][0]['read']['io_bytes'] == 0
            expected_rw = '--rw=write ' if run['pattern'] == 'sequential' else '--rw=randwrite '
            for option in [expected_rw, '--direct=1 --iodepth=1 --numjobs=1', '--bs=4096', '--norandommap=1']:
                assert option in stage['command']
            if k:
                assert namespace(measurements[k-1]['after']['reply']) == namespace(stage['before']['reply'])
            for snap in [stage['before'], stage['after']]:
                ns = namespace(snap['reply'])
                c = ns['counters']
                balance = c['nand-write-pages'] + c['gc-write-pages'] - c['block-erases'] * ns['geometry']['pages-per-block']
                closed = (ns['line-counts']['full'] + ns['line-counts']['victim']) * ns['geometry']['pages-per-line']
                assert 0 <= balance <= geometry['raw_bytes'] // 4096
                assert closed <= balance <= closed + ns['geometry']['pages-per-line']
        view = prefix['runs'][i]
        view['stages'] = view['stages'][:4]
        view['metrics'] = delta_metrics(measurements[0]['before']['reply'], measurements[1]['after']['reply'])
        view['fio_completed_bytes'] = 2 * plan['region_bytes']
        view['runtime_seconds'] = sum(s['wall_seconds'] for s in measurements[:2])
        view['fio_job_runtime_ms'] = sum(s['fio_job_runtime_ms'] for s in measurements[:2])
        assert view['metrics'] == pilot['runs'][i]['metrics'], 'Pilot prefix counters differ'
        for window in range(6):
            a, b = measurements[2*window:2*window+2]
            m = delta_metrics(a['before']['reply'], b['after']['reply'])
            host_gib = m['host_page_covered_bytes'] / 1024**3
            assert m['host_page_covered_bytes'] == plan['report_window_bytes']
            assert m['block_erases'] > 0
            rows.append({'run_index': run['index'], 'pattern': run['pattern'], 'replicate': run['replicate'], 'seed': run['seed'],
                         'window': window + 1, 'cumulative_host_gib': (window + 1)*host_gib,
                         'host_gib': host_gib, 'physical_gib': m['modeled_physical_write_bytes'] / 1024**3,
                         'waf': m['waf_pages'], **m['native_counter_deltas'],
                         'erase_per_gib': m['block_erases'] / host_gib,
                         'runtime_seconds': a['wall_seconds'] + b['wall_seconds']})
        selected = [r for r in rows if r['run_index'] == run['index']][-3:]
        criteria = {key: convergence([r[key] for r in selected], plan['convergence']) for key in ['waf', 'erase_per_gib']}
        terminal = delta_metrics(measurements[-6]['before']['reply'], measurements[-1]['after']['reply'])
        steady_runs.append({'run_index': run['index'], 'pattern': run['pattern'], 'seed': run['seed'],
                            'terminal_host_gib': terminal['host_page_covered_bytes'] / 1024**3,
                            'waf': terminal['waf_pages'],
                            'erase_per_gib': terminal['block_erases'] / (terminal['host_page_covered_bytes'] / 1024**3),
                            'convergence': criteria, 'passed': all(v['passed'] for v in criteria.values())})
    validate_pilot(prefix)
    arms = {p: {k: stats([r[k] for r in steady_runs if r['pattern'] == p]) for k in ['waf', 'erase_per_gib']}
            for p in ['sequential', 'random']}
    window_arms = {p: [{k: stats([r[k] for r in rows if r['pattern'] == p and r['window'] == w])
                        for k in ['waf', 'erase_per_gib', 'physical_gib']} for w in range(1, 7)]
                   for p in ['sequential', 'random']}
    difference_pct = {k: (arms['random'][k]['mean'] / arms['sequential'][k]['mean'] - 1)*100
                      for k in ['waf', 'erase_per_gib']}
    gaps = [{k: (window_arms['random'][w][k]['mean'] / window_arms['sequential'][w][k]['mean'] - 1)*100
             for k in ['waf', 'erase_per_gib']} for w in range(6)]
    all_converged = all(r['passed'] for r in steady_runs)
    return {'status': 'validated', 'batch_id': batch['batch_id'], 'window_rows': rows, 'terminal_runs': steady_runs,
            'arms': arms, 'window_arms': window_arms, 'window_gap_pct': gaps, 'terminal_difference_pct': difference_pct,
            'all_replicates_converged': all_converged,
            'random_above_seq_all_windows': all(all(v > 0 for v in g.values()) for g in gaps),
            'pilot_prefix_matches_all_runs': True,
            'classification': 'observed-plateau' if all_converged else 'no-plateau-within-fixed-budget',
            'scope': 'Operational finite-horizon plateau under the frozen FEMU profile; not proof of stationarity at all longer horizons or hardware behavior',
            'runtime_caveat': 'Shared-host and diagnostic-query timing varies; runtime is descriptive, not a controlled performance claim'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    pilot = json.loads((ROOT / 'records/phase-02-pilot.json').read_text(encoding='utf-8'))
    result = summarize(json.loads(args.input.read_text(encoding='utf-8')), pilot)
    result['input_sha256'] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    (ROOT / 'records/phase-02-steady-summary.json').write_bytes((json.dumps(result, ensure_ascii=False, indent=2)+'\n').encode())
    with (ROOT / 'results/phase-02-steady-windows.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result['window_rows'][0]))
        writer.writeheader()
        writer.writerows(result['window_rows'])
    print(json.dumps({k: result[k] for k in ['classification', 'all_replicates_converged', 'arms', 'terminal_difference_pct']}, indent=2))
