"""Record actual control findings, retaining prior studies and decisions."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name): return json.loads((ROOT/'records'/name).read_bytes())
if __name__=='__main__':
    s,b,r=load('phase-02-history-summary.json'),load('phase-02-history.json'),load('research.json')
    assert s['status']=='validated' and b['status']=='passed'
    label='선택한 두 history의 민감도가 낮음' if s['low_selected_history_sensitivity'] else 'history 영향 또는 수렴 불확실성이 남음'
    evidence='seed 42의 history control 2개 새 runs: '+label+'. 1회 조건은 보존된 archive에서 같은 horizon으로 비교했다. n=1/패턴의 기술적 비교이며 전체 초기 상태의 무관함이나 equivalence를 입증하지 않는다.'
    seq=next(c for c in s['comparisons'] if c['pattern']=='sequential')
    rand=next(c for c in s['comparisons'] if c['pattern']=='random')
    evidence+=f' 후반 random WAF 상대차={rand["relative_difference_pct"]["waf"]:+.4f}%, 두 패턴 erase/GiB 차이는 0%. 반면 sequential 첫 window WAF는 {seq["first_report_window"]["relative_difference_pct"]["waf"]:+.2f}%였다. 초기 비용과 후반 rate의 history 민감도를 구분한다.'
    r['scope']='Phase 2 pilot·긴 overwrite·작은 initial-history control 완료. 세 패턴 비교는 설계만 했다. solution 미구현, 추가 실행 승인 대기.'
    r['directions'][0]['evidence']=r['directions'][0]['evidence'].split('\nHistory control:')[0]+'\nHistory control: '+evidence
    for p in r['roadmap']:
        if p['phase']==2: p['status']='history-control-complete-three-pattern-design-only'
    for d in r['decisions']:
        if d['id']=='D021':d['status']='review-complete-history-control-authorized-see-D022'
    decisions=[
        {'id':'D022','title':'작은 history control은 3회 조건 두 runs만 실행',
         'reason':'seed 42의 각 패턴 한 run씩, 16.8 GiB/4 windows로 제한했다. 기존 1회 history run의 같은 horizon을 재사용했다. 동일 seed의 random preconditioning 세 번 외 설정은 유지했다.',
         'alternatives':'1회 조건도 rerun하거나 seed 3개와 25.2 GiB를 모두 반복',
         'why_not':'작은 control 요청에 맞춰 같은 byte window의 기존 원본을 재사용한다. n=1이라는 범위 제한을 명시한다.','status':'completed'},
        {'id':'D023','title':'Near 판정과 통계적 동등성을 구분','reason':evidence,
         'alternatives':'선택한 history 두 개의 작은 차이를 모든 초기 상태에 일반화',
         'why_not':'수렴 gate와 ±1% 기술적 tolerance는 실행 전에 동결했다. 다른 history/seed/FTL로의 일반화는 아직 열려 있다.','status':s['classification']},
        {'id':'D024','title':'주소 순서와 coverage를 구분하는 세 패턴 실험은 설계만',
         'reason':'S/P는 exact round coverage를 맞추고 P/R은 replacement/coverage 묶음을 비교한다. 검증된 offset sequence와 공통 replay 경로가 필요하다.',
         'alternatives':'바로 solution/서비스/LLM 실험 또는 이름만 permutation인 random workload 실행',
         'why_not':'현재는 메커니즘을 좁히는 단계다. generator/trace correctness를 별도 gate로 설계하고 main 실행은 사용자 승인 후다.','status':'designed-not-executed'}]
    for d in decisions:
        if not any(x['id']==d['id'] for x in r['decisions']):r['decisions'].append(d)
    (ROOT/'records/research.json').write_bytes((json.dumps(r,ensure_ascii=False,indent=2)+'\n').encode())
    agents=(ROOT/'AGENTS.md').read_text(encoding='utf-8')
    notice='\n- The two authorized three-pass history-control runs are COMPLETE. Do not rerun/extend them.\n  The next three-pattern experiment is DESIGN ONLY and must not execute without new approval.\n'
    if notice not in agents:agents=agents.replace('## Documents and evidence',notice+'\n## Documents and evidence')
    (ROOT/'AGENTS.md').write_bytes(agents.encode())
    readme=(ROOT/'README.md').read_text(encoding='utf-8')
    heading='\n## 작은 history control\n'
    if heading not in readme: readme+=heading+'\n'+evidence+'\n\n[결과와 설계](docs/phase-02.html) · [세 패턴 상세 설계](docs/THREE_PATTERN_PLAN.md). 다음 실험은 미실행입니다.\n'
    (ROOT/'README.md').write_bytes(readme.encode())
    print('History-control records and design-only boundary updated.')
