"""Validate measured native/fio windows, then summarize the approved pilot."""
import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.qmp_metrics import delta_metrics, namespace
from tools.validate_config import audit


def stats(values):
    sd = statistics.stdev(values)
    mean = statistics.mean(values)
    # n=3: two-sided Student t 0.975, df=2. Descriptive model-run interval only.
    half = 4.302652729911275 * sd / math.sqrt(len(values))
    return {'n': len(values), 'mean': mean, 'sample_sd': sd, 'min': min(values), 'max': max(values),
            'descriptive_t95': [mean - half, mean + half]}


def summarize(batch):
    if batch['status'] != 'passed' or len(batch['runs']) != 6:
        raise ValueError('Only a complete six-run batch can be summarized as a successful pilot')
    cfg, plan = batch['config'], batch['plan']
    assert cfg['device']['devsz_mb'] == 3072
    geometry = audit(cfg)
    assert geometry['raw_bytes'] == 4 * 1024**3 and geometry['exposed_bytes'] == 3 * 1024**3
    assert all(sum(r['pattern'] == p for r in batch['runs']) == 3 for p in ['sequential', 'random'])
    assert [{k: r[k] for k in ['pattern', 'seed', 'replicate']} for r in batch['runs']] == plan['runs']
    rows = []
    initial = batch['runs'][0]['initial_observed_state']
    for run in batch['runs']:
        assert run['status'] == 'passed' and run['qemu_stopped'] and run['qemu_exit_code'] == 0
        assert run['initial_observed_state'] == initial
        actual_geometry = namespace(run['fresh_zero']['reply'])['geometry']
        for native_key, config_key in [('channels', 'nchs'), ('luns-per-channel', 'luns_per_ch'),
                                       ('planes-per-lun', 'pls_per_lun'), ('blocks-per-plane', 'blks_per_pl'),
                                       ('pages-per-block', 'pgs_per_blk')]:
            assert actual_geometry[native_key] == cfg['device'][config_key]
        assert actual_geometry['page-size'] == 4096
        assert run['guest']['capacity_bytes'] == geometry['exposed_bytes']
        assert all(namespace(run['fresh_zero']['reply'])['counters'][k] == 0 for k in
                   ['host-write-pages', 'nand-write-pages', 'gc-write-pages', 'block-erases'])
        assert [s['name'] for s in run['stages']] == ['fill', 'precondition', 'measurement-1', 'measurement-2']
        for stage in run['stages']:
            for snap in [stage['before'], stage['after']]:
                ns = namespace(snap['reply'])
                counts = ns['counters']
                programmed_not_erased = (counts['nand-write-pages'] + counts['gc-write-pages'] -
                                         counts['block-erases'] * ns['geometry']['pages-per-block'])
                assert 0 <= programmed_not_erased <= geometry['raw_bytes'] // 4096
                closed_pages = (ns['line-counts']['full'] + ns['line-counts']['victim']) * ns['geometry']['pages-per-line']
                assert closed_pages <= programmed_not_erased <= closed_pages + ns['geometry']['pages-per-line']
            computed = delta_metrics(stage['before']['reply'], stage['after']['reply'])
            assert computed == stage['metrics']
            job = stage['fio']['jobs'][0]
            assert job['error'] == 0 and job['write']['io_bytes'] == computed['host_page_covered_bytes'] == stage['fio_completed_bytes']
            assert job['read']['io_bytes'] == 0
            assert '--direct=1 --iodepth=1 --numjobs=1' in stage['command']
            assert '--bs=4096' in stage['command'] and '--norandommap=1' in stage['command']
        assert run['stages'][0]['fio_completed_bytes'] == plan['region_bytes']
        assert run['stages'][1]['seed'] == plan['preconditioning']['seed']
        warm = run['stages'][1]['metrics']['native_counter_deltas']
        assert warm['block-erases'] > 0 and warm['gc-write-pages'] > 0
        first, second = run['stages'][2:]
        assert first['seed'] == run['seed'] and second['seed'] == run['seed'] + 1000
        assert all(s['pattern'] == run['pattern'] and s['fio_completed_bytes'] == plan['region_bytes']
                   for s in [first, second])
        expected_rw = '--rw=write ' if run['pattern'] == 'sequential' else '--rw=randwrite '
        assert all(expected_rw in s['command'] for s in [first, second])
        assert namespace(first['after']['reply']) == namespace(second['before']['reply'])
        computed = delta_metrics(first['before']['reply'], second['after']['reply'])
        assert computed == run['metrics']
        assert computed['host_page_covered_bytes'] == run['fio_completed_bytes'] == plan['measurement_bytes']
        assert math.isclose(run['runtime_seconds'], first['wall_seconds'] + second['wall_seconds'])
        assert run['fio_job_runtime_ms'] == first['fio_job_runtime_ms'] + second['fio_job_runtime_ms']
        native = computed['native_counter_deltas']
        assert native['nand-write-pages'] == native['host-write-pages']
        assert native['block-erases'] > 0 and native['gc-write-pages'] > 0
        rows.append({'index': run['index'], 'pattern': run['pattern'], 'replicate': run['replicate'], 'seed': run['seed'],
                     'host_gib': run['fio_completed_bytes'] / 1024**3,
                     'physical_gib': computed['modeled_physical_write_bytes'] / 1024**3,
                     **native, 'waf': computed['waf_pages'], 'block_erases': native['block-erases'],
                     'erase_per_gib': native['block-erases'] / (run['fio_completed_bytes'] / 1024**3),
                     'fio_completed_bytes': run['fio_completed_bytes'], 'runtime_seconds': run['runtime_seconds'],
                     'fio_job_runtime_ms': run['fio_job_runtime_ms'],
                     'window1_waf': first['metrics']['waf_pages'], 'window2_waf': second['metrics']['waf_pages'],
                     'window1_erase_per_gib': first['metrics']['block_erases'] / (plan['region_bytes'] / 1024**3),
                     'window2_erase_per_gib': second['metrics']['block_erases'] / (plan['region_bytes'] / 1024**3)})
    arms = {p: {k: stats([r[k] for r in rows if r['pattern'] == p]) for k in
                 ['waf', 'block_erases', 'erase_per_gib', 'physical_gib', 'runtime_seconds']} for p in ['sequential', 'random']}
    pairs = []
    for seed in [42, 43, 44]:
        a = next(r for r in rows if r['pattern'] == 'sequential' and r['seed'] == seed)
        b = next(r for r in rows if r['pattern'] == 'random' and r['seed'] == seed)
        pairs.append({'seed': seed, 'waf_difference_random_minus_seq': b['waf'] - a['waf'],
                      'erase_per_gib_difference_random_minus_seq': b['erase_per_gib'] - a['erase_per_gib']})
    differences = {}
    for metric in ['waf', 'erase_per_gib']:
        a, b = arms['sequential'][metric], arms['random'][metric]
        effect = b['mean'] - a['mean']
        pooled_sd = math.sqrt((a['sample_sd']**2 + b['sample_sd']**2) / 2)
        diffs = [p[metric + '_difference_random_minus_seq'] for p in pairs]
        differences[metric] = {'absolute': effect, 'relative_random_over_seq_minus_one': effect / a['mean'],
                               'pooled_sample_sd': pooled_sd,
                               'same_direction_all_pairs': all(d > 0 for d in diffs) or all(d < 0 for d in diffs),
                               'effect_exceeds_three_pooled_sd': abs(effect) > 3 * pooled_sd,
                               'paired_difference_stats': stats(diffs)}
    strong = all(v['same_direction_all_pairs'] and abs(v['relative_random_over_seq_minus_one']) >= .1 and
                 v['effect_exceeds_three_pooled_sd'] for v in differences.values())
    limited = all(v['same_direction_all_pairs'] for v in differences.values())
    return {'status': 'passed', 'batch_id': batch['batch_id'], 'rows': rows, 'arms': arms, 'paired': pairs,
            'differences': differences, 'classification': 'strong-local-pilot-support' if strong else
            'limited-local-pilot-support' if limited else 'inconclusive',
            'scope': 'Finite-window single FEMU/geometry/fill pilot; not real hardware, wear lifetime, service accounting or policy validation',
            'same_observed_initial_state': True, 'full_mapping_state_verified': False,
            'interval_note': 'n=3 descriptive t intervals; identical deterministic sequential runs do not establish external validity',
            'runtime_caveat': 'Wall runtime includes SSH fio launch; intermittent read-only live QMP diagnostics were not identically scheduled. Shared-host activity also varies. Runtime is recorded, not a controlled performance claim.',
            'next_experiment_candidate': 'Same config/fill/patterns, longer overwrite budget with fixed-size window counters to test convergence and preconditioning transients; needs user approval'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'records/phase-02-summary.json')
    parser.add_argument('--csv', type=Path, default=ROOT / 'results/phase-02-pilot.csv')
    args = parser.parse_args()
    summary = summarize(json.loads(args.input.read_text(encoding='utf-8')))
    summary['input_sha256'] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary['rows'][0]))
        writer.writeheader()
        writer.writerows(summary['rows'])
    print(json.dumps({'classification': summary['classification'], 'arms': summary['arms'], 'differences': summary['differences']}, indent=2))
