"""Publish measured screening evidence into research records and Korean report."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.kv_notes import report

def main():
    summary=json.loads((ROOT/'records/kv-screen-summary.json').read_text())
    assert summary['status']=='validated' and summary['run_count']==12
    (ROOT/'research/kv_reuse_screening_report.md').write_text(report(summary),encoding='utf-8')
    p=ROOT/'records/research.json'; r=json.loads(p.read_text())
    r['scope']='기존 FEMU pilot/steady/history 보존. KV full-state audit·smoke·12 synthetic screening 완료. Native pop-on-lookup 지배로 future-reuse screening 부적합; chunk paired replay 설계만, solution 미구현.'
    r['question']='저장·재사용 경계와 memory/storage 계층의 상호작용이 기존 효율 지표나 시스템 선택을 뒤집는 실제 조건이 있는가?'
    for d in r['directions']:
        if 'KV' in d['name']:
            d['evidence']='2026-10-12: full-state 12 synthetic runs 모두 disk saved tokens=0. 252 disk reads가 resident보다 낫지 않아 복원 없이 pop됐다. Serialized record의 scores 비중 약 96–98%. Chunk 기전/현실 workload/physical saving은 미검증.'
            d['objection']='높은 horizon-unused가 retrieval/serialization 구현 특성에 지배될 수 있다. 실제 trace, 적합한 chunk backend, 단순 tuning/batching과 동등한 recovery contract를 먼저 확인해야 한다.'
    decisions=[
        {'id':'D025','title':'새 연구 문제 후보를 위한 full-state screening','reason':'사용자 승인으로 기존 FEMU 결과와 독립적인 audit·smoke·12 runs를 수행했다. 모델/코드/config를 pin하고 서로 다른 synthetic fixture와 동일 trace의 paired chunk 설계를 사용한다.','alternatives':'즉시 controller나 FEMU physical-cost 평가 구현','why_not':'좋은 문제와 측정 가능성을 먼저 확인한다.','status':'completed-screening-only'},
        {'id':'D026','title':'미사용 100%를 KV/chunk 연구 GO로 해석하지 않는다','reason':'12 runs의 disk reuse는 0이고 252 lookups 모두 resident prefix보다 낫지 않아 pop 후 복원되지 않았다. Append disk-reuse positive baseline도 실패했다. Scores serialization 비중이 높아 file bytes를 KV bytes로 부를 수 없다.','alternatives':'20% screening threshold 초과만으로 새로운 문제 발견 선언','why_not':'backend/fixture-specific retrieval semantics가 지배한다. 현실적 발생률과 novelty는 보류한다.','status':'unsuitable-backend-fixture-for-general-screening'},
        {'id':'D027','title':'chunk와 cross-layer mismatch는 다음 검증 후보','reason':'같은 기록 trace의 LCP와 chunk 64/128/256/512를 paired replay하는 설계만 남겼다. Native availability와 retained-object potential upper bound를 구분한다.','alternatives':'full-state 관측을 fixed chunk 원인으로 표현하거나 새로운 policy 구현','why_not':'actual chunk key, partial tail, dedup, batching flush 및 recovery 조건을 아직 측정하지 않았다.','status':'designed-not-executed'}]
    for d in decisions:
        if not any(old['id']==d['id'] for old in r['decisions']):r['decisions'].append(d)
    r['kv_screening']={'status':'runtime-complete-research-go-undetermined','chunk_replay':'design-only','summary':'records/kv-screen-summary.json'}
    p.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    audit=ROOT/'research/kv_reuse_audit.md'
    if '## Runtime 확인 결과' not in audit.read_text(encoding='utf-8'):
        with audit.open('a',encoding='utf-8') as f:
            f.write('\n## Runtime 확인 결과\n\nSmoke는 observer/native 복원의 출력과 첫 logits를 정확히 일치시켰다.\n부분 복원 vs cold는 출력과 logits가 달라 backend numerical equivalence는 미확인이다.\n12 screening runs 모두 disk reuse=0이었다. 252 read가 resident보다 나은 prefix를\n제공하지 않아 pop 후 복원되지 않았다. 따라서 이 fixture에서 append-only positive\nbaseline도 실패했다. 일반적인 KV reuse 낭비나 fixed chunk 기전을 입증하지 않는다.\nScores array serialization이 record bytes의 약 96–98%를 차지했다.\n')
    print('Research records and report updated from measured evidence.')

if __name__=='__main__': main()
