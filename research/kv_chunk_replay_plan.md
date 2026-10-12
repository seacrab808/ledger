# 같은 trace의 paired token replay / chunk 분석 설계

2026-10-12 후속 승인으로 아래 설계의 offline paired replay를 실행했다.
[추가 실행 결과](kv_chunk_replay_report.md)를 읽어 주세요. 아래는 승인 전 설계 이력이며
실제 chunk backend·batching·FEMU는 실행하지 않았다.

이 문서는 설계이며 측정 결과나 새 policy 구현이 아니다. 12개 full-state
screening runs와 chunk analytical replay는 다른 evidence이다. Synthetic trace는
실제 agent 행동의 분포를 대표하지 않는다.

## 연구 목적

단순히 utilization이 낮다는 숫자보다, 저장 단위·재사용 경계·resident memory·
복구 요구·block I/O 사이에서 기존 의사결정 지표가 잘못된 선택을 만드는지 찾는다.
full-state backend에는 fixed chunk가 없으므로 그 결과로 chunk 원인을 입증하지 않는다.

## 입력과 paired 비교

- runtime에서 기록한 **실제 tokenizer의 prompt_token_ids와 persisted state token_ids**를 사용한다.
  문자 prefix나 턴 수로 token prefix를 대신하지 않는다.
- append/retry/edit/session_end는 서로 다른 topic fixture를 사용하고 seed별 detail·길이를 다르게 한다.
  같은 trace를 각 chunk size 64/128/256/512에 그대로 재생한다. 정책별로 응답을 새로 생성하지 않는다.
- model/tokenizer/template/format revision, session ID, object version, request 순서,
  persistence 시점, horizon, cache 용량·eviction 조건을 함께 고정한다.
- analytic reference는 우선 session 격리, 용량 무제한, 동기 저장, TTL 없음,
  동일한 completion 종료 시점 저장으로 정의한다. 이 idealized model과 native pop-on-read
  또는 실제 LMCache 정책을 동일한 구현이라고 표현하지 않는다.
- 이번 full-state screening에서는 pop-on-lookup 때문에 disk 재사용이 0이었다.
  우선 native lifecycle을 그대로 재생하는 reference에서는 그 결과를 재현해야 한다.
  저장 객체를 계속 가용하다고 두는 oracle은 **potential reuse upper bound**이며
  실제 backend의 측정치가 아니다. 이 가용성 차이를 chunk size 효과에 섞지 않는다.
- 이전 **모든 eligible 저장 객체** 중 최대 longest common token prefix를 구한다.
  직전 요청과의 LCP만 사용하는 분석은 interleaved session의 재방문을 놓친다.
  chunk key는 model identity 및 전체 선행 prefix를 포함한다. 같은 offset/token 조각만
  같다고 causal attention KV가 호환된다고 판단하지 않는다.

## 분리할 네 양

1. Token-level oracle의 재사용 가능 token 수: 실제 저장·가용 객체에 대한 LCP.
2. 고정 chunk 때문에 재사용하지 못하는 token 수: oracle과 chunk reference 차이.
3. 저장됐지만 관측 종료까지 한 번도 사용되지 않은 token/byte 구간.
4. 마지막 token logits refresh, eviction, context invalidation, 저장되지 않은 tail,
   session 종료 때문에 필요한 계산. chunk-boundary recomputation과 분리한다.

## 계산 모델 (실제 chunk backend 검증 전 분석 가정)

완전한 chunk만 저장·재사용할 수 있는 reference:

- 저장 token 수 N에서 full chunks는 floor(N/C)*C, 미저장 tail은 N % C.
- eligible source와 query의 공통 prefix가 L이면 reusable chunks는 floor(L/C)*C.
- prompt 길이가 P일 때 token oracle savings는 min(L,P-1), chunk savings는
  min(floor(L/C)*C,P-1). 마지막 token을 재계산하는 복원 경로라는 가정을 명시한다.
- boundary recomputation = oracle savings - chunk savings (tokens/request).
- 미저장 tail은 저장 후 미사용량에 넣지 않는다. 그것은 별도의 저장 coverage 차이다.
- partial tail을 padding하여 저장하는 backend는 별도 reference다. payload와 padding을
  구분하고 partial-chunk reuse 허용 여부를 먼저 source audit한다. 위 식을 그대로 적용하지 않는다.
