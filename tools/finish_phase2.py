"""Update provisional research decisions from validated pilot records; no guest I/O."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / 'records' / name).read_text(encoding='utf-8'))


if __name__ == '__main__':
    summary, batch = load('phase-02-summary.json'), load('phase-02-pilot.json')
    assert summary['status'] == batch['status'] == 'passed'
    research = load('research.json')
    research['scope'] = 'Phase 1과 승인된 Phase 2 pilot만 완료했다. 단일 FEMU 조건의 pattern 효과를 관찰했으며 해결 방향은 아직 미정이다.'
    for phase in research['roadmap']:
        if phase['phase'] == 1:
            phase['status'] = 'complete'
        elif phase['phase'] == 2:
            phase['status'] = 'pilot-complete-further-experiments-not-authorized'
    a, b = summary['arms']['sequential'], summary['arms']['random']
    evidence = (f'독립 FEMU pilot에서 동일 host 4.20 GiB·70% logical fill·3회씩 비교했다. '
                f'평균 WAF sequential={a["waf"]["mean"]:.4f}, random={b["waf"]["mean"]:.4f}; '
                f'erase/GiB={a["erase_per_gib"]["mean"]:.3f} / {b["erase_per_gib"]["mean"]:.3f}. '
                'GC gate와 동일 observed baseline이 통과했다. 단일 geometry의 유한 구간이며 service attribution은 미검증이다.')
    research['directions'][0]['evidence'] = '기존 ftlsim 보고와 별개로: ' + evidence
    research['directions'][-1]['evidence'] = (f'현재 pilot 분류={summary["classification"]}. '
        '한 FEMU 조건에서만 관찰했으므로 다른 상태·FTL·실기기에서는 차이가 작거나 사라질 가능성이 열려 있다.')
    for decision in research['decisions']:
        if decision['id'] == 'D013':
            decision['status'] = 'review-complete-user-authorized-pilot-see-D014'
    decisions = [
        {'id': 'D014', 'title': '사용자 승인 범위를 70% fill의 sequential/random pilot로 한정',
         'reason': 'Phase 1 완료 검토 후 사용자가 두 패턴·각 3회만 승인했다. 4/3 GiB와 모든 device 설정을 유지했다.',
         'alternatives': 'fill/OP/geometry sweep, 서비스 패턴 또는 정책으로 바로 확장',
         'why_not': '이번에는 동일 bytes에서 내부 작업 차이가 존재하는지 하나만 본다.', 'status': 'completed'},
        {'id': 'D015', 'title': 'fresh process와 동일 preconditioning, GC gate 뒤 byte 고정 비교',
         'reason': '각 run 70% 영역 fill + 고정 seed uniform overwrite 후 native GC copies/erase 증가를 확인했다. 비교 4.20 GiB는 준비 쓰기를 제외한다.',
         'alternatives': '빈 SSD 비교, 이전 run 상태 계승, 시간 고정',
         'why_not': 'GC 부족·initial-state 차이·byte budget 차이를 섞지 않는다. full mapping state 직접 검증은 하지 못했다.', 'status': 'measured'},
        {'id': 'D016', 'title': 'fio 3.36 옵션 오류를 보존하고 default uniform을 사용',
         'reason': '첫 시도는 random_distribution=uniform parsing에서 I/O 전에 중단됐다. 해당 버전의 default random이 균등 분포임을 확인했다.',
         'alternatives': 'fio 업그레이드, 다른 분포나 FEMU 설정으로 변경, 실패 삭제',
         'why_not': '지원되는 default로 충분하다. 수정은 unsupported 문자열 제거뿐이며 실패 provenance를 남겼다.', 'status': 'resolved'},
        {'id': 'D017', 'title': 'finite-window pilot 관측과 steady-state/hardware 주장을 구분',
         'reason': evidence,
         'alternatives': 'pilot 평균을 고정된 서비스 erase rate나 실기기 수명으로 사용',
         'why_not': '전반/후반 상태 변화와 작은 geometry·synthetic workload의 범위가 있다. 문제 존재와 해결책의 효과는 다르다.', 'status': summary['classification']},
        {'id': 'D018', 'title': 'pilot 종료 후 다음 실행 중단',
         'reason': '6회 측정과 검증·HTML 기록만 완료했다. 다음 후보는 동일 조건의 더 긴 overwrite에서 window별 수렴 확인이다.',
         'alternatives': '자동으로 warmup/budget 또는 workload를 확대',
         'why_not': '추가 실험은 별도 사용자 승인과 byte/runtime 자원 예산을 먼저 정한다.', 'status': 'awaiting-user-review'}
    ]
    for d in decisions:
        if not any(old['id'] == d['id'] for old in research['decisions']):
            research['decisions'].append(d)
    candidate = '주소 갱신을 묶는 host-side scheduling이 같은 bytes에서 GC 복사를 줄일 수 있을까? durability/latency를 지키는 해결 후보이며 아직 미실험이다.'
    if candidate not in research['new_questions']:
        research['new_questions'].append(candidate)
    with (ROOT / 'records/research.json').open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(research, ensure_ascii=False, indent=2) + '\n')
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    readme = readme.replace('Phase 1 통과 · Phase 2 승인 대기 / 미실행', 'Phase 1 통과 · Phase 2 pilot 완료 · 추가 실험 승인 대기')
    readme = readme.replace('- E0 및 Phase 2 이후 실험은 시작하지 않았습니다.',
        '- 승인된 Phase 2 pilot만 완료했습니다. 동일 70% fill·4 KiB/QD1/job1/direct·host 4.20 GiB에서\n'
        f'  sequential/random 각 3회. 평균 WAF {a["waf"]["mean"]:.4f}/{b["waf"]["mean"]:.4f}, '
        f'erase/GiB {a["erase_per_gib"]["mean"]:.3f}/{b["erase_per_gib"]["mean"]:.3f}.\n'
        '  native GC/erase와 동일 observed initial state가 확인됐습니다. 모든 VM을 종료했습니다.\n'
        '- 추가 E0 조건과 다음 Phase는 실행하지 않았습니다. '
        '[Phase 2 pilot 노트](docs/phase-02.html)와 records/phase-02-*.json에 원본·해석이 있습니다.')
    start = readme.find('Phase 2 pilot를 시작할 플랫폼 조건은 통과했습니다.')
    end = readme.find('\n## 구조', start)
    if start >= 0 and end > start:
        readme = readme[:start] + ('Phase 2 pilot의 차이는 단일 FEMU 조건의 유한 overwrite 구간에서 얻은 evidence입니다.\n'
            'steady state, 실기기 수명, 서비스 회계, LEDGER 정책 효과로 일반화하지 않습니다.\n'
            '다음 후보는 같은 설정에서 더 긴 overwrite의 window별 수렴 확인이며 아직 미승인입니다.\n') + readme[end:]
    readme = readme.replace('이 sanity에서 runtime 검증됐지만 GC stress·E0 trend·실기기 검증은 하지 않았습니다.',
        '이 sanity에서 runtime 검증됐습니다. 이후 GC와 E0 pattern 차이의 pilot는 별도 기록이며 실기기 검증은 하지 않았습니다.')
    with (ROOT / 'README.md').open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(readme)
    agents = (ROOT / 'AGENTS.md').read_text(encoding='utf-8')
    notice = ('- The six authorized Phase 2 pilot runs are COMPLETE. Do not rerun them,\n'
              '  extend overwrite/preconditioning, or enter another phase without new user approval.\n')
    if notice not in agents:
        agents = agents.replace('## Documents and evidence\n', notice + '\n## Documents and evidence\n')
    agents = agents.replace('Stop the owned VM after sanity;', 'Stop the owned VM after each run;')
    with (ROOT / 'AGENTS.md').open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(agents)
    print('Research map, preserved decision history and README updated from measured pilot data.')
