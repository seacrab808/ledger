"""Check generated offline documents, original hashes and local links."""
import hashlib
import json
import math
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PAGES = ["index.html", "research-map.html", "phase-01.html", "phase-02.html", "experiment-log.html", "decision-log.html", "glossary.html"]


def same_summary(a, b):
    """Exact structure/integers; tolerate insignificant Python-version float rounding."""
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_summary(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same_summary(x, y) for x, y in zip(a, b))
    return a == b


class Check(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = []
        self.lang = None
        self.styles = 0
        self.h1s = 0
        self.dependencies = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html": self.lang = a.get("lang")
        if tag == "style": self.styles += 1
        if tag == "h1": self.h1s += 1
        if "id" in a: self.ids.append(a["id"])
        if tag == "a" and "href" in a: self.links.append(a["href"])
        if tag in ("script", "img", "iframe", "link"):
            self.dependencies.append((tag, a.get("src") or a.get("href")))


def validate():
    errors = []
    for filename in PAGES:
        path = ROOT / "docs" / filename
        check = Check()
        source = path.read_text(encoding="utf-8")
        check.feed(source)
        if check.lang != "ko" or check.styles != 1 or check.h1s != 1:
            errors.append(f"{filename}: missing Korean language / inline CSS / one main heading")
        if check.dependencies:
            errors.append(f"{filename}: document must not require external assets")
        if len(check.ids) != len(set(check.ids)):
            errors.append(f"{filename}: duplicate ids")
        for href in check.links:
            url = urlsplit(href)
            if url.scheme or url.netloc or not url.path:
                continue
            target = (path.parent / unquote(url.path)).resolve()
            if not target.is_relative_to(ROOT) or not target.is_file():
                errors.append(f"{filename}: broken or outside-root link {href}")
    record = json.loads((ROOT / "records/phase-01.json").read_text(encoding="utf-8"))
    for item in record["source_documents"]:
        actual = hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
        if actual != item["sha256"]:
            errors.append("Historical HTML changed: " + item["path"])
    config_hash = hashlib.sha256((ROOT / "configs/femu/blackbox-small.json").read_bytes()).hexdigest()
    if config_hash != record["config_sha256"]:
        errors.append("Config hash and record mismatch")
    runtime_path = ROOT / 'records/phase-01-runtime.json'
    if runtime_path.exists():
        from tools.qmp_metrics import delta_metrics
        run = json.loads(runtime_path.read_text(encoding='utf-8'))
        executed_path = ROOT / 'records/phase-01-executed-config.json'
        if hashlib.sha256(executed_path.read_bytes()).hexdigest() != run['config_sha256']:
            errors.append('Executed config hash mismatch')
        computed = delta_metrics(run['native_before']['reply'], run['native_after']['reply'])
        if computed != run['metrics']:
            errors.append('Derived counter metrics disagree with native snapshots')
        if computed['host_page_covered_bytes'] != run['fio']['jobs'][0]['write']['io_bytes']:
            errors.append('Aligned host page bytes disagree with fio')
        expected = json.loads(executed_path.read_text(encoding='utf-8'))
        for field, config_key in [('channels', 'nchs'), ('luns-per-channel', 'luns_per_ch'),
                                  ('planes-per-lun', 'pls_per_lun'), ('blocks-per-plane', 'blks_per_pl'),
                                  ('pages-per-block', 'pgs_per_blk')]:
            if run['native_after']['reply']['return']['namespaces'][0]['geometry'][field] != expected['device'][config_key]:
                errors.append('Realized geometry mismatch: ' + field)
    if (ROOT / 'records/phase-02-summary.json').exists():
        from tools.summarize_phase2 import summarize
        batch_path = ROOT / 'records/phase-02-pilot.json'
        summary = json.loads((ROOT / 'records/phase-02-summary.json').read_text(encoding='utf-8'))
        batch = json.loads(batch_path.read_text(encoding='utf-8'))
        if not same_summary(summarize(batch), {k: v for k, v in summary.items() if k != 'input_sha256'}):
            errors.append('Phase 2 recomputed summary differs from archived summary')
        if hashlib.sha256(batch_path.read_bytes()).hexdigest() != summary['input_sha256']:
            errors.append('Phase 2 raw input hash mismatch')
        plan = ROOT / 'configs/experiments/phase2-pilot.json'
        if hashlib.sha256(plan.read_bytes()).hexdigest() != batch['plan_sha256']:
            errors.append('Phase 2 plan hash mismatch')
        if config_hash != batch['config_sha256']:
            errors.append('Phase 2 device config hash mismatch')
    if (ROOT / 'records/phase-02-steady-summary.json').exists():
        from tools.summarize_steady import summarize as summarize_steady
        raw_path = ROOT / 'records/phase-02-steady.json'
        raw = json.loads(raw_path.read_text(encoding='utf-8'))
        steady = json.loads((ROOT / 'records/phase-02-steady-summary.json').read_text(encoding='utf-8'))
        pilot = json.loads((ROOT / 'records/phase-02-pilot.json').read_text(encoding='utf-8'))
        if not same_summary(summarize_steady(raw, pilot), {k: v for k, v in steady.items() if k != 'input_sha256'}):
            errors.append('Long-run summary differs from actual native windows')
        if hashlib.sha256(raw_path.read_bytes()).hexdigest() != steady['input_sha256']:
            errors.append('Long-run raw input hash mismatch')
        if hashlib.sha256((ROOT / 'configs/experiments/phase2-steady.json').read_bytes()).hexdigest() != raw['plan_sha256']:
            errors.append('Long-run frozen plan hash mismatch')
        if config_hash != raw['config_sha256'] or raw['qemu_sha256'] != pilot['qemu_sha256']:
            errors.append('Long-run device or binary changed')
    if errors:
        raise ValueError("\n".join(errors))
    print("7 HTML notes: offline assets, Korean layout, local links, original hashes and config/measurement provenance pass.")


if __name__ == "__main__":
    validate()
