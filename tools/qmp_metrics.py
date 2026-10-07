"""Read native FEMU QMP counters; never issues guest I/O or resets the device."""
import argparse
import datetime as dt
import json
import socket
from pathlib import Path

KEYS = ("host-write-pages", "nand-write-pages", "gc-write-pages", "block-erases")


def namespace(reply, nsid=1):
    body = reply.get("return", reply)
    if "error" in reply:
        raise ValueError(f"QMP error: {reply['error']}")
    matches = [n for n in body["namespaces"] if n["nsid"] == nsid]
    if len(matches) != 1 or matches[0]["mode"] != "bbssd":
        raise ValueError("exactly one matching BlackBox namespace required")
    item = matches[0]
    if item["geometry"]["page-size"] <= 0:
        raise ValueError("invalid page size")
    for key in KEYS:
        if type(item["counters"][key]) is not int or item["counters"][key] < 0:
            raise ValueError(f"invalid native counter: {key}")
    return item


def delta_metrics(before, after, nsid=1):
    a, b = namespace(before, nsid), namespace(after, nsid)
    if a["geometry"] != b["geometry"]:
        raise ValueError("geometry changed across snapshots")
    delta = {key: b["counters"][key] - a["counters"][key] for key in KEYS}
    if any(v < 0 for v in delta.values()):
        raise ValueError("counter decreased: possible reset or mixed devices")
    host = delta["host-write-pages"]
    physical = delta["nand-write-pages"] + delta["gc-write-pages"]
    page_size = b["geometry"]["page-size"]
    return {"native_counter_deltas": delta, "physical_program_pages": physical,
            "modeled_physical_write_bytes": physical * page_size,
            "host_page_covered_bytes": host * page_size,
            "waf_pages": physical / host if host else None,
            "block_erases": delta["block-erases"],
            "note": "Host page-covered bytes equal logical bytes only for aligned full-page requests. No hardware claim."}


def snapshot(socket_path, nsid=1):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(10)
        client.connect(str(socket_path))
        with client.makefile("rwb") as stream:
            greeting = json.loads(stream.readline())
            if "QMP" not in greeting:
                raise ValueError("not a QMP socket")
            def request(command, ident, arguments=None):
                payload = {"execute": command, "id": ident}
                if arguments:
                    payload["arguments"] = arguments
                stream.write((json.dumps(payload) + "\n").encode())
                stream.flush()
                while True:
                    line = stream.readline()
                    if not line:
                        raise ValueError("QMP closed before response")
                    response = json.loads(line)
                    if response.get("id") == ident:
                        if "error" in response:
                            raise ValueError(response["error"])
                        return response
            request("qmp_capabilities", "capabilities")
            result = request("query-femu", "counters", {"nsid": nsid, "kind": "summary"})
            namespace(result, nsid)
            return {"captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "source": "FEMU native QMP query-femu", "measurement_kind": "emulator-internal",
                    "reply": result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--nsid", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = snapshot(args.socket, args.nsid)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Native snapshot saved: {args.output}")
