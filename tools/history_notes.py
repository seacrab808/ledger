"""Render measured control evidence and an explicitly unexecuted follow-up design."""

def add_notes(pages,s,b,design,helpers):
    e,table,section,link=helpers
    label='선택한 두 history 사이 민감도가 낮음' if s['low_selected_history_sensitivity'] else 'history 영향 또는 미수렴 불확실성이 남음'
    compare=[]; checks=[]; first=[]
    for c in s['comparisons']:
        for metric in ['waf','erase_per_gib']:
            compare.append((c['pattern'],metric,f'{c["one_pass_matched"][metric]:.6f}',f'{c["three_pass"][metric]:.6f}',
                            f'{c["relative_difference_pct"][metric]:+.3f}%',f'{c["one_pass_archived_late"][metric]:.6f}'))
            f=c['first_report_window']
            first.append((c['pattern'],metric,f'{f["one_pass"][metric]:.6f}',f'{f["three_pass"][metric]:.6f}',f'{f["relative_difference_pct"][metric]:+.3f}%'))
            for history in ['1','3']:
                g=c['convergence'][history][metric]
                checks.append((c['pattern'],history,metric,f'{g["relative_range"]:.3%}',f'{g["abs_relative_slope_per_window"]:.3%}','통과' if g['passed'] else '미통과'))
    rows=[(r['pattern'],str(r['history_passes']),str(r['window']),f'{r["host_gib"]:.6f}',f'{r["physical_gib"]:.6f}',
           f'{r["waf"]:.6f}',str(r['gc-write-pages']),str(r['block-erases']),f'{r["erase_per_gib"]:.3f}') for r in s['window_rows']]
    preparation=[(run['pattern'],stage['name'],f'{stage["metrics"]["waf_pages"]:.6f}',
                  str(stage['metrics']['native_counter_deltas']['gc-write-pages']),str(stage['metrics']['block_erases']))
                 for run in b['runs'] for stage in run['stages'][1:4]]
    content=(section('Initial FTL history control · 작은 추가 확인',
        '<p><strong>'+label+'</strong>. seed 42에서 각 패턴의 3회 history 조건만 한 번씩, 새 run 총 2개를 실행했습니다. '
        '1회 history 조건은 기존 긴 run 원본을 재사용했으며 rerun하지 않았습니다.</p>'
        '<p>FTL history란 지금까지 어떤 순서로 쓰여 내부 page 배치와 GC 상태가 만들어졌는지를 뜻합니다. '
        'raw4/exposed3 GiB·70% fill·4 KiB·direct·QD1/job1·FEMU source/binary는 유지했습니다. '
        '바꾼 것은 기존 seed 20261007의 동일한 random preconditioning을 1회에서 3회로 반복한 것뿐입니다. '
        '반복마다 seed를 바꾸지 않았습니다. 두 새 run은 fresh process에서 각각 재구성했습니다.</p>'
        '<p>첫 preconditioning pass의 native snapshot은 기존 조건과 일치했고, 세 번째 pass 후 GC/erase gate도 확인했습니다. '
        '두 새 run의 관측 baseline은 같았습니다. 전체 mapping을 dump해 검증한 것은 아닙니다.</p>'+
        table(['패턴','준비 pass','준비 WAF','GC copies','Block erases'],preparation)+
        '<p>준비 구간은 측정 byte budget에서 제외합니다. 같은 random sequence를 세 번 반복한 history는 '
        'steady state를 보장하는 방법으로 제안한 것이 아니라, 기존과 다른 초기 이력을 만드는 control입니다.</p>')+
        section('필요한 작은 길이와 먼저 정한 판정',
        '<p>각 run은 2.1 GiB subwindow 8개, 4.2 GiB report window 4개, 총 약 16.8 GiB입니다. '
        '기존 관측에서 초기 변화가 있었던 첫 report window 뒤의 세 windows(2–4)를 평가합니다. '
        '같은 seed·같은 측정 길이의 기존 1회 history windows 2–4와 비교하므로 horizon 차이를 섞지 않습니다.</p>'
        '<p>두 history 각각 마지막 세 windows의 상대 범위 ≤1%·상대 기울기 ≤0.5%/window를 먼저 요구했습니다. '
        'WAF와 erase/GiB의 history 간 rate 차이가 모두 ±1% 이내이면 기술적으로 near라고 정했습니다. '
        '길이·기준은 실행 전에 Git에 고정했고 결과를 보고 늘리지 않았습니다.</p>'
        '<p>n=1 per pattern/history의 작은 control입니다. SD나 confidence interval을 만들어 붙이지 않습니다. '
        '±1%는 기술적 허용 범위이며 통계적 equivalence 검정이나 모든 초기 상태의 무관함을 증명하지 않습니다.</p>'+
        table(['패턴','Metric','1회 · 같은 horizon','3회 · control','3회−1회 상대차','1회 · 기존 late 참고'],compare)+
        table(['패턴','History passes','Metric','상대 범위','상대 기울기/window','판정'],checks))+
        section('History별 window · 측정과 계산',table(['Pattern','History','Window','Host GiB','Physical GiB','WAF','GC pages','Erases','Erase/GiB'],rows)+
        '<p>1회 행은 보존된 archive, 3회 행은 새 실측입니다. host bytes는 fio 완료 bytes와 native host pages로 대조했습니다. '
        'physical bytes는 NAND user pages+GC copies에서 계산하며 WAF·erase/GiB는 window delta를 사용합니다. '
        'FEMU 모델의 값이며 실제 NAND 수명 측정은 아닙니다.</p>')+
        section('초기 구간도 그대로 보고합니다',table(['패턴','Metric','1회 첫 window','3회 첫 window','차이'],first)+
        '<p>이 표는 첫 4.2 GiB 구간의 기술적 관측이며, 사전에 고정한 terminal 비교와 분리합니다. '
        '초기 transient 비용이 history에 민감하더라도 후반 rate는 같을 수 있습니다. 초기 차이를 숨기거나 '
        '초기와 후반을 합쳐 history가 전혀 중요하지 않다고 말하지 않습니다.</p>')+
        section('해석과 남은 범위','<p>'+label+'. '
        +('현재 sequential≈1/random≈1.9 차이가 random preconditioning 1회라는 특정 이력에만 붙어 있는 현상이라는 설명은 약해졌습니다. '
          if s['low_selected_history_sensitivity'] else '이 길이와 두 history만으로 기존 terminal 차이가 초기 상태와 무관하다고 판단하지 않습니다. ')+
        '하지만 다른 seed·다른 종류의 history·다른 fill/FTL/실기기로 일반화하지 않습니다. 해결책 구현은 아직 하지 않았습니다.</p>')+
        section('다음 우선 실험 · 세 패턴 비교는 설계만',
        table(['패턴','한 round','Coverage'],[('Sequential','0부터 N−1까지','모든 주소 정확히 한 번'),
             ('Random permutation','전체 N개 주소의 Fisher–Yates shuffle','모든 주소 정확히 한 번'),
             ('Uniform replacement random','같은 N개 주소에서 N회 복원 추출','재방문·미방문 허용')])+
        '<p>N=550,502 pages입니다. S↔P는 exact coverage를 유지한 순서 효과를, P↔R은 재방문·uneven coverage와 '
        '이에 연결된 시간적 locality의 묶음을 비교합니다. 후자를 순수한 한 요인의 효과나 보편적인 인과 비중으로 부르지 않습니다.</p>'
        '<p>같은 device·fill·request·QD·direct·공통 history·byte budget을 제안합니다. 공통 history는 기존 '
        'random preconditioning 1회를 우선 후보로 유지하되 실행 전 사용자 검토로 고정합니다. seed 42–44의 9 runs와 '
        '순환 실행 순서, 공통 25.2 GiB ceiling·마지막 3 windows 수렴 판정을 승인 전에 고정해야 합니다. '
        'P의 실제 수렴 속도는 아직 모릅니다. 결과를 보고 특정 arm만 늘리거나 일부 구간을 선택하지 않습니다.</p>'
        '<p>가능하면 동일 fio replay 경로로 세 trace를 제출합니다. 향후 S/R의 직접 경로와 replay가 같은 주소 sequence와 '
        'native 결과를 내는지 먼저 검증해야 합니다. 현재 R generator를 몰래 교체하지 않습니다. LFSR이나 randommap 옵션만 '
        '바꾼 workload를 uniform permutation이라고 이름 붙이지 않습니다.</p>'
        '<p>trace 검사: 총 요청 수·bytes·정렬·범위, S/P 주소별 빈도=1, reproducible seed/hash, 실제 발행 순서, '
        'R unique coverage·주소 빈도·재방문 간격을 보존합니다. 약 63.2% coverage는 이론적 참고값이며 측정 합격 기준이 아닙니다.</p>'
        '<p>P≈S&lt;R이면 replacement/coverage 묶음이 더 중요한 후보, S&lt;P≈R이면 무작위 순서만으로도 큰 비용이 가능한 후보, '
        'S&lt;P&lt;R이면 두 비교 모두 기여하는 후보입니다. 예상 밖 순위와 미수렴도 보존합니다.</p>'
        '<p><strong>Permutation generator·trace·3-pattern benchmark를 만들거나 실행하지 않았습니다.</strong> '
        +link('THREE_PATTERN_PLAN.md','상세 설계')+' · '+link('../records/phase-02-three-pattern-plan.json','기계 판독 계획')+' · '
        +link(design['references'][0],'fio 3.36 공식 기능 문서')+'</p>')+
        section('Control provenance와 종료',table(['항목','기록'],[('Batch',e(b['batch_id'])),('UTC',e(b['start_utc'])+' → '+e(b['end_utc'])),
             ('Run Git/dirty',e(b['project_commit_at_run'])+' / '+e(b['project_dirty_at_run'])),('Plan SHA256',e(b['plan_sha256'])),
             ('FEMU/source/binary','기존 commit/config/binary와 동일. 한 VM·2 GiB/2 vCPU·nice10·6 CPU affinity·12 GiB AS limit'),
             ('종료','소유 VM 모두 종료. 원본 pilot/steady 자료 보존. 다음 실험 미실행')])+
        '<p>'+link('../records/phase-02-history.json','전체 native/fio 기록')+' · '+link('../records/phase-02-history-summary.json','검증된 비교')+' · '
        +link('../results/phase-02-history-windows.csv','Window CSV')+' · '+link('../records/phase-02-history-footprint.json','종료 점검')+'</p>'))
    title,lead,body=pages['phase-02.html']
    body=body.replace('아직 실행하지 않았으며 별도 승인이 필요합니다.</p>', '이것은 긴 overwrite 종료 시점의 후보였습니다. 이후 승인된 control 결과를 아래에 추가했습니다.</p>')
    pages['phase-02.html']=(title,'Pilot·긴 overwrite·작은 history control을 구분해 보존합니다. 다음 세 패턴 비교는 설계만 했습니다.',body+content)
    for page in ['research-map.html','experiment-log.html','index.html']:
        title,lead,body=pages[page]
        body=body.replace('현재 · 긴 overwrite 확인까지 완료','이전 완료 · 긴 overwrite 확인')
        pages[page]=(title,lead,section('현재 · History control 완료 / 다음 실험 설계만', '<p>'+label+'. 새 run은 두 개입니다. '
            '다음 단계는 순서와 coverage를 분리하는 세 패턴 비교이며 아직 미실행입니다.</p>'+table(['패턴','Metric','1회 matched','3회','차이','기존 late 참고'],compare)+
            '<p>'+link('phase-02.html','Control 결과와 설계 보기')+'</p>')+body)
