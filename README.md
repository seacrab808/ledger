# LEDGER / shared-flash research exploration

**연구 방향: provisional · Phase 1 통과 · Phase 2 pilot/긴 overwrite 확인 완료 · 추가 실험 승인 대기**

이 저장소는 정해진 LEDGER의 최종 구현 명세가 아닙니다. 여러 서비스와 LLM이
저장장치를 쓸 때 논리 쓰기 바이트가 내부 NAND 쓰기·소거 비용을 충분히
설명하는지 탐색합니다. 더 강한 현상이 발견되면 문제와 해결 방향을 바꿉니다.

[연구 대시보드](docs/index.html)를 브라우저에서 열어 주세요.
새 HTML은 CSS를 포함하며 인터넷 없이 읽을 수 있습니다.

## 현재 상태

- Windows 10 Home, Ryzen 5 3500 / 6 cores / 16 GB RAM.
- 설치된 Ubuntu 26.04는 WSL2입니다. 물리 Ubuntu 설치 여부는 미확인입니다.
- 공식 FEMU는 물리 x86_64 Linux/KVM을 요구하며 WSL을 지원하지 않습니다.
- FEMU source는 external/FEMU에 pin하고 Git에는 lock만 기록합니다.
- 연구실 서버 자동 SSH 점검 성공: 물리 Ubuntu 22.04, AMD Threadripper,
  충분한 available RAM. 사용자가 KVM 권한을 준비했고 **새 SSH 세션의
  group/RW/open/API/빈 VM 생성 검사**가 통과했습니다.
- 시스템 설치 없이 ledger 내부 dependency/venv로 FEMU build와 native 단위
  테스트가 통과했습니다. FEMU source patch는 없습니다.
- Guest 2 GiB/2 vCPU, raw 4 GiB/exposed 3 GiB BlackBox에서 16 MiB direct write와
  CRC32C verify read 성공. native delta host/NAND=4096 pages, GC/erase=0입니다.
- QEMU observed peak RSS 3.63 GiB, fio 구간 평균 CPU 약 271% (100%=논리 CPU 하나).
  관측 구간 host swap-in/out=0. VM은 정상 종료했습니다. 전체 작업 폴더 약 4.61 GiB.
- 승인된 Phase 2 pilot만 완료했습니다. 동일 70% fill·4 KiB/QD1/job1/direct·host 4.20 GiB에서
  sequential/random 각 3회. 평균 WAF 1.1944/1.9049, erase/GiB 1222.858/1950.478.
  native GC/erase와 동일 observed initial state가 확인됐습니다. 모든 VM을 종료했습니다.
- 추가 E0 조건과 다음 Phase는 실행하지 않았습니다. [Phase 2 pilot 노트](docs/phase-02.html)와 records/phase-02-*.json에 원본·해석이 있습니다.

## 집과 연구실

집 Windows/WSL에서는 코드·HTML·오프라인 분석을 하고, FEMU 실행은 집의 물리
Ubuntu 또는 승인된 연구실 Linux에서 할 수 있습니다. Git과 JSON config를
공유하되 host 정보를 매 실행 기록합니다. 호스트별 성능을 같은 조건처럼
합치지 않습니다. 접속 주소·계정은 Git에 저장하지 않습니다.

공용 서버에서는 계정의 **ledger 폴더 안에만** 파일·venv·cache·build·image를
둡니다. 시스템 패키지/계정/서비스/권한/네트워크 설정은 변경하지 않습니다.
venv는 KVM device 권한을 해결하지 못합니다. 과거 권한 부족 이력은
records/lab-constraints.json, 현재 통과 검사는 records/kvm-sanity.json에 있습니다.
서버의 기존 빈 `~/ledger`에 프로젝트 checkout도 준비했습니다. 초기 준비 시각과
commit은 records/lab-workspace.json에 남겼습니다. 서버에도 pinned source·내부 dependency·
build·guest image·run log가 `external/FEMU/`, `artifacts/`, `.venv/`에 있으며 큰 파일은 Git에서 제외합니다.

## 오프라인 도구 — FEMU 실험을 실행하지 않음

```text
python tools/validate_config.py
python -m unittest discover -s tests -v
python tools/render_docs.py
python tools/validate_docs.py
```

물리 Linux 후보에서는 먼저 다음 환경 점검만 수행합니다.

```text
python3 tools/preflight_linux.py --output results/summary/linux-preflight.json
```

Phase 1 결과와 절차는 [Phase 1 노트](docs/phase-01.html)에 있습니다. 작은 config는
이 sanity에서 runtime 검증됐습니다. 이후 GC와 E0 pattern 차이의 pilot는 별도 기록이며 실기기 검증은 하지 않았습니다.
실행 당시 config bytes/hash는 records/phase-01-executed-config.json에 보존했습니다.

공용 서버의 dependency 설치도 ledger 내부 prefix/venv로 한정합니다.
공식 문서의 sudo/apt 예제를 이 서버에서 그대로 실행하지 않습니다.
Build는 2 jobs/nice 10/2 CPU affinity, VM은 하나만/6 CPU affinity/12 GiB address-space
limit로 실행했습니다. CPU 수치는 전체 QEMU process이며 짧은 fio 실행·수집 구간입니다.
공용 서버 활동이 latency/resource 값에 영향을 줄 수 있습니다.

Phase 2 pilot의 차이는 단일 FEMU 조건의 유한 overwrite 구간에서 얻은 evidence입니다.
steady state, 실기기 수명, 서비스 회계, LEDGER 정책 효과로 일반화하지 않습니다.
이후 승인된 긴 overwrite의 window별 수렴 확인도 완료했습니다. 다음 실험은 승인 대기입니다.

## 구조

- docs/LEDGER*.html: 수정하지 않는 과거 원본.
- records/: 작은 환경 관측·진행·의사결정 JSON, 설명의 source of truth.
- tools/render_docs.py: 기록으로부터 HTML 생성.
- docs/DOCUMENT_CONFLICTS.md: 문서 차이와 현재 해석.
- external/femu.lock.json: upstream pin과 공식 출처.
- configs/femu/blackbox-small.json: 작은 FTL 모델 후보.
- results/summary/: 작은 기계 판독 결과. 큰 artifact는 Git 밖에 보관.

기존 remote는 public입니다. 이번 작업에서 visibility는 바꾸지 않습니다.

## 긴 overwrite 추가 확인

동일 FEMU 설정과 70% fill에서 25.20 GiB overwrite를 각 3회 실행했다. 마지막 3 windows 평균 WAF=1.000000/1.900780, erase/GiB=1023.493/1946.245. 6회 모두 수렴 기준 통과=True. 유한 관측 구간과 단일 geometry의 FEMU 모델 근거이며 실기기나 서비스 정책 효과는 미검증이다.

[36 windows와 수렴 판정](docs/phase-02.html). 원본: records/phase-02-steady*.json. 추가 실험은 실행하지 않았습니다.
