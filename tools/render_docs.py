"""Generate self-contained Korean research notes from small structured records."""
import datetime as dt
import html
import json
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.validate_config import audit
NAV = [("index.html", "대시보드"), ("research-map.html", "가능성 지도"),
       ("phase-01.html", "Phase 1"), ("experiment-log.html", "실험 기록"),
       ("decision-log.html", "결정 기록"), ("glossary.html", "용어 사전")]
CSS = """
:root{--ink:#202e2a;--muted:#5c6c65;--accent:#226653;--paper:#fffef9;--bg:#f1f3ec;--line:#d6ded2;--warn:#8e581c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.8 system-ui,-apple-system,'Malgun Gothic',sans-serif}
a{color:var(--accent);text-underline-offset:4px}a:focus-visible{outline:3px solid #dcad58;outline-offset:4px}
.shell{max-width:1160px;margin:auto;padding:32px 24px 70px}.top{display:flex;gap:16px;justify-content:space-between;align-items:center;font-size:13px;color:var(--muted)}
.brand{font-weight:800;letter-spacing:.12em;color:var(--accent)}nav{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0 36px}nav a{padding:8px 14px;border:1px solid var(--line);border-radius:6px;text-decoration:none;background:var(--paper)}nav a.active{background:var(--accent);color:white;border-color:var(--accent)}
header{margin-bottom:28px}.eyebrow{font-size:12px;font-weight:700;letter-spacing:.13em;color:var(--accent)}h1{font-size:clamp(28px,4.5vw,44px);line-height:1.3;margin:12px 0 18px;letter-spacing:-.035em}h2{font-size:23px;line-height:1.4;margin:0 0 16px}h3{font-size:18px;margin:18px 0 8px}p{margin:8px 0 14px}.lead{max-width:78ch;color:var(--muted);font-size:18px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.card,section{padding:24px;background:var(--paper);border:1px solid var(--line);border-radius:10px;margin-bottom:18px}.grid .card{margin:0}.grid{margin-bottom:18px}.callout{border-left:4px solid #ba863e;background:#faf3e4;padding:16px 20px;margin:20px 0}.tag{font-size:12px;font-weight:700;display:inline-block;border-radius:20px;padding:3px 10px;background:#e8eee4;color:var(--accent)}.tag.warn{background:#f7ecd9;color:var(--warn)}.tiny{font-size:13px;color:var(--muted)}.big{font-size:32px;font-weight:800;color:var(--accent);line-height:1.3}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:12px 10px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line);overflow-wrap:anywhere}th{color:var(--muted);font-size:12px;background:#f6f7f0}code{font:13px/1.7 ui-monospace,Consolas,monospace;background:#edf0e8;padding:2px 5px;border-radius:3px;overflow-wrap:anywhere}pre{white-space:pre-wrap;word-break:break-word;background:#203b32;color:#f2f5eb;padding:18px;border-radius:8px;font:13px/1.8 Consolas,monospace}ul,ol{padding-left:22px}li{margin:8px 0}details{margin:12px 0}summary{cursor:pointer;font-weight:700}.flow{display:flex;flex-wrap:wrap;gap:10px;align-items:center}.flow span{padding:10px 14px;background:#e9eee3;border-radius:6px}.flow b{color:var(--muted)}footer{margin-top:36px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}.statusline{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}.terms{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.terms article{background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:20px}.terms h2{font-size:18px;margin-bottom:10px}@media(max-width:720px){.shell{padding:22px 16px}.grid,.terms{grid-template-columns:1fr}section,.card{padding:18px}.top{align-items:flex-start}.top span:last-child{max-width:180px;text-align:right}nav{gap:6px}nav a{padding:6px 9px;font-size:13px}th,td{padding:10px 8px}}
"""


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def e(value):
    return html.escape(str(value))


def link(path, label):
    return f'<a href="{e(quote(path, safe="/:-._"))}">{e(label)}</a>'


