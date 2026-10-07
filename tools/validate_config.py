"""Offline geometry audit; never starts a VM or touches a device."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "configs/femu/blackbox-small.json"


def audit(config):
    d = config["device"]
    geometry = ["secsz", "secs_per_pg", "pgs_per_blk", "blks_per_pl",
                "pls_per_lun", "luns_per_ch", "nchs"]
    for key in geometry:
        if type(d[key]) is not int or d[key] <= 0:
            raise ValueError(f"positive integer geometry required: {key}")
    if d["femu_mode"] != 1 or d["namespaces"] != 1:
        raise ValueError("Phase 1 requires one BlackBox namespace")
    if d["op_pcent"] != 0:
        raise ValueError("this audited profile uses explicit devsz_mb, not op_pcent")
    if config["placement"]["fdp"] or config["placement"]["subsystem"]:
        raise ValueError("placement must be disabled")
    for key in ["streams", "hot_cold_sep", "ns_mgmt", "power_loss",
                "buffer_size", "read_cache_mb", "mapping_cache_mb",
                "read_reclaim_limit", "retention_limit_sec"]:
        if d[key]:
            raise ValueError(f"Phase 1 baseline requires {key}=off/0")
    if d["mapping"] != "page" or d["gc_policy"] != "greedy":
        raise ValueError("baseline must use page mapping / greedy GC")
    if not 1 <= d["gc_thres_pcent"] <= d["gc_thres_pcent_high"] < 100:
        raise ValueError("invalid GC thresholds")
    page = d["secsz"] * d["secs_per_pg"]
    block = page * d["pgs_per_blk"]
    blocks_per_line = d["nchs"] * d["luns_per_ch"] * d["pls_per_lun"]
    line = block * blocks_per_line
    raw = line * d["blks_per_pl"]
    exposed = d["devsz_mb"] * 1024**2
    if not 0 < exposed < raw or exposed % page:
        raise ValueError("namespace must be page-aligned and smaller than raw NAND")
    # Same truncation as bb_gc_forced_lines for this page/greedy/non-stream profile.
    reserve_lines = int((1 - d["gc_thres_pcent_high"] / 100) * d["blks_per_pl"]) + 1
    if exposed > raw - reserve_lines * line:
        raise ValueError("insufficient spare lines for configured GC reserve")
    if config["sanity_plan"]["write_bytes"] % page:
        raise ValueError("sanity bytes must be page-aligned")
    if config["sanity_plan"]["write_bytes"] >= line * 2:
        raise ValueError("sanity must be a bounded check, not an aging workload")
    return {
        "page_bytes": page, "block_bytes": block, "blocks_per_line": blocks_per_line,
        "line_bytes": line, "line_count": d["blks_per_pl"],
        "raw_bytes": raw, "exposed_bytes": exposed, "spare_bytes": raw - exposed,
        "raw_spare_fraction": (raw - exposed) / raw,
        "logical_op_fraction": (raw - exposed) / exposed,
        "gc_background_free_line_threshold": int((1 - d["gc_thres_pcent"] / 100) * d["blks_per_pl"]),
        "gc_foreground_free_line_threshold": reserve_lines - 1,
        "backend_mib": d["devsz_mb"],
        "estimated_process_budget_mib": d["devsz_mb"] + config["guest"]["ram_mib"] + 1024,
        "sanity_host_pages": config["sanity_plan"]["write_bytes"] // page,
        "validation": "offline arithmetic only; FEMU realize/boot not tested"
    }


def device_argument(config):
    audit(config)
    def value(v):
        return "on" if v is True else "off" if v is False else str(v)
    return "femu,id=femu0," + ",".join(f"{k}={value(v)}" for k, v in config["device"].items())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT)
    parser.add_argument("--device-argument", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    print(device_argument(cfg) if args.device_argument else json.dumps(audit(cfg), indent=2))
