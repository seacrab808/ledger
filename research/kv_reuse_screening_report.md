# KV reuse screening report — 2026-10-12

## 1. 실험 환경

승인된 연구실 physical Linux에서 CPU-only llama-cpp-python 0.3.36과 pinned
Qwen2.5 0.5B Q4_K_M을 사용했다. 생성/prefill 모두 2 threads, 2 CPU affinity,
nice 10, context 2048, 생성 upper bound 32, 단일 LLM process로 실행했다.
12 screening runs의 최대 RSS는 0.955 GiB였다. 시스템 package/권한/service
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

|Workload|horizon 미사용 token %|한 번이라도 쓰인 record bytes %|disk 절약 tokens|serialized MiB|scores 비중 %|
|---|---:|---:|---:|---:|---:|
|append|100.00 ± 0.00|0.00 ± 0.00|0.00 ± 0.00|1714.84 ± 9.84|96.16 ± 0.02|
|retry|100.00 ± 0.00|0.00 ± 0.00|0.00 ± 0.00|1704.82 ± 9.25|96.69 ± 0.03|
|edit|100.00 ± 0.00|0.00 ± 0.00|0.00 ± 0.00|1689.77 ± 15.70|97.26 ± 0.02|
|session_end|100.00 ± 0.00|0.00 ± 0.00|0.00 ± 0.00|950.13 ± 19.01|97.60 ± 0.02|

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
첫 token logits 상대 RMS=0.034884,
max absolute difference=0.513166; 같은 native
복원 vs observer의 logits 차이는 0.000000였다.
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
