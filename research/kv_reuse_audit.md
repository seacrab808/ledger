# KV persistence audit — 2026-10-12

현재 ledger에는 KV backend나 실제 conversation/agent trace가 없었다. 기존 FEMU
결과는 보존하며 새 screening과 독립적으로 취급한다. 연구 목적은 분석 기반
시스템 설계 논문의 문제 후보를 발견하는 것이다. 아래는 아직 runtime 검증 전
source 관측이며 chunk mismatch가 입증됐다는 뜻이 아니다.

## 고정한 구현

- llama-cpp-python 0.3.36 PyPI source archive.
- SHA256: `832db0699007f1be95a7e41ef12e88926b02ba836461e36a36372db2760c1a2e`.
- archive 내부 vendor/llama.cpp가 실제 backend이며 움직이는 main과 혼합하지 않는다.
- 모델 후보: Qwen/Qwen2.5-0.5B-Instruct-GGUF, revision
  `9217f5db79a29953eb74d5343926648285ec7e67`, Q4_K_M.
- CPU-only, context 2048, generation upper bound 32, one process/two threads.
  작은 모델은 lifecycle correctness와 controlled screening용이며 성능 일반화용이 아니다.

## Source 경로 (고정 source archive 기준)

|동작|파일·함수|확인한 내용|
|---|---|---|
|KV 생성/계산|llama_cpp/llama.py:Llama.eval (666), _internals.py:LlamaContext.decode|eval token batch가 native decode로 전달된다. Prompt와 generation은 별도 추적한다.|
|저장 시점|llama.py:Llama._create_completion (1710/1718)|완료 후 prompt+completion token key로 save_state를 disk cache에 넣는다.|
|직렬화|llama.py:Llama.save_state (2214)|native state bytes, scores, input_ids, n_tokens, seed를 포함한다. 순수 KV 파일이 아니다.|
|저장/용량|llama_cache.py:LlamaDiskCache.__setitem__ (145)|기존 같은 key 제거, diskcache에 state 저장, capacity 초과 시 항목 제거.|
|key 선택|llama_cache.py:LlamaDiskCache._find_longest_prefix_key|token tuple의 longest common prefix를 탐색한다. 모델 identity 격리는 실험 cache directory로 보장한다.|
|조회|llama_cache.py:LlamaDiskCache.__getitem__ (130)|선택한 항목을 pop한다. 이 제거는 invalidation/용량 eviction과 다르므로 CONSUMED_ON_LOOKUP으로 기록한다.|
|복원 선택|llama.py:Llama._create_completion (1372)|disk prefix가 resident prefix보다 길 때만 load_state한다. 조회가 곧 복원은 아니다.|
|복원|llama.py:Llama.load_state (2244)|native state를 복원하고 _requires_eval=True로 설정한다.|
|실제 생략|llama.py:Llama.generate (916–957)|token prefix를 재사용한다. 복원 후 완전히 일치한 prompt는 logits 갱신을 위해 마지막 token 재계산 가능.|
|종료/edit/retry|backend에는 별도 사용자 session lifecycle API 없음|fixture의 행동을 기록하되 edit를 곧바로 backend invalidation이라고 부르지 않는다. 기존 객체가 나중에 재사용 가능할 수 있다.|

## 계측 원칙

backend source를 수정하지 않고 관찰 subclass/wrapper를 사용한다. disk lookup,
load_state, 첫 prompt eval, 저장 성공을 연결한다. lookup은 LOADED 이전의 별도 사건이다.
native n_p_eval은 single-token decode를 generation으로 분류할 수 있으므로 prompt 처리량의
유일한 ground truth로 쓰지 않는다. prompt eval의 실제 token 수와 첫 sample 위치를 추적한다.

저장 버전별 unique ID를 부여하고 그 버전의 실제 재사용 token 구간을 union한다.
동일 저장 bytes를 반복 load해도 unique utilization 분자에는 한 번만 포함한다.
반복 reuse 호출 수와 token savings 합계는 별도 metric이다. 서로 다른 저장 버전의
동일 prefix는 실제 반복 저장이므로 write-instance 분모에는 각각 포함한다.

native state 크기는 순수 KV 크기가 아니다. serialized record bytes는 직접 측정,
순수 KV byte attribution은 unavailable로 남긴다. token interval utilization은
tokens/tokens로 계산한다. bytes/tokens는 효율 단위이며 utilization이라고 부르지 않는다.

현재 backend는 full state를 저장한다. fixed chunk boundary, async flush, chunk dedup,
batching 또는 실제 NAND write reduction은 여기서 검증할 수 없다.

## Runtime 확인 결과

Smoke는 observer/native 복원의 출력과 첫 logits를 정확히 일치시켰다.
부분 복원 vs cold는 출력과 logits가 달라 backend numerical equivalence는 미확인이다.
12 screening runs 모두 disk reuse=0이었다. 252 read가 resident보다 나은 prefix를
제공하지 않아 pop 후 복원되지 않았다. 따라서 이 fixture에서 append-only positive
baseline도 실패했다. 일반적인 KV reuse 낭비나 fixed chunk 기전을 입증하지 않는다.
Scores array serialization이 record bytes의 약 96–98%를 차지했다.
