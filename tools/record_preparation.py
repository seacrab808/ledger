"""Capture preparation provenance; this does not report a FEMU runtime result."""
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "LEDGER 실험 보고서.html": "8e0d6b1dd92c8cef14f2c398c70a75b668ff1babd91909be46d23ad51145b514",
    "LEDGER 연구 제안서.html": "9332dd217d1e3b8a76c3b958287c0acd4338de24d970021b767cdfaa6a225d0b",
    "LEDGER_한장요약.html": "e83d27ea9cae6cf96c7b2c608aecfa77c6d73b3370e1cceb ded1cac96486fbe3".replace(" ", "")
}


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def capture():
    connection_file = ROOT / "records/remote-connection.json"
    connection = json.loads(connection_file.read_text(encoding="utf-8")) if connection_file.exists() else {
        "status": "not-verified", "login_succeeded": False, "host_environment_read": False,
        "private_endpoint": "omitted"
    }
    workspace_file = ROOT / "records/lab-workspace.json"
    workspace = json.loads(workspace_file.read_text(encoding="utf-8")) if workspace_file.exists() else None
    lock = json.loads((ROOT / "external/femu.lock.json").read_text(encoding="utf-8"))
    external = ROOT / lock["checkout"]
    if git("rev-parse", "HEAD", cwd=external) != lock["commit"]:
        raise ValueError("FEMU checkout does not match pin")
    if git("status", "--porcelain", cwd=external):
        raise ValueError("FEMU source changed; record an explicit patch first")
    sources = []
    for name, expected in EXPECTED.items():
        digest = hashlib.sha256((ROOT / "docs" / name).read_bytes()).hexdigest()
        if digest != expected:
            raise ValueError(f"Historical document changed: {name}")
        sources.append({"path": "docs/" + name, "sha256": digest, "status": "original-unchanged"})
    refs = []
    for topic, rel in lock["references"].items():
        refs.append({"topic": topic, "path": rel,
                     "sha256": hashlib.sha256((external / rel).read_bytes()).hexdigest(),
                     "url": f"https://github.com/MoatLab/FEMU/blob/{lock['commit']}/{rel}"})
    result = {
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "display_timezone": "Asia/Seoul",
        "project_commit_at_capture": git("rev-parse", "HEAD"),
        "project_dirty_at_capture": bool(git("status", "--porcelain")),
        "femu_commit": lock["commit"], "femu_source_clean": True,
        "source_checkout_status": "completed", "source_documents": sources,
        "references": refs,
        "config_sha256": hashlib.sha256((ROOT / "configs/femu/blackbox-small.json").read_bytes()).hexdigest(),
        "environment_probe_source_sha256": {
            filename: hashlib.sha256((ROOT / "tools" / filename).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for filename in ("preflight_linux.py", "lab_constraints.py")
        },
        "phase": 1, "phase_status": "incomplete-kvm-permission-blocked",
        "runtime": {"dependency_install": "not-run", "build": "not-run", "guest_creation": "not-run",
                    "guest_boot": "not-run", "sanity": "not-run", "target_device": None,
                    "qemu_rss_bytes": None, "qemu_cpu_utilization": None,
                    "guest_memory_measured_bytes": None, "host_swap_during_femu": None,
                    "native_counters": None},
        "remote_connection": connection,
        "remote_workspace_initialization": workspace,
        "activities": [
            {"id": "P1-HOST-001", "kind": "environment", "status": "confirmed", "result": "Windows host와 WSL Ubuntu를 읽기 전용으로 확인. FEMU 실행 gate 미통과.", "artifacts": ["records/windows-host.json", "records/wsl-preflight.json"]},
            {"id": "P1-SOURCE-001", "kind": "preparation", "status": "confirmed", "result": "공식 source를 external/FEMU에 detached checkout, pin 확인. 수정·build 없음.", "artifacts": ["external/femu.lock.json"]},
            {"id": "P1-CONFIG-001", "kind": "offline-audit", "status": "source-reviewed", "result": "geometry와 counter source 확인. arithmetic audit만 수행했으며 realize/boot는 하지 않음.", "artifacts": ["configs/femu/blackbox-small.json"]},
            {"id": "P1-SSH-001", "kind": "connection", "status": connection["status"], "result": connection.get("summary", "자동 접속 미확인"), "artifacts": ["records/remote-connection.json"] if connection_file.exists() else []},
            {"id": "P1-WORKSPACE-001", "kind": "preparation", "status": "ready" if workspace else "not-run", "result": "서버의 기존 빈 ledger 폴더 안에 프로젝트 checkout 준비. 초기 checkout commit은 lab-workspace.json에 기록. 공용 설정 변경 없음." if workspace else "서버 프로젝트 checkout 미준비", "artifacts": ["records/lab-workspace.json"] if workspace else []},
            {"id": "P1-SANITY-001", "kind": "platform-sanity", "status": "not-run", "result": "FEMU guest가 없어 실행하지 않음. 연구 결과 없음.", "artifacts": []}
        ],
        "issues": [
            {"problem": "지원되지 않는 Windows/WSL 실행 환경", "action": "dependency 설치·build·guest·fio를 실행하지 않고 물리 Linux 경로를 준비", "status": "open"},
            {"problem": "자동 서버 접속에 필요한 암호화 키 해제", "action": "사용자가 SSH agent에 키를 직접 추가. 자동 SSH 환경 probe 성공. credential은 기록하지 않음", "status": "resolved"},
            {"problem": "Windows 드라이브의 private key를 WSL이 0777로 인식", "action": "로컬 WSL 개인 디렉터리에 키 복사 후 600. Git·서버에는 private key를 넣지 않음", "status": "resolved"},
            {"problem": "첫 SSH 등록 helper의 Windows 인용 처리 오류", "action": "등록 내용을 SSH stdin으로 전달하도록 수정. 기존 키 보존. 수정 후 등록 성공을 터미널에서 확인", "status": "resolved"},
            {"problem": "공용 서버 계정의 /dev/kvm 접근 권한 없음", "action": "기본 설정 수정 금지 지시를 준수. sudo·group·ACL 변경·TCG 우회 없이 FEMU 실행 보류", "status": "open"},
            {"problem": "서버에 다수의 FEMU C build dependency가 없음", "action": "공용 apt 설치 금지. 실행 경로가 확보된 뒤 ledger 내부 prefix/venv만 사용하는 설치 가능성을 검토", "status": "open"},
            {"problem": "기존 README가 UTF-16이라 patch 도구가 읽지 못함", "action": "README만 UTF-8로 변환해 편집. 원본 HTML은 hash로 보존 확인", "status": "resolved"}
        ],
        "feasibility": {
            "home_native_linux": "미확인. 물리 Ubuntu/KVM과 충분한 available RAM이면 작은 E0 후보",
            "home_current_wsl": "C: 현재 지원 환경이 아님. 원격 Linux 또는 집 물리 Linux가 필요",
            "lab": "물리 Ubuntu 22.04·AMD-V·KVM 모듈·충분한 RAM 확인. 현재 계정은 /dev/kvm 접근 불가라 runtime gate 미통과",
            "note": "연구실 장비가 필수인 것은 아니다. 집 물리 Linux도 가능하다. 두 호스트의 성능을 합치지 않는다."
        }
    }
    runtime_file = ROOT / 'records/phase-01-runtime.json'
    if runtime_file.exists():
        run = json.loads(runtime_file.read_text(encoding='utf-8'))
        executed = ROOT / 'records/phase-01-executed-config.json'
        if hashlib.sha256(executed.read_bytes()).hexdigest() != run['config_sha256']:
            raise ValueError('Executed config hash changed')
        old_config = json.loads(executed.read_text(encoding='utf-8'))
        current_config = json.loads((ROOT / 'configs/femu/blackbox-small.json').read_text(encoding='utf-8'))
        if old_config['device'] != current_config['device'] or old_config['guest'] != current_config['guest']:
            raise ValueError('Runtime result does not validate current geometry/guest')
        if run['status'] == 'passed' and run['qemu_stopped']:
            resources = run['resources']
            result['phase_status'] = 'complete-awaiting-phase2-approval'
            result['executed_config_sha256'] = run['config_sha256']
            result['runtime_result'] = 'records/phase-01-runtime.json'
            result['runtime'] = {
                'dependency_install': 'project-local extraction + venv; no system install',
                'build': 'passed', 'guest_creation': 'passed', 'guest_boot': 'passed', 'sanity': 'passed',
                'target_device': run['guest']['target'], 'qemu_rss_bytes': resources['rss_peak_bytes'],
                'qemu_cpu_utilization': resources['cpu_mean_by_phase'],
                'guest_memory_measured_bytes': int(run['guest']['guest_memory'].splitlines()[0].split()[1]) * 1024,
                'host_swap_during_femu': resources['host_swap_page_deltas'],
                'native_counters': run['metrics']['native_counter_deltas'], 'qemu_stopped': True}
            result['activities'] += [
                {'id': 'P1-KVM-002', 'kind': 'environment-sanity', 'status': 'passed', 'result': '새 SSH 세션에서 kvm group·R/W·open·API 12·빈 VM 생성 확인. 사용자가 권한을 준비했고 agent는 공용 설정을 수정하지 않음.', 'artifacts': ['records/kvm-sanity.json', 'records/lab-preflight-current.json']},
                {'id': 'P1-BUILD-001', 'kind': 'build', 'status': 'passed', 'result': '공식 Ubuntu dependency를 ledger 내부에 압축 해제하고 venv 사용. 2 jobs/nice 10으로 QEMU 10.1 build와 native 단위 테스트 2개 통과. FEMU source patch 없음.', 'artifacts': ['records/lab-preparation.json', 'records/femu-build.json']},
                {'id': 'P1-GUEST-001', 'kind': 'guest', 'status': 'passed', 'result': '공식 Ubuntu 24.04 이미지 checksum/signature 확인. native image builder로 guest 준비. 2 GiB·2 vCPU boot와 3 GiB BlackBox namespace 인식.', 'artifacts': ['records/phase-01-guest.json']},
                {'id': 'P1-SANITY-002', 'kind': 'platform-sanity', 'status': 'passed', 'result': '16 MiB direct write + CRC32C 검증 read 성공. native delta host/NAND 4096·GC/erase 0. VM 정상 종료. E0 evidence 아님.', 'artifacts': ['records/phase-01-runtime.json', 'records/phase-01-executed-config.json', 'records/phase-01-footprint.json']}]
            # Preserve prior blocked/preparation entries as history, rather than rewriting them.
            for issue in result['issues']:
                if issue['problem'] == '공용 서버 계정의 /dev/kvm 접근 권한 없음':
                    issue.update(action='사용자가 kvm group 등록을 준비. 새 세션의 open/API/빈 VM 검사 통과. agent의 권한 변경 없음.', status='resolved')
                if issue['problem'] == '서버에 다수의 FEMU C build dependency가 없음':
                    issue.update(action='프로젝트 내부 APT index/cache·deb 압축 해제·venv로 build 성공. 공용 apt install 없음.', status='resolved')
            result['issues'] += [
                {'problem': '공용 서버의 오래된 APT 목록으로 일부 deb 404', 'action': 'ledger 내부에 별도 sources/index/cache를 두고 signed Ubuntu repository로 갱신. /etc·/var 상태 변경 없음.', 'status': 'resolved'},
                {'problem': 'GLib의 추가 libpcre build dependency 누락', 'action': '공식 libpcre development/runtime 패키지를 동일한 내부 prefix에 추가. 시스템 설치 없음.', 'status': 'resolved'},
                {'problem': '사용자 기존 Python site-package의 .pth 오류', 'action': 'remote Python -I, build PYTHONNOUSERSITE=1 및 project venv로 격리. 기존 설치 수정 없음.', 'status': 'resolved'},
                {'problem': 'FEMU serial property가 compatibility-only라 첫 identity 검사 실패', 'action': '쓰기 전 중단, native model·생성된 serial·capacity·mount 확인으로 수정. 실패 기록 보존. FEMU source patch 없음.', 'status': 'resolved'}]
            result['feasibility']['lab'] = '작은 Phase 1 통과. 동일 4/3 GiB로 pilot E0 준비 가능하지만 Phase 2 승인과 GC/reset/preconditioning 설계가 먼저 필요.'
    return result


if __name__ == "__main__":
    (ROOT / "records/phase-01.json").write_text(json.dumps(capture(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Phase 1 provenance recorded from structured measurement artifacts.")
