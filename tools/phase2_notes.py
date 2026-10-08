"""Korean pilot explanation assembled from actual native/fio records."""


def add_notes(pages, summary, batch, helpers, footprint):
    e, table, section, link = helpers
    arms, differences = summary['arms'], summary['differences']
    plan = batch['plan']
    label = {'strong-local-pilot-support': '이 FEMU pilot 조건 안에서는 강하게 지지',
             'limited-local-pilot-support': '이 FEMU pilot 조건 안에서는 제한적으로 지지',
             'inconclusive': '아직 애매함'}[summary['classification']]
    def mean_sd(pattern, metric):
        v = arms[pattern][metric]
        return f'{v["mean"]:.4f} ± {v["sample_sd"]:.4f}'
    rows = [(e(r['pattern']) + ' #' + str(r['replicate']), str(r['seed']), f'{r["host_gib"]:.6f}',
             f'{r["physical_gib"]:.6f}', f'{r["waf"]:.6f}', str(r['block_erases']),
             f'{r["erase_per_gib"]:.3f}', f'{r["runtime_seconds"]:.2f}') for r in summary['rows']]
    counter_rows = [(e(r['pattern']) + ' #' + str(r['replicate']), *[str(r[k]) for k in
                     ['host-write-pages', 'nand-write-pages', 'gc-write-pages', 'block-erases']],
                     str(r['fio_completed_bytes'])) for r in summary['rows']]
    comparisons = [(e(k), mean_sd('sequential', k), mean_sd('random', k),
                    f'{v["absolute"]:+.6f}', f'{v["relative_random_over_seq_minus_one"]:+.2%}',
                    '3쌍 모두 같은 방향' if v['same_direction_all_pairs'] else '방향이 섞임') for k, v in differences.items()]
    baseline = batch['runs'][0]['initial_observed_state']
    warm = batch['runs'][0]['stages'][1]['metrics']['native_counter_deltas']
    window_rows = [(e(r['pattern']) + ' #' + str(r['replicate']), f'{r["window1_waf"]:.6f}',
                    f'{r["window2_waf"]:.6f}', f'{r["window1_erase_per_gib"]:.3f}',
                    f'{r["window2_erase_per_gib"]:.3f}') for r in summary['rows']]
    observations = []
    for pattern in ['sequential', 'random']:
        selected = [r for r in summary['rows'] if r['pattern'] == pattern]
        change = sum(r['window2_waf'] - r['window1_waf'] for r in selected) / 3
        observations.append(f'{pattern}: 후반 2.10 GiB 구간 WAF − 전반 WAF 평균 = {change:+.6f}. '
                            '차이가 있으면 쓰는 동안 FTL 상태도 바뀐 것입니다.')
    content = (
        '<div class="callout"><strong>' + e(label) + '</strong><p>같은 bytes를 쓰는 비교입니다. '
        '관측은 FEMU 내부 모델에서 나온 것이며 실제 SSD 수명이나 LEDGER 해결책의 효과를 증명하지 않습니다.</p></div>' +
        '<div class="grid"><div class="card"><h2>Sequential · 순서대로</h2><p>Host는 4.20 GiB</p><p class="big">내부 ' +
        f'{arms["sequential"]["physical_gib"]["mean"]:.3f} GiB</p><p>평균 WAF ' +
        f'{arms["sequential"]["waf"]["mean"]:.4f}</p></div><div class="card"><h2>Random · 균등 무작위</h2>' +
        '<p>Host는 똑같이 4.20 GiB</p><p class="big">내부 ' + f'{arms["random"]["physical_gib"]["mean"]:.3f} GiB</p><p>평균 WAF ' +
        f'{arms["random"]["waf"]["mean"]:.4f}</p></div></div>' +
        section('질문 하나만 봅니다', '<p>OS가 똑같이 4.20 GiB를 썼더라도, 주소를 순서대로 덮어쓰는 것과 '
                '아무 곳이나 골라 덮어쓰는 것이 SSD 내부에서 같은 일을 만들까요? '
                '새 빈 페이지에 쓴 원본과 GC가 옮긴 사본을 함께 세고, 블록을 몇 번 지웠는지 비교했습니다.</p>') +
        section('왜 SSD를 먼저 채웠나', '<p>빈 SSD에 처음 쓰면 빈 NAND page가 충분하므로 예전 데이터를 옮기거나 '
                '블록을 지울 이유가 적습니다. 그러면 두 패턴 모두 erase=0이 나와 중요한 차이를 못 볼 수 있습니다.</p>'
                '<ol><li>매 run마다 새 QEMU 프로세스와 새 boot overlay를 사용했습니다. FEMU counter가 모두 0인지 확인했습니다.</li>'
                '<li>노출된 3 GiB의 앞쪽 약 70%를 sequential로 한 번 채웠습니다. 범위는 '
                f'{plan["region_bytes"]:,} bytes = {plan["region_bytes"]/1024**3:.6f} GiB입니다.</li>'
                '<li>같은 범위를 uniform random으로 한 범위 분량만큼 덮어썼습니다. 모든 run의 준비 seed는 '
                f'{plan["preconditioning"]["seed"]}로 같았습니다. GC copy와 erase 증가를 확인한 뒤에만 비교에 진입했습니다.</li></ol>'
                '<p>70%는 <strong>유효하게 매핑된 logical bytes / exposed capacity</strong>입니다. 파일시스템 사용률이 아닙니다. '
                f'raw 4 GiB의 {batch["live_fraction_raw"]:.2%}가 live data이며 raw·OP·GC threshold는 바꾸지 않았습니다.</p>'
                '<p>나머지 약 0.90 GiB logical 영역은 처음부터 쓰지 않았습니다. 기본 raw spare와 별개로 '
                '미사용 logical 공간도 존재하므로 이 조건의 비용을 가득 찬 장치의 비용으로 일반화하지 않습니다.</p>'
                '<p>준비 overwrite 단계의 native delta: GC pages=' + str(warm['gc-write-pages']) +
                ', block erases=' + str(warm['block-erases']) + '. 따라서 GC gate를 통과했습니다.</p>') +
        section('무엇만 다르게 했나', table(['항목', 'A · sequential', 'B · random'], [
            ('주소 선택', '범위 처음부터 끝까지 순서대로', '같은 범위에서 매번 균등하게 선택; 같은 주소 재방문 허용'),
            ('fio rw', 'write', 'randwrite'), ('request / direct / QD / job', '4 KiB / 1 / 1 / 1', '동일'),
            ('host byte budget', f'{plan["measurement_bytes"]:,} bytes', '동일'),
            ('raw / exposed / GC / FTL', '4 / 3 GiB · 75/95 · page mapping/greedy', '동일'),
            ('reset / preconditioning', '새 process → 같은 fill → 같은 고정 seed random', '동일'),
            ('실행 반복', '3회; seed 42/43/44는 순차 주소에 영향 없음', '3회; 첫 구간 seed 42/43/44'),
            ('두 번째 구간', '같은 시작 주소에서 반복', '첫 구간 seed + 1000'),
            ('환경', 'guest 2 GiB/2 vCPU · libaio · raw NVMe · end_fsync', '동일')]) +
            '<p>run 순서는 S42 → R42 → R43 → S43 → S44 → R44로 섞었습니다. 시간 고정이 아니라 bytes 고정이며 '
            'runtime은 결과입니다. 두 패턴의 고유 주소 방문 수가 다른 것은 주소 패턴의 일부입니다.</p>'
            '<p>준비가 끝난 <strong>native counters·geometry·line counts는 6회 모두 일치</strong>했습니다. '
            '그러나 QMP summary는 전체 mapping/page-validity state를 노출하지 않으므로 그것까지 직접 대조한 것은 아닙니다. '
            '동일 명령·고정 seed·QD1로 상태를 재구성한 것입니다.</p>') +
        section('각 run · 비교 구간만 집계', table(['Run', 'Seed', 'Host GiB', 'Physical GiB', 'WAF',
                'Block erases', 'Erase/GiB', 'Runtime s'], rows) +
                '<p>preconditioning 쓰기와 erase는 이 표에서 제외했습니다. Physical GiB = '
                '(ΔNAND user pages + ΔGC pages) × 4096 / 2³⁰, WAF = physical / host. '
                'Erase/GiB는 Δblock erase / host GiB이며 GC line 횟수와 다릅니다. 한 line은 16 blocks입니다.</p>'
                '<p>Runtime은 두 비교 fio 호출의 wall time 합이며 SSH 실행 시작 overhead를 포함합니다. '
                '진행 점검용 read-only QMP 추가 조회 시점은 run마다 완전히 같지 않았고 공용 host 활동도 달라질 수 있습니다. '
                '따라서 runtime은 기록용이며 통제된 성능 차이로 주장하지 않습니다. counter before/after는 '
                '완료 뒤 안정된 상태에서 수집했습니다.</p>') +
        section('Native counter 원본 delta · fio와 대조', table(['Run', 'Host pages', 'NAND user pages',
                'GC pages', 'Block erases', 'fio completed bytes'], counter_rows) +
                '<p>모든 run에서 host pages × 4096 = fio completed bytes, NAND user pages = host pages였습니다. '
                'GC가 추가로 만든 page만 합산했습니다. 누적 WAF끼리 빼지 않고 before/after counter delta로 계산했습니다.</p>') +
        section('3회 평균과 방향', table(['Metric', 'Sequential mean ± sample SD', 'Random mean ± sample SD',
                'Random − Sequential', '상대 차이', '반복 방향'], comparisons) +
                '<p>SD는 run 사이의 표본 표준편차입니다. 동일한 deterministic sequential 반복에서 SD가 0이어도 '
                '다른 geometry·initial state·실기기까지 확실하다는 뜻은 아닙니다. n=3이므로 정식 일반화 통계로 확대하지 않습니다.</p>'
                '<p>시작 전에 동결한 pilot 기준: 모든 byte/state/GC 검사 통과, 3쌍 모두 같은 방향, '
                'WAF와 erase/GiB 모두 평균 상대 차이 ≥10%, 차이가 pooled sample SD의 3배 초과이면 '
                '현재 조건의 강한 지지로 분류합니다. 10%는 작은 pilot의 practical screening 기준이며 LEDGER 숫자나 '
                'hardware 요구에서 가져온 임계값이 아닙니다. 원시 차이는 기준과 별개로 모두 공개합니다.</p>') +
        section('예상 밖의 결과와 아직 모르는 것', '<p>GC는 작동했지만 준비 이후에도 FTL의 페이지 배치는 계속 바뀝니다. '
                '전체 평균 하나로 그 변화를 숨기지 않기 위해 같은 run 안의 두 2.10 GiB 구간을 따로 남겼습니다.</p>' +
                table(['Run', '전반 WAF', '후반 WAF', '전반 erase/GiB', '후반 erase/GiB'], window_rows) +
                ''.join('<p>' + e(o) + '</p>' for o in observations) +
                '<p>전반/후반 두 구간만으로 steady state를 인증할 수 없습니다. 이번 pilot의 차이는 '
                '동일한 준비 상태에서 시작한 <strong>유한 overwrite 구간의 효과</strong>입니다. '
                'steady-state rate나 서비스마다 고정된 erase rate가 존재한다고 말하지 않습니다.</p>'
                '<p><strong>GC copies=0과 GC 미발생은 다릅니다.</strong> 예전 page가 모두 invalid인 블록은 '
                '살아 있는 page를 옮길 필요 없이 바로 지울 수 있습니다. 그래서 WAF=1인 구간에서도 '
                'erase가 생길 수 있습니다. WAF와 erase는 같은 GC 과정에서 나오는 관련 지표이며 '
                '서로 독립적인 두 증거로 셈하지 않습니다.</p>'
                '<p>첫 시도는 fio 3.36이 uniform 옵션 문자열을 거부해 I/O 전에 중단했습니다. default random 분포가 '
                'uniform이라는 버전별 source를 확인해 그 문자열만 제거했습니다. 실패와 기존 config hash는 보존했습니다. '
                'FEMU source·capacity·GC 설정을 바꿔 결과를 유도하지 않았습니다.</p><p>' +
                link('https://github.com/axboe/fio/blob/fio-3.36/options.c', 'fio 3.36 고정 버전 source · default random 분포') +
                ' · ' + link('https://github.com/axboe/fio/blob/fio-3.36/HOWTO.rst', 'fio 3.36 공식 옵션 설명 · size/io_size/norandommap') + '</p>') +
        section('이 결과로 어디까지 말할 수 있나', '<p><strong>' + e(label) + '</strong>. '
                '동일 logical bytes가 현재 FEMU 조건의 physical work/erase를 충분히 구별하지 못하는지를 직접 비교했습니다. '
                'FTL 모델 하나·fill 하나·작은 geometry·synthetic raw I/O라는 범위를 함께 붙여 보고해야 합니다.</p>'
                '<p>이것만으로 서비스 혼합 간섭, per-service attribution, KV 저장의 이득, 실제 edge 매체 수명이나 '
                'CCGrid contribution이 확보된 것은 아닙니다. ftlsim 절대 erase 수에 맞추지 않았습니다.</p>'
                '<p>가장 먼저 권하는 추가 실험 하나: <strong>동일 설정과 70% fill을 유지하고 overwrite 길이만 늘려 '
                '고정 GiB window의 WAF·erase/GiB가 수렴하는지 확인</strong>하기. 지금 관측한 차이가 준비 직후 '
                '과도현상인지, 지속되는 패턴 효과인지 구분할 수 있습니다. 아직 실행하지 않았고 별도 승인이 필요합니다.</p>') +
        section('재현 자료와 종료 상태', table(['Metadata', '값'], [
            ('Batch', e(batch['batch_id'])), ('실행 Git / dirty', e(batch['project_commit_at_run']) + ' / ' + e(batch['project_dirty_at_run'])),
            ('FEMU commit', e(batch['femu_commit'])), ('Config SHA256', e(batch['config_sha256'])),
            ('Plan SHA256', e(batch['plan_sha256'])), ('Runner SHA256', e(batch['runner_sha256'])),
            ('UTC', e(batch['start_utc']) + ' → ' + e(batch['end_utc'])),
            ('VM 종료', '6회 모두 정상 종료; 각 boot overlay는 종료 후 삭제; 큰 artifact는 Git 제외'),
            ('종료 후 확인', f'실행 중 프로젝트 QEMU {footprint["active_project_qemu_count"]}개 · 작업 폴더 실제 allocation {footprint["workspace_allocated_bytes"]/1024**3:.2f} GiB · FEMU tracked diff 없음'),
            ('공용 서버', 'ledger 내부만 생성·변경. one VM · nice10 · 6 CPU affinity · 12 GiB address-space limit')]) +
            '<p>' + link('../records/phase-02-pilot.json', 'fio·native before/after·정확한 config/plan·seed JSON') + ' · ' +
            link('../records/phase-02-summary.json', '검증·통계 JSON') + ' · ' + link('../results/phase-02-pilot.csv', 'run별 CSV') + ' · ' +
            link('../records/phase-02-attempts.json', '실패 시도 보존') + ' · ' +
            link('../records/phase-02-footprint.json', 'VM 종료·disk allocation·source 무수정 확인') + ' · ' +
            link('../records/phase-02-kvm.json', '새 SSH 세션 KVM 확인') + '</p><p>Phase 2 pilot 종료. 다른 fill/OP/geometry/workload, '
            'LLM, LEDGER 정책, 다음 Phase는 실행하지 않았습니다.</p>'))
    pages['phase-02.html'] = ('Phase 2 pilot · 같은 양, 다른 내부 작업?',
                             '채워 놓은 SSD에 같은 양을 덮어썼습니다. 주소를 고르는 순서만 바꾸고 내부 복사와 소거를 비교했습니다.', content)
    title, lead, body = pages['research-map.html']
    body = body.replace('❓ logical bytes ≠ physical wear는 현재 관찰 후보입니다. 이 저장소에서 확인한 연구 결과가 아닙니다.',
                        'Phase 2 pilot: ' + e(label) + '. FEMU의 한 조건에서 얻은 내부 작업 evidence이며 hardware wear나 해결책 효과는 아직 미검증입니다.')
    pages['research-map.html'] = (title, lead, section('첫 독립 pilot evidence', '<p>' + e(label) + '. '
        '동일 host bytes·같은 준비 상태·GC gate를 통과한 3회 비교입니다.</p>' +
        table(['Metric', 'Sequential mean ± SD', 'Random mean ± SD'],
              [(k, mean_sd('sequential', k), mean_sd('random', k)) for k in ['waf', 'erase_per_gib']]) +
        '<p>' + link('phase-02.html', '범위·원본·전반/후반 변화 확인') + '</p>') + body)
    title, lead, body = pages['experiment-log.html']
    pages['experiment-log.html'] = (title, 'Phase 1 correctness와 Phase 2 유한 overwrite pilot를 구분해 보존합니다.',
        section(batch['batch_id'] + ' · Phase 2 pilot 완료', '<p>' + e(label) + '</p>' +
                table(['Run', 'Seed', 'Host GiB', 'Physical GiB', 'WAF', 'Block erases', 'Erase/GiB', 'Runtime s'], rows) +
                '<p>실행 Git ' + e(batch['project_commit_at_run']) + ' / dirty=' + e(batch['project_dirty_at_run']) + '. UTC ' +
                e(batch['start_utc']) + ' → ' + e(batch['end_utc']) + '.</p><p>' + link('phase-02.html', 'pilot의 조건과 해석') +
                ' · ' + link('../records/phase-02-pilot.json', '측정 provenance 원본') + '</p>') + body)
