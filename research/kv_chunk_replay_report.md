# Paired chunk replay 결과 — 2026-10-12

## 무엇을 실행했나

12개 기록 synthetic trace, 264 requests의 token 배열과 저장 version을 읽어
64/128/256/512를 같은 입력으로 offline replay했다. 새 모델 생성·backend 변경·
policy/controller·FEMU·서버 실행은 없다. 분석 code/config/input hashes와 timestamps는
records/kv-chunk-replay.json에 있다. 원본 38 artifact hashes를 먼저 검증했다.

## 실제 token LCP 분포

같은 session의 **엄격히 이전** 저장 상태 전부에 대해 LCP 최대값을 구했다.
동률이면 가장 최근 snapshot을 사용하고 C를 바꿔도 source 선택을 고정했다.
최초 60 requests는 해당 session의 저장 상태가 없어 LCP=0이다. 후속 204 requests의 분포:

|Workload|후속 요청 수|LCP min / p50 / p90 / p95 / max|
|---|---:|---|
|append|60|36.0 / 170.0 / 298.1 / 302.0 / 307.0|
|retry|60|36.0 / 168.5 / 233.1 / 235.1 / 238.0|
|edit|60|11.0 / 96.0 / 160.1 / 164.0 / 165.0|
|session_end|24|37.0 / 73.5 / 110.0 / 110.0 / 110.0|
|all|204|11.0 / 106.0 / 234.7 / 294.0 / 307.0|


이 LCP는 실제 token 배열에서 계산한 값이지만 **저장 객체가 계속 남는다는 가정** 아래의
potential이다. Native pop-on-lookup으로 실제 가용했던 객체의 LCP와 다르다.
Prompt 전체가 일치한 12건의 마지막 logits refresh를 oracle에서 제외해 총 상한은
25,507 tokens다. 저장 상태 최대 길이는 399 tokens다. 이는 짧은 synthetic fixture다.

## 분석 가정과 단위

same-session retained snapshots, 무제한 용량, 동기 저장, 완전한 chunk만 저장·matching,
partial tail 저장 없음, dedup/padding 없음이다. 새로운 backend 정책을 구현한 것이 아니다.
Native lifecycle replay는 원래 lookup/pop/resident comparison을 유지했으며 모든 C에서
disk reuse=0을 재현했다. 가용성 문제가 chunk 크기 때문에 해결된 것으로 표현하지 않는다.

L=실제 LCP, P=prompt 길이, N=source snapshot 길이이면:
- token oracle O=min(L,P-1)
- 저장 coverage 상한 V=min(L,floor(N/C)*C,P-1)
- chunk reuse R=min(floor(L/C)*C,P-1)
- 미저장 tail 재계산=O-V, 저장된 chunk 내부 경계 재계산=V-R
- 총 추가 재계산=O-R; 마지막 logits refresh는 이미 oracle에 포함한 별도 비용

모든 양은 tokens다. 저장 version별 unique 사용 구간의 union과 반복 reuse events를
분리했다. 같은 prefix의 재저장은 write-instance 분모에 각각 들어간다. Tokens/tokens
utilization만 계산하고 full-state serialized bytes를 chunk KV bytes로 환산하지 않았다.

## Paired 결과

|Chunk|가능 reuse tokens|총 추가 계산|경계 손실|미저장 tail 손실|상한 대비 총 손실|
|---|---:|---:|---:|---:|---:|
|64|17,664|7,843|7,424|419|30.75%|
|128|12,288|13,219|8,127|5,092|51.82%|
|256|3,072|22,435|5,615|16,820|87.96%|
|512|0|25,507|0|25,507|100.00%|

합계는 각 trace의 paired 결과를 합친 기술적 요약이다. 실제 workload 발생률로
가중한 모집단 추정이 아니다. Workload별 세 fixture의 mean ± sample SD:

|Workload|Chunk|총 손실 % 평균 ± sample SD|
|---|---:|---:|
|append|64|24.76 ± 1.24|
|append|128|39.81 ± 0.99|
|append|256|69.90 ± 0.49|
|append|512|100.00 ± 0.00|
|retry|64|28.45 ± 0.80|
|retry|128|46.34 ± 0.60|
|retry|256|100.00 ± 0.00|
|retry|512|100.00 ± 0.00|
|edit|64|37.85 ± 2.02|
|edit|128|68.92 ± 1.01|
|edit|256|100.00 ± 0.00|
|edit|512|100.00 ± 0.00|
|session_end|64|56.40 ± 2.11|
|session_end|128|100.00 ± 0.00|
|session_end|256|100.00 ± 0.00|
|session_end|512|100.00 ± 0.00|


seed별 표: results/kv_chunk_replay/seed_summary.csv. 요청별 LCP/손실, 객체별
고유 사용량/반복 사용, native reference는 같은 폴더의 CSV들에 보존했다.
512의 stored tokens=0이므로 utilization은 **null**, zero가 아니다. Unused=0을
효율 개선으로 부를 수 없다. 이 조건은 아예 persistence coverage가 없다.

## 단순 chunk 크기 조정만으로 해결되는가

256→64는 총 추가 계산 22,435→7,843 tokens, **65.04% 감소**이고 oracle reuse
회수율은 12.04%→69.25%로 높아진다. 크기 조정 효과는 크지만, 시험한 최소 C=64에도
30.75% 손실이 남아 **이 네 크기 안에서 완전히 해결됐다고 볼 수 없다**.
다만 이 모델은 C를 1로 줄이면 경계 손실이 수학적으로 없어지는 구조다. 잔여 손실이
곧 새 policy 필요성이나 novelty의 증거는 아니다. 더 작은 C의 I/O·metadata·batching·
latency 비용을 측정하지 않아 어느 크기가 시스템적으로 최적인지도 판단할 수 없다.

원래 full-state backend의 native 재사용 0과 scores serialization 비용은 chunk tuning의
해결 대상과 다른 현상이다. 이번 replay는 그것들을 해결하지 않았다. Partial chunks를
저장·truncate-reuse하는 실제 backend는 다른 결과를 낼 수 있으므로 이 표를 그대로
LMCache/실제 SSD 성능으로 옮기면 안 된다. Batching의 효과는 미측정이다.
앞선 full-state smoke의 cold/partial numerical equivalence도 미해결이다.
이번 수치는 LCP 기반 계산 가능량이며 실제 logits·출력 품질 보존을 검증한 결과가 아니다.

## 연구 판단과 다음 최소 검증

Chunk size가 짧은 trace의 재사용 상한을 크게 바꾸는 것은 정량화했다. 실제 chunk
backend의 기전이나 novel cross-layer mismatch를 입증하지는 않았다. 다음 최소
검증 후보는 같은 trace에서 기존 chunk backend의 partial-tail/partial-chunk reuse
semantics가 이 strict reference와 맞는지 확인하는 것이다. 실행은 하지 않았다.
논문 후보가 되려면 현실 trace에서 반복되고 단순 tuning/batching 후에도 비용-이득의
선택 역전이 동일 SLO/recovery 조건에서 보여야 한다. Byte/NAND/latency evidence는 아직 없다.