def table(headers, rows):
    return '<div class="scroll"><table><thead><tr>' + ''.join(f'<th>{e(h)}</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{v}</td>' for v in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def section(title, body):
    return f'<section><h2>{e(title)}</h2>{body}</section>'


def bullets(items):
    return '<ul>' + ''.join(f'<li>{e(i)}</li>' for i in items) + '</ul>'


def gib(value):
    return "미측정" if value is None else f"{value / 1024**3:.2f} GiB"


def render():
    research = load("records/research.json")
    record = load("records/phase-01.json")
    win, wsl = load("records/windows-host.json"), load("records/wsl-preflight.json")
    lab, constraints = load("records/lab-preflight.json"), load("records/lab-constraints.json")
    config = load("configs/femu/blackbox-small.json")
    geom = audit(config)
    stamp = dt.datetime.fromisoformat(record["captured_at_utc"]).astimezone(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    source_links = '<ul>' + ''.join('<li>' + link(Path(s["path"]).name, Path(s["path"]).name) + ' <span class="tiny">원본·수정 없음</span></li>' for s in record["source_documents"]) + '</ul>'
    status = '<div class="statusline"><span class="tag">연구 방향 · provisional</span><span class="tag warn">Phase 1 · KVM 권한으로 실행 보류</span><span class="tag">Phase 2 · 미시작</span></div>'
    runtime_rows = [(e(k), e(v if v is not None else "미측정 / 없음")) for k, v in record["runtime"].items()]
    geometry_rows = [
        ("Guest", f'{config["guest"]["ram_mib"]} MiB RAM / {config["guest"]["vcpus"]} vCPU'),
        ("Raw / exposed", f'{gib(geom["raw_bytes"])} / {gib(geom["exposed_bytes"])}'),
        ("Spare 정의", f'raw 기준 {geom["raw_spare_fraction"]:.0%} / logical 기준 OP {geom["logical_op_fraction"]:.2%}'),
        ("Page / block", f'{geom["page_bytes"]:,} bytes / {geom["block_bytes"] // 1024**2} MiB'),
        ("Channels / LUNs / planes", f'{config["device"]["nchs"]} / {config["device"]["luns_per_ch"]} per channel / {config["device"]["pls_per_lun"]} per LUN'),
        ("GC line", f'{geom["blocks_per_line"]} blocks = {geom["line_bytes"] // 1024**2} MiB / {geom["line_count"]} lines'),
        ("GC thresholds", f'{config["device"]["gc_thres_pcent"]} / {config["device"]["gc_thres_pcent_high"]}; free-line threshold {geom["gc_background_free_line_threshold"]} / {geom["gc_foreground_free_line_threshold"]}'),
        ("FTL / placement", "page mapping · greedy GC · FDP/streams/hot-cold OFF · buffer 0"),
        ("Process 메모리 계획", f'{geom["estimated_process_budget_mib"] / 1024:.0f} GiB ≈ logical backend + guest + QEMU 여유; 실측 아님')]
    pages = {}
    pages["index.html"] = ("좋은 문제부터 찾는 연구", "지금은 LEDGER를 완성하는 단계가 아닙니다. 여러 서비스와 LLM의 쓰기가 내부 NAND 작업을 얼마나 잘 설명하는지, 실험으로 연구 방향을 고르는 단계입니다.", status +
        '<div class="grid"><div class="card"><h2>현재 가장 중요한 질문</h2><p>' + e(research["question"]) + '</p><p class="tiny">OS에서 1 GiB를 썼다고 보여도 SSD는 살아 있는 데이터를 옮기느라 내부에서 더 많이 쓸 수 있습니다. 그 차이가 실제로 크고 반복되는지 먼저 봅니다.</p></div><div class="card"><h2>지금 어디까지 왔나</h2><p>✅ 원본 검토 · source pin · geometry 검토 · 자동 SSH · 서버 환경 점검</p><p>⚠️ 서버 계정에 /dev/kvm 권한이 없습니다. build · guest boot · sanity는 미완료입니다.</p><p>❓ 실행 경로를 확보해야 Phase 1을 재개할 수 있습니다. 공용 서버 기본 설정은 변경하지 않습니다.</p></div></div>' +
        section("확정한 작업 규칙 / 아직 열려 있는 방향", table(["구분", "내용"], [("작업 규칙", "원본 보존, negative result 기록, native/derived·모델/실기기 구분, Phase 1에서 중단"), ("미확정", "문제의 크기, accounting/placement/KV/controller 중 해결 방향, 최종 contribution과 architecture"), ("주의", "기존 C1/C2/C3·H1~H5는 후보와 보고된 기록. 독립 재현한 사실로 표현하지 않음")])) +
        section("집에서도 계속 작업할 수 있습니다", '<p>집 Windows/WSL에서는 코드와 설명을 편집하고 분석할 수 있습니다. FEMU 실행은 집의 물리 Ubuntu 또는 연구실 Linux에서 합니다. 같은 Git/config를 쓰고 장비 정보와 resource 상태를 함께 기록하면 됩니다.</p><p>⚠️ 현재 WSL은 upstream 지원 환경이 아닙니다. 연구실 장비가 유일한 선택은 아니지만, 물리 Linux가 없는 현재에는 원격 실행이 현실적인 후보입니다.</p>') +
        section("연구 원본과 안내", source_links + '<p>' + link("DOCUMENT_CONFLICTS.md", "문서 차이와 현재 기준") + ' · ' + link("../AGENTS.md", "이후 작업 규칙") + ' · ' + link("../records/phase-01.json", "실제 준비 기록 JSON") + '</p>'))
    direction_cards = ''.join('<section><span class="tag">open · provisional</span><h2>' + e(d["name"]) + '</h2><h3>왜 재미있는가</h3><p>' + e(d["why"]) + '</p><h3>필요한 evidence</h3><p>' + e(d["needed"]) + '</p><h3>현재 evidence</h3><p>' + e(d["evidence"]) + '</p><h3>가장 큰 반론</h3><p>' + e(d["objection"]) + '</p></section>' for d in research["directions"])
    pages["research-map.html"] = ("승자를 정하지 않은 가능성 지도", "같은 관찰에서 여러 해결 방향이 나올 수 있습니다. 먼저 차이를 측정하고, 더 강하고 직관적인 설명을 가진 방향을 선택합니다.",
        '<div class="callout">❓ logical bytes ≠ physical wear는 현재 관찰 후보입니다. 이 저장소에서 확인한 연구 결과가 아닙니다.</div>' + direction_cards +
        section("잠정 roadmap", table(["Phase", "질문/작업", "상태"], [(str(p["phase"]), e(p["name"]), e(p["status"])) for p in research["roadmap"]]) + '<p>Phase 5에서 accounting, isolation, placement, KV policy, compute–wear controller 또는 새 방향을 선택합니다. Phase 6 이후는 그 결정에 따라 다시 설계합니다.</p>') +
        section("새 연구 질문 후보", bullets(research["new_questions"]) + '<p class="tiny">아이디어이며 결과가 아닙니다. 기존 주장을 지키기 위해 새 관찰을 무시하지 않습니다.</p>'))
    resume = """<ol><li><strong>접속과 환경 확인.</strong> 개인 터미널에서 SSH 인증을 준비합니다. 비밀번호/개인키를 채팅·Git에 보내지 않습니다. 서버에서 <code>tools/preflight_linux.py</code>로 물리 Linux, /dev/kvm, 모듈, available RAM을 점검합니다.</li>
<li><strong>프로젝트와 FEMU pin.</strong> 같은 Git commit을 가져오고 lock에 적힌 FEMU commit을 checkout합니다. 주소·사용자명·개인 작업 경로는 공개 결과에 제외합니다.</li>
<li><strong>공용 서버 경계.</strong> 모든 파일·가상환경·cache·build·image는 계정의 ledger 폴더 안에 둡니다. sudo/apt/usermod/ACL·service·network 변경은 하지 않습니다. Python venv는 C library나 /dev/kvm 권한을 해결하지 못합니다. 현재는 권한 gate 미통과로 설치·build를 보류합니다.</li>
<li><strong>Build.</strong> 작은 build job 수를 사용하고 configure/build log와 binary hash를 남깁니다. 기존 upstream source는 수정하지 않습니다.</li>
<li><strong>Guest 준비와 작은 launcher.</strong> boot disk는 Git 밖에 둡니다. default launcher의 12 GiB device를 그대로 실행하지 않습니다. guest 2 GiB·2 vCPU와 검토된 config를 사용합니다.</li>
<li><strong>Device 확인.</strong> <code>nvme list</code>, capacity, model/serial, partition/mount 상태로 boot disk와 FEMU namespace를 구분합니다. target을 확인하기 전 raw write를 하지 않습니다.</li>
<li><strong>Bounded sanity.</strong> fresh QEMU에서 작은 aligned write/read verification만 수행합니다. 아래 계획의 bytes와 native counter delta를 대조합니다. pattern 비교·aging·sweep은 하지 않습니다.</li>
<li><strong>자원과 상태 기록 후 중단.</strong> RSS·available RAM·swap activity·thread CPU·guest 결과를 JSON/log에 보존하고 HTML을 갱신합니다. Phase 2는 시작하지 않습니다.</li></ol>"""
    metrics_rows = [("host-write-pages", "native QMP / C0h offset 8", "host가 요청한 page 범위 수. aligned full-page 요청에서만 bytes = pages × page size"),
                    ("nand-write-pages", "native QMP / C0h offset 24", "host 쓰기에서 실제 프로그램한 모델 page; GC 제외"),
                    ("gc-write-pages", "native QMP / C0h offset 16", "GC로 복사한 모델 page"),
                    ("block-erases", "native QMP", "모델 block erase 누적. C0h에는 일반 erase counter 없음"),
                    ("Physical programs", "derived", "ΔNAND user pages + ΔGC pages. page size를 곱하면 bytes"),
                    ("Window WAF", "derived", "physical program delta / host page delta. host=0이면 미정의"),
                    ("FTL state", "native QMP summary / lines", "free/victim/full/open, valid/invalid pages와 line wear; 전체 L2P fingerprint는 아님")]
    windows_rows = [("OS", e(win["caption"] + " / " + win["version"])), ("CPU", e(win["cpu_model"].strip()) + f' / {win["physical_cores"]} cores / {win["logical_cpus"]} threads'),
                    ("Physical / available RAM", gib(win["total_physical_memory_bytes"]) + " / " + gib(win["available_memory_bytes"])),
                    ("Pagefile current usage", f'{win["pagefile_current_usage_mib"]:.0f} MiB; 활성 paging rate 측정 아님'),
                    ("C: 여유", gib(win["disk_free_bytes"])), ("Firmware virtualization", e(win["virtualization_firmware_enabled"]) + "; hypervisor가 일부 CPU flag를 가릴 수 있음")]
    wsl_rows = [("Ubuntu / kernel", e(wsl["distro"]["PRETTY_NAME"] + " / " + wsl["kernel"])), ("Virtualization", e(wsl["virtualization"])),
                ("/dev/kvm / kvm module", e(str(wsl["kvm_exists"])) + " / " + e(str(wsl["kvm_loaded"]))),
                ("RAM / available", gib(wsl["mem_total_bytes"]) + " / " + gib(wsl["mem_available_bytes"])),
                ("Swap used", gib(wsl["swap_total_bytes"] - wsl["swap_free_bytes"])),
                ("주의", "WSL filesystem의 virtual 여유가 Windows 물리 SSD 여유를 뜻하지는 않음")]
    lab_rows = [("OS / kernel", e(lab["distro"]["PRETTY_NAME"] + " / " + lab["kernel"])),
                ("CPU", e(lab["cpu_model"]) + f' / {lab["logical_cpus"]} logical CPUs'),
                ("물리 환경 / AMD-V", e(lab["virtualization"]) + " / " + e(lab["hardware_virtualization_flag"])),
                ("RAM / available", gib(lab["mem_total_bytes"]) + " / " + gib(lab["mem_available_bytes"])),
                ("KVM device / module", e(lab["kvm_exists"]) + " / " + e(lab["kvm_loaded"])),
                ("계정 KVM 접근", e(lab["kvm_access"]) + " · " + e(constraints["kvm_mode"]) + " · device group " + e(constraints["kvm_group"])),
                ("계정의 device group 소속", e(constraints["current_account_in_device_group"])),
                ("Dependency", "Python 3.10·gcc·Git 있음. pkg-config·GLib dev·ninja 등 미설치"),
                ("관측 시각 UTC", e(lab["captured_at_utc"])),
                ("작업 경계", "계정의 ledger 안에서만 파일 생성·변경. 공용 설정 변경 없음")]
    pages["phase-01.html"] = ("Phase 1 · 장비를 먼저 믿을 수 있게", "무엇을 하려고 했고, 어디까지 실제로 확인했는지 기록합니다. 플랫폼 준비를 연구 결과로 바꾸어 말하지 않습니다.", status +
        section("무엇을 하려고 했나 / 왜 필요한가", '<p>SSD를 작게 흉내 내는 장비를 만들고, OS가 쓴 양과 내부에서 처리한 양을 읽을 수 있게 하려 했습니다. 예를 들어 write가 성공해도 counter가 잘못 해석되면 이후 모든 그래프가 잘못될 수 있습니다. 그래서 본 실험 전에 작은 write/read와 수집 경로부터 확인합니다.</p>') +
        section("FEMU가 무엇인가", '<p>QEMU가 컴퓨터 전체를 흉내 내는 가상 컴퓨터라면 FEMU는 그 컴퓨터에 꽂힌 SSD를 자세히 흉내 내는 장치입니다. guest는 NVMe라는 장치 통신 규약으로 요청하고, FTL은 논리 주소를 NAND 위치로 바꿉니다.</p><div class="flow"><span>fio / guest Linux</span><b>→</b><span>NVMe</span><b>→</b><span>FEMU FTL / GC</span><b>→</b><span>NAND 작업 모델</span></div><p>⚠️ 데이터 bytes를 보관하는 DRAM 경로와 FTL/timing 경로는 구분됩니다. readback만으로 FTL bookkeeping이 옳다고 증명하지 않습니다. NVMe FEMU는 Raspberry Pi eMMC/SD의 protocol·controller·FTL과 다릅니다.</p>') +
        section("실제 집 환경 · 관측", table(["항목", "Windows snapshot"], windows_rows) + '<h3>설치된 Ubuntu는 WSL2</h3>' + table(["항목", "WSL snapshot"], wsl_rows) + '<p>숫자는 각 JSON의 capture timestamp 시점 관측입니다. QEMU 실행 중 resource 사용량이 아닙니다.</p><div class="callout">⚠️ 공식 upstream은 WSL을 지원하지 않습니다. /dev/kvm도 없으므로 여기서 dependency 설치·build를 하지 않았습니다.</div>') +
        section("연구실 서버 · 자동 SSH로 직접 관측", table(["항목", "읽기 전용 점검"], lab_rows) + '<div class="callout">⚠️ 장비 사양은 충분하지만 현재 계정의 KVM 권한이 없습니다. 가상환경만으로 해결되지 않습니다. 사용자의 공용 설정 변경 금지 지시에 따라 실행을 보류합니다.</div><p>' + link("../records/lab-preflight.json", "환경 JSON") + ' · ' + link("../records/lab-constraints.json", "접근 권한·dependency JSON") + '</p>') +
        section("Source 확보와 설정 후보", '<p>공식 upstream을 <code>external/FEMU</code>에 분리해 clean detached checkout했습니다. pin: <code>' + e(record["femu_commit"]) + '</code>. 프로젝트 Git에는 source 전체 대신 lock을 넣습니다.</p>' + table(["항목", "후보 값 · runtime 미검증"], geometry_rows) + '<p>4 GiB raw flash 중 3 GiB만 OS에 보이고 나머지를 내부 spare로 남깁니다. GC는 살아 있는 데이터를 옮길 빈 공간이 필요하기 때문입니다. 채널을 줄이면 GC line과 병렬성이 달라지므로 실제 edge를 복제했다고 주장하지 않습니다.</p><p>이 explicit-capacity 설정의 DRAM data backend는 exposed size이고 raw spare는 FTL 모델의 공간입니다. 메모리 계획과 raw NAND 용량을 같은 숫자로 읽지 않습니다.</p>') +
        section("무엇을 설치/실행했나", table(["작업·metric", "현재 기록"], runtime_rows) + '<p>Python stdlib를 이용한 config 계산·문서 생성·오프라인 테스트는 FEMU build나 benchmark가 아닙니다.</p>') +
        section("Sanity test · 아직 실행하지 않음", f'<p>ID <code>{e(config["sanity_plan"]["id"])}</code>. 예정량은 {config["sanity_plan"]["write_bytes"] // 1024**2} MiB / {config["sanity_plan"]["block_size_bytes"]} bytes / QD {config["sanity_plan"]["iodepth"]} / job {config["sanity_plan"]["numjobs"]}입니다. fresh aligned 상태라면 host delta {geom["sanity_host_pages"]:,} pages, GC/erase=0, window WAF≈1을 기대합니다. 이 값들은 <strong>예상치이며 측정치가 아닙니다.</strong></p><p>write/read 성공·data verification·native delta 일치·오류 없음을 확인합니다. 통과해도 E0의 pattern 차이나 GC 현상을 검증한 것은 아닙니다.</p>') +
        section("Native metric 경로 · source 확인, runtime 미확인", table(["Metric", "수집 위치/분류", "뜻"], metrics_rows) + '<p><code>query-femu</code>는 일관된 한 namespace 상태를 FTL thread에서 복사합니다. 여러 페이지에 나눈 line query는 하나의 전체 snapshot이 아닐 수 있습니다. 수집 자체도 FTL thread 시간을 쓰므로 빈도를 기록합니다.</p>') +
        section("연구실 연결과 오류", '<p>' + e(record["remote_connection"]["summary"]) + '</p>' + table(["문제", "선택한 대응", "상태"], [(e(i["problem"]), e(i["action"]), e(i["status"])) for i in record["issues"]])) +
        section("물리 Linux에서 재개하는 순서", resume) +
        section("Phase 2로 넘어가도 되는가", '<p><strong>아직 아닙니다.</strong> build·guest·sanity·native counter·runtime resource가 확인돼야 Phase 1 완료입니다. 사용자 검토 전에는 Phase 2로 넘어가지 않습니다.</p>' + table(["경로", "현재 판단"], [("집 현재 WSL", e(record["feasibility"]["home_current_wsl"])), ("집 물리 Linux", e(record["feasibility"]["home_native_linux"])), ("연구실", e(record["feasibility"]["lab"]))]) + '<p>' + e(record["feasibility"]["note"]) + '</p>'))
    entries = []
    for activity in record["activities"]:
        body = '<p>' + e(activity["result"]) + '</p>' + table(["Metadata", "값"], [("시각", e(stamp) + " · 준비 기록 capture 시각, 개별 workload 시각 아님"), ("Git commit at capture", '<code>' + e(record["project_commit_at_capture"]) + '</code> · dirty=' + e(record["project_dirty_at_capture"])), ("FEMU", '<code>' + e(record["femu_commit"]) + '</code>'), ("Config hash", '<code>' + e(record["config_sha256"]) + '</code>'), ("Workload", "sanity 미실행 / research workload 없음"), ("Artifacts", ' · '.join(link("../" + p, p) for p in activity["artifacts"]) or "없음"), ("다음 행동", "공용 설정을 바꾸지 않는 실행 경로 확보 → Phase 1 재개")])
        entries.append(section(activity["id"] + " · " + activity["status"], body))
    pages["experiment-log.html"] = ("실험 기록 · 관측과 준비를 구분", "JSON/CSV/log가 source of truth입니다. HTML은 사람이 읽는 설명입니다. 아직 연구 실험 결과는 없고, 아래는 Phase 1 준비 기록입니다.", ''.join(entries))
    pages["decision-log.html"] = ("결정의 이유를 남깁니다", "결정은 바뀔 수 있습니다. 바뀌면 삭제하지 않고 superseded와 새 결정을 연결합니다.", ''.join(section(d["id"] + " · " + d["title"], '<span class="tag">' + e(d["status"]) + '</span><h3>이유</h3><p>' + e(d["reason"]) + '</p><h3>대안</h3><p>' + e(d["alternatives"]) + '</p><h3>현재 선택하지 않은 이유</h3><p>' + e(d["why_not"]) + '</p>') for d in research["decisions"]) + section("새로운 질문을 발견하면", bullets(research["new_questions"])))
    terms = [
        ("NAND flash", "전원이 꺼져도 데이터를 보관하는 메모리입니다. SSD/eMMC/SD 안에서 쓰이지만 controller와 protocol은 다릅니다."),
        ("Page · 페이지", "FTL/NAND 모델에서 프로그램하는 작은 단위입니다. 이 후보는 4 KiB입니다. OS memory page와 같은 이름이어도 의미를 구분합니다."),
        ("Block · 블록", "여러 NAND page를 묶은 소거 단위입니다. 이 후보는 256 pages = 1 MiB입니다. 모든 실제 flash가 이 크기는 아닙니다."),
        ("Program / write", "빈 NAND page에 데이터를 기록하는 동작입니다. OS가 같은 주소를 덮어써도 FTL은 보통 다른 빈 page에 새로 씁니다."),
        ("Erase · 소거", "NAND block 전체를 지워 다시 쓸 수 있게 만드는 동작입니다. 파일 삭제와 같은 동작이 아닙니다."),
        ("P/E cycle", "한 block이 program/erase를 반복하는 횟수입니다. 누적 소거는 마모의 대리 지표지만 수명은 매체·분포·controller 등에도 의존합니다."),
        ("FTL", "Flash Translation Layer. OS의 논리 주소를 NAND의 물리 위치로 연결하고, 갱신·GC·공간을 관리합니다."),
        ("LBA", "Logical Block Address. OS가 장치에 요청할 때 쓰는 논리 주소입니다. 실제 NAND 위치가 직접 드러나는 주소는 아닙니다."),
        ("Garbage collection · GC", "빈 공간을 만들기 위해 살아 있는 page를 옮기고 기존 block을 지우는 작업입니다. 우리가 쓴 것 외에 내부 복사 쓰기가 생깁니다."),
        ("Valid / invalid page", "valid는 아직 최신 데이터입니다. 같은 논리 주소에 새 데이터를 쓰면 예전 사본은 invalid가 됩니다. invalid여도 block 전체를 지우기 전에는 즉시 빈 page가 아닙니다."),
        ("Write amplification · WAF", "내부 physical writes / host logical writes. host가 1 GiB 쓰고 내부가 복사까지 2 GiB 프로그램하면 WAF=2입니다. 이것은 설명 예시이며 측정치가 아닙니다."),
        ("Over-provisioning · OP", "OS에 보이지 않는 spare 공간입니다. raw 4 / logical 3이면 raw spare=25%, logical 기준 OP=33.33%로 분모가 다릅니다."),
        ("Fill ratio", "공간이 얼마나 차 있는지 나타내는 비율입니다. filesystem 사용량, live mapped / logical capacity, live mapped / raw capacity를 구분해야 합니다."),
        ("Logical write", "host가 장치에 요청한 쓰기입니다. application bytes는 page cache에서 합쳐지거나 버려져 device bytes와 다를 수 있습니다."),
        ("Physical write", "NAND에 실제 또는 모델상 프로그램한 양입니다. 여기서는 host 원본과 GC 복사를 합한 FEMU 모델 값이며 하드웨어 측정이 아닙니다."),
        ("NVMe", "host와 저장장치가 요청을 주고받는 규약입니다. NAND 종류나 FTL 정책 자체를 뜻하지 않습니다."),
        ("QEMU", "CPU·메모리·장치를 가진 가상 컴퓨터를 실행하는 소프트웨어입니다. guest는 그 안에서 실행하는 OS입니다."),
        ("KVM / AMD-V", "KVM은 Linux에서 CPU 가상화를 사용하는 기능이고 AMD-V/SVM은 CPU/firmware 지원입니다. WSL에서 flag가 안 보여도 물리 BIOS가 꺼졌다고 단정하지 않습니다."),
        ("FEMU", "QEMU에 SSD 모델을 더한 도구입니다. 실제 NAND 대신 host DRAM을 쓰고 FTL/NAND 작업과 시간을 모델링합니다."),
        ("BlackBox SSD", "guest는 일반 block device로 쓰고 장치 쪽 FTL이 위치와 GC를 관리하는 모드입니다. 연구자는 emulator 내부 counter를 관측할 수 있습니다."),
        ("GC line / superblock", "여러 channel/LUN의 block을 묶어 회수하는 FEMU 단위입니다. 이 후보는 16 blocks = 16 MiB라 물리 block erase와 GC 한 번은 다릅니다."),
        ("KV cache", "LLM이 이미 처리한 문맥의 계산 중간값입니다. 다음 token 계산에 재사용합니다. 모델 가중치나 학습 gradient가 아닙니다."),
        ("Re-prefill", "저장된 KV가 없을 때 이전 문맥 token을 다시 처리해 KV를 만드는 계산입니다. storage를 줄이는 대신 CPU 시간·첫 응답 지연이 늘 수 있습니다."),
        ("TTFT / SLO", "TTFT는 요청 후 첫 token까지의 시간이고 SLO는 서비스가 지켜야 할 목표입니다. 평균이 괜찮아도 느린 요청 p99가 목표를 넘을 수 있습니다."),
        ("Sanity / research result", "sanity는 장비가 제대로 쓰고 읽는지 확인하는 작은 점검입니다. 패턴 차이·수명 위험을 입증하는 본 실험과 다릅니다.")]
    pages["glossary.html"] = ("용어 사전 · 그림 없이도 이해하기", "전문용어를 만날 때 다시 돌아올 수 있는 설명입니다. 수치 예시는 config에서 유래하거나 교육용이며 연구 결과가 아닙니다.", '<div class="terms">' + ''.join('<article><h2>' + e(name) + '</h2><p>' + e(desc) + '</p></article>' for name, desc in terms) + '</div>')
    refs = '<details><summary>공식 출처 · 고정 commit</summary><ul>' + ''.join('<li>' + link(r["url"], r["topic"]) + '</li>' for r in record["references"]) + '</ul></details>'
    for filename, (title, lead, content) in pages.items():
        nav = '<nav aria-label="연구 노트">' + ''.join('<a' + (' class="active" aria-current="page"' if file == filename else '') + ' href="' + file + '">' + label + '</a>' for file, label in NAV) + '</nav>'
        out = '<!doctype html>\n<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + e(title) + ' | LEDGER 연구 노트</title><style>' + CSS + '</style></head><body><div class="shell"><div class="top"><span class="brand">LEDGER / EXPLORATION</span><span>기록 시각 ' + stamp + '</span></div>' + nav + '<header><div class="eyebrow">RESEARCH NOTE · PROVISIONAL</div><h1>' + e(title) + '</h1><p class="lead">' + e(lead) + '</p></header><main>' + content + '</main><footer><p>생성 원본: records/*.json · config. HTML은 설명 layer이며 실측 원본은 JSON/CSV/log입니다. 기존 연구 HTML은 별도 원본입니다.</p>' + refs + '</footer></div></body></html>\n'
        (ROOT / "docs" / filename).write_text(out, encoding="utf-8")
    print(f"Generated {len(pages)} self-contained notes.")


if __name__ == "__main__":
    render()
