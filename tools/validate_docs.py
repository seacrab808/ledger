"""Check generated offline documents, original hashes and local links."""
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["index.html", "research-map.html", "phase-01.html", "experiment-log.html", "decision-log.html", "glossary.html"]


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
    if errors:
        raise ValueError("\n".join(errors))
    print("6 HTML notes: offline assets, Korean layout, local links, original hashes and config provenance pass.")


if __name__ == "__main__":
    validate()
