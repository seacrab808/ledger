# LEDGER / shared-flash research exploration

**연구 방향: provisional · 현재 Phase 1 · 서버 연결 완료, KVM 권한으로 실행 보류**

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
  충분한 available RAM. 현재 계정에 `/dev/kvm` 접근 권한이 없습니다.
- Dependency 설치, build, guest 생성/boot, fio sanity는 미실행입니다.
- E0 및 Phase 2 이후 실험은 시작하지 않았습니다.

## 집과 연구실

집 Windows/WSL에서는 코드·HTML·오프라인 분석을 하고, FEMU 실행은 집의 물리
Ubuntu 또는 승인된 연구실 Linux에서 할 수 있습니다. Git과 JSON config를
공유하되 host 정보를 매 실행 기록합니다. 호스트별 성능을 같은 조건처럼
합치지 않습니다. 접속 주소·계정은 Git에 저장하지 않습니다.

공용 서버에서는 계정의 **ledger 폴더 안에만** 파일·venv·cache·build·image를
둡니다. 시스템 패키지/계정/서비스/권한/네트워크 설정은 변경하지 않습니다.
venv는 KVM device 권한을 해결하지 못합니다. 현재 gate를 통과하지 못했으므로
실행을 강행하지 않습니다. 접근 권한 확인 결과는 records/lab-constraints.json에 있습니다.
서버의 기존 빈 `~/ledger`에 프로젝트 checkout도 준비했습니다. 초기 준비 시각과
commit은 records/lab-workspace.json에 남겼습니다. FEMU source 확보는 현재 로컬에서만
완료됐으며 서버에는 프로젝트 코드·문서·lock이 있습니다.

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

환경 gate를 통과한 뒤 설치/build/guest/sanity를 수행합니다. 재개 절차는
[Phase 1 노트](docs/phase-01.html)에 있습니다. config는 source로 검토한 후보이며
VM에서 검증한 최종 설정은 아닙니다.

공용 서버의 dependency 설치도 ledger 내부 prefix/venv로 한정합니다.
공식 문서의 sudo/apt 예제를 이 서버에서 그대로 실행하지 않습니다.

## 구조

- docs/LEDGER*.html: 수정하지 않는 과거 원본.
- records/: 작은 환경 관측·진행·의사결정 JSON, 설명의 source of truth.
- tools/render_docs.py: 기록으로부터 HTML 생성.
- docs/DOCUMENT_CONFLICTS.md: 문서 차이와 현재 해석.
- external/femu.lock.json: upstream pin과 공식 출처.
- configs/femu/blackbox-small.json: 작은 FTL 모델 후보.
- results/summary/: 작은 기계 판독 결과. 큰 artifact는 Git 밖에 보관.

기존 remote는 public입니다. 이번 작업에서 visibility는 바꾸지 않습니다.
