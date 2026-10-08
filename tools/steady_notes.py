"""Append the completed steady-state check without replacing historical pilot data."""
import re


def add_notes(pages, summary, batch, svg, helpers):
    e, table, section, link = helpers
    arms, plan = summary['arms'], batch['plan']
    plateau = summary['all_replicates_converged']
    label = '정해 둔 수렴 기준을 6회 모두 통과' if plateau else '고정 길이 안에서 수렴을 확인하지 못함'
    def ms(pattern, metric):
        value = arms[pattern][metric]
        return f'{value["mean"]:.6f} ± {value["sample_sd"]:.6f}'
    windows = []
    for w in range(6):
        a, b = summary['window_arms']['sequential'][w], summary['window_arms']['random'][w]
        windows.append((str(w+1), f'{(w+1)*plan["report_window_bytes"]/1024**3:.2f}',
                        f'{a["waf"]["mean"]:.6f} ± {a["waf"]["sample_sd"]:.6f}',
                        f'{b["waf"]["mean"]:.6f} ± {b["waf"]["sample_sd"]:.6f}',
                        f'{a["erase_per_gib"]["mean"]:.3f}', f'{b["erase_per_gib"]["mean"]:.3f}',
                        f'{summary["window_gap_pct"][w]["waf"]:.2f}%', f'{summary["window_gap_pct"][w]["erase_per_gib"]:.2f}%'))
    raw_rows = [(e(r['pattern']) + ' #' + str(r['replicate']), str(r['window']),
                 f'{r["host_gib"]:.6f}', f'{r["physical_gib"]:.6f}', f'{r["waf"]:.6f}',
                 str(r['gc-write-pages']), str(r['block-erases']), f'{r["erase_per_gib"]:.3f}', f'{r["runtime_seconds"]:.2f}')
                for r in summary['window_rows']]
    checks = []
    for r in summary['terminal_runs']:
        for metric, gate in r['convergence'].items():
            checks.append((e(r['pattern']) + ' / seed ' + str(r['seed']), e(metric),
                           f'{gate["relative_range"]:.3%}', f'{gate["abs_relative_slope_per_window"]:.3%}',
                           '통과' if gate['passed'] else '미통과'))
    svg = re.sub(r'<style\b[^>]*>.*?</style>', '', svg[svg.index('<svg'):], flags=re.DOTALL)
    svg = '\n'.join(line.rstrip() for line in svg.splitlines())
    svg = svg.replace('<svg ', '<svg style="max-width:100%;height:auto;display:block;stroke-linejoin:round;stroke-linecap:butt" ', 1)
    svg = '<div class="scroll"><div style="min-width:700px">' + svg + '</div></div>'
    terminal_table = table(['Metric', 'Sequential mean ± sample SD', 'Random mean ± sample SD', 'Random 상대 차이'],
        [(k, ms('sequential', k), ms('random', k), f'{summary["terminal_difference_pct"][k]:.2f}%') for k in ['waf', 'erase_per_gib']])
    content = (section('추가 확인 · 긴 overwrite에서도 차이가 남는가', '<p><strong>' + label + '</strong>.</p>'
        '<p>위의 짧은 pilot는 그대로 보존했습니다. 이번에는 device·fill·request size·QD·job·direct·preconditioning을 '
        '모두 유지하고 overwrite 길이만 늘렸습니다. FEMU source와 실행 binary도 pilot와 같습니다.</p>'
        '<p>기존 2.10 GiB 단위를 그대로 12번 이어 썼습니다. 두 단위씩 묶은 report window는 '
        f'{plan["report_window_bytes"]/1024**3:.6f} GiB, 각 run 총량은 {plan["measurement_bytes"]/1024**3:.6f} GiB입니다. '
        'FTL은 window 사이에 reset하지 않았습니다. 순차 주소는 같은 70% 영역 끝에서 처음으로 돌아가며, '
        'random seed는 pilot의 seed+1000×subwindow 규칙을 연장했습니다. fio 호출·end_fsync 경계도 유지했습니다.</p>'
        '<p>주의: uniform random은 복원 추출입니다(norandommap=1). sequential은 한 바퀴에 모든 주소를 갱신하지만 '
        'random은 일부 주소를 여러 번 쓰고 일부는 건너뜁니다. 따라서 이 비교는 두 패턴 전체의 효과이며, '
        '주소 순서만의 효과와 갱신 범위·재방문 간격의 효과를 분리한 실험은 아닙니다.</p>'
        '<p>첫 report window의 native counter delta는 해당 seed의 기존 pilot 결과와 <strong>6회 모두 일치</strong>했습니다. '
        '그래서 이전 59.5% 결과와 이번 긴 구간을 같은 프로토콜의 앞부분과 뒷부분으로 비교할 수 있습니다.</p>') +
        section('먼저 고정한 수렴 기준', '<p>마지막 3 report windows(4–6)의 WAF와 erase/GiB 각각에 대해 '
        '① (최댓값−최솟값)/평균 ≤1%, ② 선형 기울기의 절댓값/평균 ≤0.5% per window를 요구했습니다. '
        '두 metric이 모든 replicate에서 통과해야 관측한 plateau로 부릅니다.</p>'
        '<p>길이는 결과를 보고 늘리지 않았습니다. 이것은 작은 모델에서 사용할 운영상 정의입니다. '
        '무한히 오래 같은 분포가 유지되는지 증명하거나 엄밀한 stationarity 검정을 한 것은 아닙니다.</p>' +
        table(['Run', 'Metric', '상대 범위 ≤1%', '상대 추세 ≤0.5%/window', '판단'], checks)) +
        section('Window별 변화 · 3회 평균', svg +
        '<p>작은 화면에서는 그래프와 넓은 표를 좌우로 스크롤해 읽을 수 있습니다.</p>'
        '<p>점은 3회 평균, error bar는 표본 SD입니다. 회색 영역은 사전에 정한 마지막 3 windows의 평가 구간입니다. '
        'SD가 작아 error bar가 점보다 작게 보일 수 있습니다. deterministic sequential의 동일 결과와 SD=0은 '
        '다른 FTL·상태·하드웨어에서도 불확실성이 없다는 뜻이 아닙니다.</p>' +
        table(['Window', '누적 host GiB', 'Seq WAF ± SD', 'Random WAF ± SD', 'Seq erase/GiB', 'Random erase/GiB', 'WAF 차이', 'Erase 차이'], windows)) +
        section('마지막 3 windows의 rate', terminal_table +
        '<p>run마다 마지막 3 windows의 physical writes와 erase를 합쳐 같은 구간의 host bytes로 나눴고, '
        '그 rate를 3회 평균·표본 SD로 정리했습니다. 위 수렴 기준 미통과 시 이 표는 terminal rate이며 '
        'steady-state rate라고 부르지 않습니다.</p><p>' +
        ('현재 관측 길이에서 두 패턴의 차이는 초기 transient가 끝나도 남았습니다.'
         if plateau and summary['random_above_seq_all_windows'] else '현재 결과만으로 안정된 패턴 차이라고 단정할 수 없습니다.') +
        ' 첫 window의 약 59.5%라는 숫자와 terminal 차이는 따로 보고합니다. '
        'WAF와 erase는 같은 GC 메커니즘에서 나온 관련 지표이며 독립된 두 증거가 아닙니다.</p>') +
        section('각 replicate의 6 windows · 원본 값', table(['Run', 'Window', 'Host GiB', 'Physical GiB', 'WAF', 'GC pages', 'Block erases', 'Erase/GiB', 'Runtime s'], raw_rows) +
        '<p>모든 host bytes는 fio completed bytes 및 aligned native host pages와 대조했습니다. '
        '원본은 before/after QMP와 fio JSON이고, physical bytes·WAF·erase/GiB는 counter delta에서 계산했습니다. '
        'GC copies=0이어도 invalid block의 erase는 발생할 수 있습니다. erase는 16-block GC line 단위로 증가하여 '
        '인접 window의 erase/GiB에 작은 진동이 생길 수 있습니다. runtime은 공용 서버의 기술적 기록이며 '
        '통제된 성능 비교로 해석하지 않습니다.</p>') +
        section('문제 정의와 다음 최소 확인', '<p>' +
        ('초기 상태 하나에서 잠깐 보인 차이라는 반론이 약해져, 현재 FEMU 조건의 문제 존재 근거는 더 강해졌습니다.'
         if plateau and summary['random_above_seq_all_windows'] else '수렴 또는 방향 유지에 대한 불확실성이 남아 문제 정의의 강도를 더 높이지 않습니다.') +
        ' 다만 fill·geometry·FTL 하나의 synthetic evidence입니다. 실기기 수명, 서비스 혼합·회계, KV 정책이나 '
        'LEDGER 해결책의 효과는 여전히 미검증입니다.</p><p>다음 최소 실험 후보 하나: ' +
        ('같은 설정·70% fill·두 패턴을 유지하면서 random preconditioning을 1회에서 3회로만 늘려 최종 rate가 같은지 확인하기. '
         '초기 배치에 의존하지 않는 plateau인지 확인할 수 있습니다.' if plateau else
         '같은 설정과 두 패턴에서 overwrite budget만 한 단계 늘려 같은 수렴 기준을 다시 확인하기.') +
        ' 아직 실행하지 않았으며 별도 승인이 필요합니다.</p>') +
        section('긴 실험의 provenance와 종료', table(['항목', '값'], [
            ('Batch / UTC', e(batch['batch_id']) + ' / ' + e(batch['start_utc']) + ' → ' + e(batch['end_utc'])),
            ('실행 Git / dirty', e(batch['project_commit_at_run']) + ' / ' + e(batch['project_dirty_at_run'])),
            ('FEMU pin', e(batch['femu_commit'])), ('Config SHA256', e(batch['config_sha256'])),
            ('Binary SHA256', e(batch['qemu_sha256'])), ('Plan SHA256', e(batch['plan_sha256'])),
            ('Runner SHA256', e(batch['runner_sha256'])), ('경계', '한 VM · 2 GiB/2 vCPU · nice10 · 6 CPU affinity · 12 GiB address-space limit'),
            ('종료', '6회 모두 VM 종료. 기존 pilot artifacts와 원본 HTML 보존. 다른 workload·sweep·정책·다음 Phase는 미실행')]) +
        '<p>' + link('../records/phase-02-steady.json', '전체 fio/QMP/config/seed provenance') + ' · ' +
        link('../records/phase-02-steady-summary.json', 'window와 수렴 판정 JSON') + ' · ' +
        link('../results/phase-02-steady-windows.csv', '36 windows CSV') + ' · ' +
        link('../results/phase-02-steady-convergence.svg', '독립 SVG figure') + ' · ' +
        link('../records/phase-02-steady-footprint.json', '종료 후 VM 0개·disk footprint·source 무수정 확인') + '</p>'))
    title, lead, body = pages['phase-02.html']
    body = body.replace('아직 실행하지 않았고 별도 승인이 필요합니다.', '이 문장은 pilot 종료 시점의 계획입니다. 이후 승인된 긴 overwrite 결과는 아래에 추가했습니다.')
    pages['phase-02.html'] = (title, '짧은 pilot를 보존하고, 같은 설정의 긴 overwrite에서 수렴과 지속성을 추가 확인했습니다.', body + content)
    for page in ['research-map.html', 'experiment-log.html']:
        title, lead, body = pages[page]
        pages[page] = (title, lead, section('추가 evidence · 같은 설정의 긴 overwrite', '<p>' + label + '</p>' + terminal_table +
                      '<p>' + link('phase-02.html', '36 windows·수렴 기준·한계 확인') + '</p>') + body)
    title, lead, body = pages['index.html']
    pages['index.html'] = (title, lead, section('현재 · 긴 overwrite 확인까지 완료', '<p>' + label +
                          '. 다음 실험은 승인 대기입니다.</p>' + terminal_table + '<p>' + link('phase-02.html', '원본과 해석') + '</p>') + body)
