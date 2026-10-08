"""Update research history from validated longer overwrites; does not run I/O."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    return json.loads((ROOT / 'records' / name).read_text(encoding='utf-8'))

if __name__ == '__main__':
    summary, batch, research = load('phase-02-steady-summary.json'), load('phase-02-steady.json'), load('research.json')
    assert summary['status'] == 'validated' and batch['status'] == 'passed'
    a, b = summary['arms']['sequential'], summary['arms']['random']
    evidence = (f'동일 FEMU 설정과 70% fill에서 25.20 GiB overwrite를 각 3회 실행했다. '
                f'마지막 3 windows 평균 WAF={a["waf"]["mean"]:.6f}/{b["waf"]["mean"]:.6f}, '
                f'erase/GiB={a["erase_per_gib"]["mean"]:.3f}/{b["erase_per_gib"]["mean"]:.3f}. '
                f'6회 모두 수렴 기준 통과={summary["all_replicates_converged"]}. '
                '유한 관측 구간과 단일 geometry의 FEMU 모델 근거이며 실기기나 서비스 정책 효과는 미검증이다.')
    research['scope'] = 'Phase 1, Phase 2 pilot와 승인된 동일 설정의 긴 overwrite 확인만 완료했다. 해결 방향은 아직 미정이며 다음 실행은 승인 대기다.'
    for phase in research['roadmap']:
        if phase['phase'] == 2:
            phase['status'] = 'steady-check-complete-next-experiment-not-authorized'
    research['directions'][0]['evidence'] = research['directions'][0]['evidence'].split('\n추가 관측:')[0] + '\n추가 관측: ' + evidence
    for decision in research['decisions']:
        if decision['id'] == 'D018':
            decision['status'] = 'review-complete-long-overwrite-authorized-see-D019'
    additions = [
        {'id': 'D019', 'title': '동일 설정의 긴 overwrite와 수렴 기준을 실행 전에 동결',
         'reason': '기존 2.10 GiB subwindow를 12번 이어 쓰고 두 개씩 4.20 GiB report window로 묶었다. 마지막 3 windows의 상대 범위 ≤1%, 상대 기울기 ≤0.5%/window를 두 metric·모든 replicate에 요구했다.',
         'alternatives': '결과를 보고 budget·설정·seed를 바꾸거나 window를 선택',
         'why_not': '초기 transient와 지속되는 패턴 차이를 구분하려면 비교 프로토콜과 판정 기준을 고정해야 한다.', 'status': 'completed'},
        {'id': 'D020', 'title': '짧은 pilot와 긴 구간의 관측을 구분해 보존',
         'reason': evidence + ' 첫 report window native delta는 기존 pilot 6회와 모두 일치했다.',
         'alternatives': '기존 59.5%를 steady-state 차이라고 그대로 사용',
         'why_not': '초기 혼합 배치를 정리하는 비용과 이후 rate가 다를 수 있다. 수렴은 유한 길이의 운영상 기준이며 엄밀한 stationarity 증명은 아니다.', 'status': summary['classification']},
        {'id': 'D021', 'title': '긴 확인 종료 후 다음 실험 중단',
         'reason': '같은 두 패턴·3회씩만 실행하고 모든 소유 VM을 종료했다. 다음 후보는 같은 조건에서 preconditioning 이력만 바꾸는 확인이다.' if summary['all_replicates_converged'] else '고정 budget의 결과를 보존하고 모든 소유 VM을 종료했다. 다음 후보는 동일 설정의 더 긴 budget 확인이다.',
         'alternatives': 'fill/geometry/서비스/정책 실험으로 자동 진입',
         'why_not': '추가 조건은 사용자 판단과 별도 승인이 필요하다.', 'status': 'awaiting-user-review'}]
    for decision in additions:
        if not any(d['id'] == decision['id'] for d in research['decisions']):
            research['decisions'].append(decision)
    (ROOT / 'records/research.json').write_text(json.dumps(research, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    agents = (ROOT / 'AGENTS.md').read_text(encoding='utf-8')
    agents = agents.replace('The user now authorizes longer overwrites of the same two patterns at the same fill.',
                            'The six longer same-profile overwrite runs are also COMPLETE. Do not rerun or extend them.')
    (ROOT / 'AGENTS.md').write_text(agents, encoding='utf-8', newline='\n')
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    readme = readme.replace('Phase 1 통과 · Phase 2 pilot 완료 · 추가 실험 승인 대기',
                            'Phase 1 통과 · Phase 2 pilot/긴 overwrite 확인 완료 · 추가 실험 승인 대기')
    readme = readme.replace('다음 후보는 같은 설정에서 더 긴 overwrite의 window별 수렴 확인이며 아직 미승인입니다.',
                            '이후 승인된 긴 overwrite의 window별 수렴 확인도 완료했습니다. 다음 실험은 승인 대기입니다.')
    marker = '\n## 긴 overwrite 추가 확인\n'
    if marker not in readme:
        readme += marker + '\n' + evidence + '\n\n[36 windows와 수렴 판정](docs/phase-02.html). 원본: records/phase-02-steady*.json. 추가 실험은 실행하지 않았습니다.\n'
    (ROOT / 'README.md').write_text(readme, encoding='utf-8', newline='\n')
    print('Updated research and decisions; next experiments remain unauthorized.')
