# LMCache 64 / 128 / 256 비교 — 실측 준비, 아직 미실행

사용자의 최신 요청은 실제 기존 chunk backend 비교이다. 이전 AGENTS.md의
history-control 종료 제한은 이번 요청의 범위를 막는 근거가 아니다.
공유 서버 자원 및 ledger 밖 쓰기 금지 규칙은 유지한다.

## 먼저 확인한 구현

LMCache **0.5.5**, commit `05a013b29da78cf2321b9b46ec5039dde2fb0bb0`을
source audit 대상으로 고정했다. 다운로드한 source의 SHA256은
`records/lmcache-audit.json`에 있다. 설치/추론 성공을 뜻하지 않는다.

- `ChunkedTokenDatabase._chunk_tokens`, `_prefix_hash`, `process_tokens`:
  `save_unfull_chunk`가 마지막 짧은 chunk의 저장 범위를 결정한다.
  key는 이전 prefix hash와 해당 chunk 전체 token 배열에서 만든다.
  따라서 마지막 짧은 chunk를 저장할 수 있다는 사실만으로, 긴 저장 chunk의
  임의의 앞부분을 조회할 수 있다고 해석하면 안 된다. 같은 짧은 token 배열로
  조회하는 경우와, 연장/편집으로 같은 위치의 chunk 내용이 바뀌는 경우가 다르다.
- `LocalDiskBackend.batched_submit_put_task`: key마다 개별 submit 호출이다.
  디스크 파일/쓰기 자체를 합치는 기능으로 해석하지 않는다.
- `batched_get_blocking`: metadata lookup을 묶고 여러 파일 읽기를 병렬 제출한다.
- `BatchedMessageSender`: controller admission/eviction 메시지 batching이다.
- `write_file`: 기본 buffered file write 및 선택적 O_DIRECT 경로가 있다.
  fsync 호출은 없다. 완료 callback을 durable commit으로 부르지 않는다.