- 어느 모델도 measured FL/FEMU/LMCache threshold나 실제 latency로 표현하지 않는다.

예를 들어 L=257, P=400인 경우 C=256에서는 oracle 257 tokens,
chunk 256 tokens이고 boundary loss는 1 token이다. L=256,P=256인 복원은
두 방식 모두 255 tokens를 생략하며, 마지막 1 token 재계산은 boundary loss가 아니다.

## Unique 사용량과 반복 benefit

- physical 저장 write-instance identity는 (object_id, version, byte interval)이다.
  같은 prefix를 다른 snapshot에 다시 쓰면 실제 반복 저장이므로 별도 instance다.
- unique useful bytes = 각 저장 instance에서 한 번이라도 사용된 byte interval의 union.
  total persisted bytes도 같은 종류의 payload bytes여야 한다. 둘의 ratio는 [0,1].
- semantic deduplicated token identity는 model/template와 전체 token prefix hash에 기반한다.
  이 metric의 분자와 분모는 모두 deduplicated token 수이며 write-instance 효율과 별도다.
- reuse count와 saved-prefill-tokens는 매 재사용의 benefit을 합산한다. 이 값은
  저장 token 수보다 클 수 있다. saved tokens / stored tokens를 bounded utilization으로 부르지 않는다.
- token/byte 환산은 일정한 KV layout일 때만 모델 dtype·layer/head dimensions로 계산한다.
  압축, sparse state, metadata, padding이 있으면 실측 format mapping이 필요하다.
- full-state runtime의 serialized record bytes와 modeled KV payload bytes를 합치지 않는다.

## horizon과 원인 분류

폐기/eviction, 명시적 semantic invalidation, 종료 후 재방문 없음, 아직 살아 있는
객체의 right censoring을 구분한다. edit/retry가 발생했다고 전체 객체를 무효화하지 않는다.
edit된 branch가 나중에 다시 사용될 수도 있다. 충돌 없는 최초 확인 원인을 primary로,
부가 행동은 secondary tags로 기록하며 UNKNOWN을 허용한다.

## 결과 표·그림 (향후 replay 실행 시)

각 seed/trace/C의 oracle-reusable, chunk-reusable, boundary recomputation,
stored-useful, horizon-unused, censored, unpersisted-tail, repeated reuse count를 저장한다.
같은 trace의 C 간 paired deltas를 제시하고 서로 다른 fixture나 길이의 raw totals를
효율 ratio처럼 비교하지 않는다. 실제 trace가 없으면 현실 발생률이나 CCGrid novelty가
입증됐다고 주장하지 않는다. C와 무관한 마지막 save 효과도 별도 표시한다.

## 기존 backend와 다음 검증의 경계

|full-state에서 관찰 가능|chunk backend에서 확인할 항목|
|---|---|
|저장/조회/복원/실제 prompt eval|실제 chunk key와 partial-tail 처리|
|resident vs disk 재사용|부분 chunk를 truncate해서 재사용할 수 있는지|
|state 및 scores overhead|dedup, admission, eviction, shared prefixes|
|pop-on-read와 저장 버전 중복|async save 완료 전 취소, batching flush 시점|
|유한 horizon의 미사용|block write/metadata/fsync와 실제 prefill benefit|

현재는 작은 chunk나 batching을 runtime에 구현하지 않는다. chunk 분석도 설계 상태다.
크기 조정이 boundary loss를 거의 없애면 해당 원인은 단순 tuning 후보이며 독립
system contribution으로는 약하다. batching의 효과는 이 token 분석만으로 측정할 수 없다.
flush 지연으로 생기는 reuse miss·crash recovery contract까지 실제 backend로 검증해야 한다.

## novel cross-layer mismatch로 발전하려면

서로 다른 현실적인 trace에서 현상이 반복되고, 단순 chunk tuning/batching 이후에도
남으며, 다음과 같은 구체적인 선택 역전이 동일 SLO·recovery contract에서 보여야 한다.
예: application persisted bytes는 감소하지만 작은 I/O/metadata/GC 때문에 physical
programs 또는 erase per saved-prefill-token은 증가한다. 또는 높은 hit rate가 실제
prefill 절약과 durability 비용을 설명하지 못한다. 이는 다음 단계 후보이며 현재 관측이 아니다.
기존 FEMU의 sequential/random WAF 차이를 이 역전의 결과로 재사용하지 않는다.
