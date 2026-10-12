"""Render the explanation layer from measured KV records, with explicit boundaries."""
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def report(summary):
    diagnostic=json.loads((ROOT/'results/kv_lifecycle/smoke/numerical-diagnostic.json').read_text())
    rows=[]
    for a in summary['aggregates']:
        m=a['metrics']
        def f(k,scale=1): return f"{m[k]['mean']*scale:.2f} ± {m[k]['sample_sd']*scale:.2f}"
        rows.append(f"|{a['pattern']}|{f('horizon_unused_token_ratio',100)}|{f('record_ever_used_ratio',100)}|{f('disk_saved_prefill_tokens')}|{f('persisted_record_bytes',1/1024**2)}|{f('scores_array_fraction_of_record_bytes',100)}|")
    table='\n'.join(['|Workload|horizon 미사용 token %|한 번이라도 쓰인 record bytes %|disk 절약 tokens|serialized MiB|scores 비중 %|',
                      '|---|---:|---:|---:|---:|---:|',*rows])
    peak=max(r['peak_rss_bytes'] for r in summary['rows'])/1024**3
    return f'''# KV reuse screening report — 2026-10-12

## 1. 실험 환경

승인된 연구실 physical Linux에서 CPU-only llama-cpp-python 0.3.36과 pinned
Qwen2.5 0.5B Q4_K_M을 사용했다. 생성/prefill 모두 2 threads, 2 CPU affinity,
nice 10, context 2048, 생성 upper bound 32, 단일 LLM process로 실행했다.
12 screening runs의 최대 RSS는 {peak:.3f} GiB였다. 시스템 package/권한/service
설정 변경, VM/FEMU 실행은 없었다. 원본 FEMU 결과는 보존했다.
단, 최초 venv bootstrap에는 project-local TMPDIR/HOME을 실제 parent 환경에
적용하기 전 EnvBuilder를 호출한 결함이 있었다. Ensurepip의 일시 temp가 외부에
생겼을 가능성을 배제할 수 없으며 당시 temp 경로는 기록하지 않았다. 이후 build와
실험 child에는 project-local 환경을 적용했다. 재현 script는 bootstrap 이전에도
환경을 적용하도록 수정했다. 모든 임시 쓰기가 ledger 안이었다고 주장하지 않는다.

## 2. 정확히 무엇을 측정했는지

native DiskCache의 serialized state-record payload size, native state size,
scores array size, 저장 버전별 token 수, lookup/load/실제 prompt eval 및 저장 후
재사용을 측정했다. SQLite metadata/WAL, OS block bytes, 순수 KV byte layout,
NAND writes/erase는 미측정이다. filename size를 총 storage traffic이라고 부르지 않는다.

token instance utilization은 고유 재사용 token 구간 / 저장 token 구간이다.
반복 reuse count와 disk saved-prefill-token 합계는 별도이다. record-ever-used bytes
ratio는 **부분 hit라도 전체 record를 한 번 사용한 것으로 분류하는 거친 metric**이며,
fine-grained KV byte utilization이 아니다. 생성 직전 eval은 actual execution observer로
집계했다. lookup/pop과 load_state와 REUSED를 구분했다.

## 3. Workload

실제 trace가 없어 네 종류의 controlled synthetic completion fixture를 사용했다.
User/Assistant 문자열을 명시적으로 구성했으며 실제 chat template workload나 agent
tool trace가 아니다. append/retry/edit는 네 session을 round-robin으로 각 6번 요청했다.
session_end는 8 session 중 4개는 한 번, 4개는 세 번 요청했다. 각 종류는 seed
42/43/44의 서로 다른 topics/details/길이를 사용한 3개 fixture runs이다.
3회 SD는 fixture 간 변동이며 실제 사용자 모집단의 confidence interval이 아니다.
종류 간 fixture와 요청 수가 달라 표의 차이를 edit 하나의 순수 causal effect로 읽으면 안 된다.
같은 실측 token trace를 다음 chunk 분석의 모든 C에 재사용하도록 설계했다.

## 4. 결과

아래는 평균 ± sample SD, n=3이며 모든 값은 runtime 기록에서 계산했다.

{table}

핵심 관측은 **screening 12 runs의 disk-backed saved prefill tokens가 모두 0**이라는
것이다. Disk read 252회 중 load_state 0회였다. 252회 모두 관측 source state LCP가
resident LCP 이하였으며, native code는 먼저 record를 pop한 뒤 그 경우 복원을 하지
않는다. 해당 record가 다음 같은 session 요청까지 남지 않았다. 이는 선택한
interleaved fixture와 backend retrieval semantics의 상호작용이며 모든 KV backend의 성질이 아니다.
smoke에서 explicit cold restore가 실제 계산을 생략함은 별도로 확인했다.

12개 seed-level 결과는 results/kv_lifecycle/summary.csv, 객체 및 request는 각 run.json,
event는 각 events.jsonl이다. 총 bytes와 고유 semantic KV 양을 혼합하지 않는다.

## 5. dead persistence 비율

위 미사용 비율은 **미리 정한 유한 horizon의 unused persisted token instances**다.
session 종료 후 복구/resume 가치까지 영구히 사라졌다는 dead 비율은 아니다.
고유 객체 version 내부에서는 동일 prefix를 여러 번 사용해도 union에 한 번만 포함한다.
같은 prefix의 재저장은 실제 write-instance이므로 분모에 각각 들어간다.
pure-KV reused bytes는 format mapping이 없어 null로 남겼다.

## 6. 주요 원인

Screening을 지배한 것은 native pop-on-lookup 후 미복원이며, 마지막 record는 horizon
종료 후 재방문되지 않았다. partial prefix 뒤의 미사용 tail은 smoke에서만 관측했고
screening의 edit/retry 원인으로 귀속하지 않는다. Full-state에 포함된 scores array는
source에서 직접 포함됨을 확인했고
크기를 측정했다. 이 overhead를 KV lifecycle 낭비나 chunk waste라고 부르지 않는다.
Edit/retry는 입력 행동이고 backend가 명시적 invalidation event를 제공하지 않으므로
그 행동만으로 원인을 확정하지 않는다. 폐기된 record의 disposition과 token 미사용
원인을 같은 것으로 취급하지 않는다. CHUNK_BOUNDARY_WASTE는 실측되지 않았다.

## 7. Measurement limitation

smoke의 계측 전후 cold 출력, 동일 prompt 복원 출력, native 부분 복원 출력과 logits
일치 및 실제 prompt eval 감소가 통과했다. 그러나 부분 복원 vs cold 생성문은 달랐다.
첫 token logits 상대 RMS={diagnostic['cold_vs_restored_first_logit_relative_rms']:.6f},
max absolute difference={diagnostic['cold_vs_restored_first_logit_max_abs']:.6f}; 같은 native
복원 vs observer의 logits 차이는 {diagnostic['native_vs_observed_first_logit_max_abs']:.6f}였다.
계측은 기존 실행을 보존하지만 backend의 cold/partial numerical correctness가
입증됐다는 뜻은 아니다. 차이의 원인은 아직 확인하지 않았으며 무해한 roundoff라고
단정하지 않는다. 다른 모델/dtype/batch geometry로 후속 검증할 수 있지만 이번에는
변경하지 않았다. 속도 개선이나 생성 품질 보존 주장을 하지 않는다.

최초 prefill-thread 기본값 oversubscription, fresh-cache guard, 자원 모니터와 cache
삭제의 race를 기록하고 수정했다. 실패 attempt를 보존하고 성공한 screening을
반복하거나 덮어쓰지 않았다. 측정 overhead 때문에 request runtime은 정책 성능으로
사용하지 않는다. RAM native reuse와 disk-backed reuse도 별도 집계했다.

## 8. GO / NO-GO 판단

**이 backend/fixture의 future-reuse screening은 부적합이며, 현실적 연구 문제/novel
cross-layer mismatch 판정은 보류**한다. Append-only에서 기대한 disk 재사용 positive
baseline도 통과하지 못했다. 100% 미사용은 일반적인 edit/retry/chunk 낭비의 증거가
아니며 pop-on-lookup 조건에 지배됐다. 종료 fixture도 자체적으로 미사용을 만든다.
20%/30% screening 숫자를 넘어도 실제 workload
prevalence, fixed chunk 기전, 해결 필요성 또는 novelty가 입증되지 않는다.
특정 serialization overhead가 크다면 implementation-specific issue를 먼저 분리해야 한다.

## 9. 단순 baseline으로 해결되는지

**아직 미검증**이다. 현재는 full-state이고 chunk size/batching baseline을 runtime에
추가하지 않았다. 64/128/256/512 paired trace replay는 research/kv_chunk_replay_plan.md의
설계로 남겼다. 작은 C에서 boundary loss가 사라지면 chunk tuning으로 설명될 수 있다.
batching 효과는 token trace만으로 판정할 수 없고 flush 시점, I/O, recovery contract가
필요하다. state serialization overhead가 주원인이면 controller보다 기존 구현 점검이 먼저다.

## 10. 다음 실험 하나

동일한 기록 token trace의 64/128/256/512 **paired analytical replay**로 oracle LCP,
chunk-compatible reuse, 미사용 저장량, boundary 재계산, 미저장 tail을 분리한다.
그 분석 뒤 실제 chunk backend에서 partial-chunk 처리와 결과를 cross-check한다.
이는 제안이며 이번 실행은 하지 않았다.

분석 기반 시스템 설계 논문 후보로 발전하려면 현실적인 서로 다른 trace에서 현상이
반복되고 간단한 tuning/batching 후에도 남으며, 동일 SLO/recovery 조건에서 정책의
선택 역전이 있어야 한다. 예: logical saving이 physical programs/erase per saved-token을
오히려 늘리는 경우. 그때 block I/O/FEMU 단계가 유효하다. 현재 그런 역전을 관측했다고
주장하지 않는다. 새 policy/controller는 구현하지 않았다.
'''