확인 대상 source:
[token database](https://github.com/LMCache/LMCache/blob/05a013b29da78cf2321b9b46ec5039dde2fb0bb0/lmcache/v1/token_database.py),
[LocalDisk](https://github.com/LMCache/LMCache/blob/05a013b29da78cf2321b9b46ec5039dde2fb0bb0/lmcache/v1/storage_backend/local_disk_backend.py).

## 실행 전 gate

1. 공유 GPU 사용 허가/예약 확인. 현재 probe에서 GPU 약 97,887 MiB 중
   83,185 MiB가 사용 중이었다. 순간 utilization=0은 비어 있다는 뜻이 아니다.
2. 기존 2 CPU affinity/nice 10, RSS 8 GiB, address space 12 GiB,
   추가 artifact 10 GiB를 유지한다. GPU 후보 상한은 4 GiB이며 아직 미승인이다.
   이 한도에서 CUDA runtime이 맞는지도 확인한다. 실패하면 한도를 조용히 풀지 않는다.
3. Python / torch / CUDA / LMCache / inference engine ABI tuple 및 model을
   고정하고 설치 크기를 먼저 조사한다. 기존 GGUF 모델은 vLLM용 weight와
   호환을 확인하지 않은 상태이므로 그대로 사용할 수 있다고 가정하지 않는다.
4. CPU MP 대안은 존재하지만 POSIX shared memory를 쓴다. ledger 밖 생성 금지와
   충돌하는 IPC 경로는 사용자 확인 없이 실행하지 않는다. CPU storage bench를
   실제 model prefill 측정으로 대신하지 않는다.
5. 캐시/HOME/TMPDIR/build/model을 ledger 내부로 설정한 뒤 bootstrap한다.
   전역 cache drop, sudo, system install, 타인의 process 종료는 금지한다.

## correctness smoke

모델 1개, worker 1개, 작은 cache로 cold baseline을 얻고 다음 경우를 별도로 확인한다.

- 정확히 동일한 full chunk prefix의 저장 → 디스크 조회 → 실제 model 계산 생략.
- LCP가 chunk 내부에서 끝나는 연장/편집 요청.
- 동일한 짧은 tail 조회와, 그 tail을 연장한 요청을 비교한다.
  `save_unfull_chunk=false/true`의 native lookup/load 결과를 따로 확인한다.
- native engine RAM prefix cache를 비활성화하고 CPU hot cache가 disk hit를
  대신하지 않는지 실제 disk read 및 KV restore 이벤트로 확인한다.
- 결과 token 및 첫 logits를 cold baseline과 비교한다. 수치 차이는 기록하고
  correctness gate 실패 시 성능 본 비교를 진행하지 않는다.
- async writes를 모두 drain한 뒤 수집한다. 저장 직후 같은 프로세스에서의
  hit만으로 재시작 후 disk recovery를 주장하지 않는다.

## 주 비교 — 실제 integrated inference

동일한 기존 12개 controlled synthetic trace(4 fixtures × seeds 42/43/44)를
64/128/256에 paired 적용한다. 원본 38개 artifact hash 검증을 완료했다.
주소/입력 token, 요청 순서, model, dtype, cache capacity, worker, decoding 조건,
disk backend, partial-tail 설정은 고정한다. arm 순서는 교대로 배치하고 기록한다.

각 요청의 입력은 기록된 token IDs를 그대로 사용한다. completion을 다시 만들어
다음 arm의 입력을 바꾸지 않는다. token-ID 입력 지원과 tokenizer/model 호환을
smoke에서 확인한다. 최대 1 token 출력으로 TTFT/prefill을 분리하는 후보이며,
native prompt-only KV 저장을 쓰면 이전 full-state completion snapshot reference와
동일한 저장 coverage가 아니므로 새 native 저장 event로 LCP와 coverage를 다시 계산한다.
모델/engine이 지원하는 native 저장 경로를 이용하며 별도 SAVE/DROP 정책은 만들지 않는다.

계산 baseline은 cache-disabled 상태의 같은 입력이다. cache hit 수만 읽지 않고
실제 forward/prefill token count와 restore를 교차 확인한다. 개별 요청의
`baseline evaluated tokens - cache-arm evaluated tokens`가 계산 절약량이다.
TTFT는 요청 시작→첫 출력 token, prefill duration, read/restore duration,
전체 runtime을 분리한다. I/O 대기와 계산 절약을 latency 이득으로 혼동하지 않는다.

## 기존 batching 비교 — 기능 범위를 먼저 제한

integrated engine에 native batching on/off 설정이 있으면 그 설정만 비교한다.
해당 토글이 없으면 가짜 batching-off 정책을 추가하지 않는다.
같은 실제 KV 객체/key를 native 단일 API와 batch API로 처리하는 **storage
component 비교**를 추가할 수 있다. 결과는 integrated TTFT 결과와 분리한다.

비교는 동일한 키/bytes, worker thread 수(최대 2), warm/cold 조건에서 한다.
단일 read 반복 vs `batched_get_blocking`의 완료시간/I/O 횟수를 측정한다.
write는 동일한 completion barrier를 두고 단일 제출 vs batch 제출을 비교한다.
호출 한 번이 file write 한 번과 같다고 가정하지 않는다. 읽기 병렬화가 시간을
줄여도 bytes/files/syscalls가 줄었는지는 별개로 보고한다.

## metric 및 단위

|항목|측정/정의|해석 한계|
|---|---|---|
|실제 prefill 절약|paired forward token count 차이, tokens 및 ms|분석 LCP 상한과 구분|
|KV payload 쓰기|native write buffer 길이 합, bytes|중복 저장/dedup/tail 포함 기록|
|Linux write_bytes|소유 process `/proc/PID/io` delta, bytes|NAND 물리 쓰기/erase 아님; filesystem journal 별도|
|I/O 횟수|소유 process/thread의 read/write/pread/pwrite syscall 및 open/close 개별 count|file 수나 API call 수로 대체 금지|
|metadata|native key/index 개수, index RAM 증가/고정 overhead, on-disk header bytes, 파일/inode 수|RSS 차이는 metadata만의 정확한 bytes가 아님; FS metadata write bytes는 unavailable 가능|
|지연|TTFT, prefill, read/restore, write completion, batch 완료, ms|fsync 없는 완료는 durability 보장 아님|
|고유 사용 bytes|저장 객체/version별 한번 이상 restore한 byte 범위의 union|반복 hit bytes 총합과 분리|
|반복 reuse|restore 횟수 및 누적 restore bytes|고유 사용 bytes / 저장 bytes와 혼합하지 않음|

strace는 소유 process에만 사용하고 실행 overhead를 기록한다. timing 비교는
같은 계측 조건을 유지한다. 원본 JSON/CSV/event log가 근거이다.
메타데이터나 물리 I/O가 직접 계측되지 않으면 null로 보고한다.
전체 OS cache를 비우지 않는다. warm page cache 및 요청별 관측 read_bytes를 기록한다.

## 판정

fixture별 seed-level paired 차이와 평균 ± sample SD를 보고한다. 짧은 fixture의
p99를 안정적인 SLO 결론으로 사용하지 않는다. 작은 C가 계산을 줄이는 동시에
payload bytes, syscall 수, metadata 또는 TTFT를 늘리는지는 **각각** 판정한다.
prefix dedup이 더 잘되면 작은 C의 total bytes가 줄 수도 있다.

기존 batching으로 지연/호출 비용이 없어지는 경우는 단순 구현·tuning 개선으로
해석한다. tuning 후에도 동일 trace·correctness 조건에서 계산/쓰기/latency의
선택 역전이 반복되고 실제 trace에서도 유지되어야 새로운 시스템 mismatch 후보로
발전시킨다. 이번에는 synthetic 외삽, NAND/wear 주장, 새로운 정책 구현을 하지 않는다.

## 실행 전 상태 (historical)

source audit 및 read-only host probe만 완료했다. 실제 prefill / disk bytes /
syscalls / metadata 비용 / latency / batching 수치는 **미측정(null)**이다.
공유 GPU 사용 확인과 실행 환경 gate가 해결되기 전에는 완료 결과로 표현하지 않는다.

## 2026-10-12 실행 기록

사용자가 GPU 최대 4 GiB와 GPU 가상 주소 제한 예외를 승인했다. 실제 RSS 8 GiB,
2-CPU affinity/nice 10, project-local 추가 artifact 10 GiB 제한은 유지했다.
Pinned 패키지의 설치/import와 CUDA preflight를 완료했다. V1 LocalDisk smoke는
correctness 실패로 보존하고, 기존 MP connector + FSL2Adapter로 작은 smoke를
통과한 뒤 12 traces × baseline/64/128/256을 실행했다. Library source나 새 정책은
구현하지 않았다. 기존 `skip_l1`과 temporary-prefetch 설정으로 RAM hot-cache와
디스크 복원을 분리했다. 모든 입력은 archived prompt token IDs 그대로다.

본 비교 greedy 792/792와 공통 logprob 차이 0.05 기준은 통과했지만 추가 top20
key-set gate는 14건 실패했다. 기준을 사후 완화하지 않고 screening 결과로만
보고한다. 실행 옵션은 `configs/experiments/lmcache-native-mp.json`, 실제 source,
입력, counter events와 실패 기록은 `results/lmcache_native/`에 있다.

실제 파일 API bytes/operation 수, forward tokens, 1-token wall time, 파일/key
수와 파생 고유 소비 bytes를 측정했다. Kernel syscall, metadata-only RAM,
filesystem metadata writes, isolated GPU prefill time, NAND writes는 미측정이다.
기존 MP FS list API와 단일-key API의 component 비교는 동일 실제 KV 객체 8개,
순서 교대 및 3회 반복으로 완료했다. Bytes hash 18/18 통과, bytes와 파일 API
호출 수는 동일했다. Integrated engine batching의 on/off 성능 비교로 부르지 않는다.

설명은 `docs/kv-screen.html`, 수치는 `records/lmcache-native-summary.json`을
참고한다. 다음 최소 진단은 14건의 top20 순위 차이 확인이며 아직 실행하지 않았다.