def add_notes(pages,summary,helpers):
    e,table,section,link=helpers
    rows=[]
    for a in summary['aggregates']:
        m=a['metrics']
        def f(k,scale=1):return f"{m[k]['mean']*scale:.2f} ± {m[k]['sample_sd']*scale:.2f}"
        rows.append([e(a['pattern']),f('horizon_unused_token_ratio',100)+'%',f('disk_saved_prefill_tokens'),f('persisted_record_bytes',1/1024**2),f('scores_array_fraction_of_record_bytes',100)+'%'])
    body=section('먼저 무엇을 확인했나','<p>실제 KV 저장 구현이 없어서 pinned 공개 backend를 준비했다. 계측이 원래 native 복원 동작을 보존하고 실제 prompt 계산을 줄이는지 smoke로 확인한 뒤 4종 synthetic workload를 각 3회 실행했다. FEMU와 기존 결과는 수정하지 않았다.</p>')
    body+=section('관측 · n=3 평균 ± sample SD',table(['fixture','horizon 미사용 token','disk 절약 tokens','serialized MiB','scores array 비중'],rows)+'<p>저장 버전별 token 구간을 분모로 사용한다. 파일 bytes는 순수 KV가 아니며 NAND 쓰기도 아니다. 아직 살아 있거나 미래 복구에 쓸 수 있는 데이터를 영구적인 dead로 단정하지 않는다.</p>')
    for name,title in [('01-token-use.svg','고유 token 구간의 사용과 horizon 미사용'),('02-unused-disposition.svg','관측한 객체 처분 · causal 원인과 다름'),('03-benefit-vs-bytes.svg','실제 prefill 절약과 serialized record bytes')]:
        svg=(ROOT/'results/kv_lifecycle/figures'/name).read_text()
        svg=svg[svg.index('<svg'):]
        svg=re.sub(r'<style\b[^>]*>.*?</style>','',svg,flags=re.S)
        ids=re.findall(r'id="([^"]+)"',svg)
        prefix=name[:2]+'-'
        for identifier in ids:
            svg=svg.replace('id="'+identifier+'"','id="'+prefix+identifier+'"')
            svg=svg.replace('href="#'+identifier+'"','href="#'+prefix+identifier+'"')
            svg=svg.replace('url(#'+identifier+')','url(#'+prefix+identifier+')')
        svg=svg.replace('<svg ','<svg style="max-width:100%;height:auto;stroke-linejoin:round;stroke-linecap:butt" ',1)
        svg='\n'.join(line.rstrip() for line in svg.splitlines())
        body+=section(title,'<div class="scroll">'+svg+'</div>')
    lookups=summary['lookup_summary']
    body+=section('핵심 관측 · 높은 미사용 비율을 GO로 읽지 않는다',f'<p>12 screening runs의 disk 절약 tokens는 모두 0이다. Disk read {lookups["disk_reads"]}회 중 load_state {lookups["restored"]}회였고, {lookups["not_restored_and_disk_lcp_not_better_than_resident"]}회 모두 disk prefix가 resident prefix보다 길지 않았다. 먼저 pop한 record를 복원하지 않아 다음 같은 session까지 보존하지 못했다. Append-only disk 재사용 baseline도 실패했으므로 이 backend/fixture는 일반적인 future-reuse screening에 부적합하다.</p>')
    body+=section('해석 · 아직 논문 문제를 확정하지 않는다','<p>미사용 100%는 일반적인 KV/chunk 문제의 증거가 아니다. 선택한 fixture의 native pop-on-lookup과 scores serialization이 지배적이다. Full-state 결과는 fixed chunk mismatch의 증거가 아니다. 실제 trace와 recovery 요구를 확인하지 않아 현실적 GO/NO-GO는 보류한다.</p>')
    body+=section('예상 밖의 결과와 correctness 범위','<p>부분 복원은 계측 없는 native 실행과 출력·logits가 정확히 같았지만 cold 실행과는 달랐다. 계측 correctness와 backend numerical equivalence를 구분한다. prefill도 2 threads로 명시했고, 실패 cache와 자원 모니터 race 이력을 보존했다.</p>')
    replay_complete=(ROOT/'records/kv-chunk-replay.json').exists()
    body+=section('Full-state 종료 시점의 다음 설계 · 이후 실행 결과는 아래에 추가' if replay_complete else '다음 설계 · 실행하지 않음','<p>같은 trace를 chunk 64/128/256/512에 paired replay한다. LCP의 oracle reuse, chunk boundary loss, 미저장 tail, 마지막 token 재계산을 분리한다. 이 문단은 full-state 종료 시점의 설계 기록이다. 실제 chunk backend와 batching 효과는 아직 측정하지 않았다. 새 policy/controller는 만들지 않았다.</p>'+link('../research/kv_chunk_replay_plan.md','paired replay 상세 설계'))
    body+=section('원본·audit·보고서','<p>'+link('../results/kv_lifecycle/summary.csv','seed별 CSV')+' · '+link('../results/kv_lifecycle/reason_breakdown.csv','disposition CSV')+' · '+link('../research/kv_reuse_audit.md','source audit')+' · '+link('../research/kv_reuse_screening_report.md','전체 보고서')+'</p>')
    pages['kv-screen.html']=('KV persistence · 좋은 문제를 찾는 screening','Full-state 실측과 chunk 분석 설계를 구분한다. 실제 conversation/agent trace가 없는 controlled synthetic evidence이다.',body)
    replay_status='기록 trace의 chunk paired replay도 추가 완료했다.' if replay_complete else 'Chunk 64/128/256/512 replay는 설계만 했다.'
    note=section('새 연구 탐색 · KV lifecycle screening','<p>12개 controlled full-state runs와 smoke가 완료됐다. Disk saved tokens는 모두 0이고 native pop-on-lookup이 지배했다. '+replay_status+' 현실적 문제 발생률과 cross-layer novelty는 보류한다.</p>'+link('kv-screen.html','KV screening 결과·한계'))
    for name in ('index.html','research-map.html','experiment-log.html','decision-log.html'):
        title,lead,body=pages[name]; pages[name]=(title,lead,body+note)
