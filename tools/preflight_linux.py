"""Read-only Linux eligibility probe; does not install, build, boot or benchmark."""
import argparse
import datetime as dt
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path


def command(argv):
    if not shutil.which(argv[0]):
        return {"argv": argv, "exit_code": None, "stdout": None, "stderr": "not installed"}
    try:
        run = subprocess.run(argv, capture_output=True, text=True, timeout=15)
        return {"argv": argv, "exit_code": run.returncode,
                "stdout": run.stdout.strip(), "stderr": run.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"argv": argv, "exit_code": None, "stdout": None, "stderr": str(exc)}


def evaluate(info, required_available_bytes=8 * 1024**3):
    blockers = []
    if info["system"] != "Linux":
        blockers.append("physical Linux required")
    if "microsoft" in info["kernel"].lower() or info["virtualization"] == "wsl":
        blockers.append("WSL is unsupported by FEMU upstream")
    elif info["virtualization"] not in ("none", "physical"):
        blockers.append("physical host not established; nested virtualization is not accepted")
    if info["architecture"] != "x86_64":
        blockers.append("x86_64 required")
    if not info["kvm_exists"] or not info["kvm_access"]:
        blockers.append("/dev/kvm missing or not readable/writable")
    if not info["hardware_virtualization_flag"]:
        blockers.append("svm/vmx not exposed; physical BIOS state cannot be inferred from a VM")
    if not info["kvm_loaded"]:
        blockers.append("kvm module not visible")
    if info["mem_available_bytes"] is None or info["mem_available_bytes"] < required_available_bytes:
        blockers.append("less than 8 GiB available for the selected profile and headroom")
    return {"eligible": not blockers, "blockers": blockers,
            "required_available_bytes": required_available_bytes}


def collect():
    cpu = Path("/proc/cpuinfo").read_text() if Path("/proc/cpuinfo").exists() else ""
    flags = next((line.split(":", 1)[1].split() for line in cpu.splitlines() if line.startswith("flags")), [])
    memory = {}
    if Path("/proc/meminfo").exists():
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, rest = line.split(":", 1)
            memory[key] = int(rest.split()[0]) * 1024
    virt = command(["systemd-detect-virt"])
    virtualization = virt["stdout"] or "unknown"
    distro = {}
    if Path("/etc/os-release").exists():
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                key, val = line.split("=", 1)
                if key in ("ID", "VERSION_ID", "PRETTY_NAME"):
                    distro[key] = val.strip('"')
    info = {
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "system": platform.system(), "kernel": platform.release(),
        "architecture": platform.machine(), "distro": distro,
        "virtualization": virtualization,
        "cpu_model": next((line.split(":", 1)[1].strip() for line in cpu.splitlines() if line.startswith("model name")), None),
        "logical_cpus": os.cpu_count(), "hardware_virtualization_flag": bool({"svm", "vmx"}.intersection(flags)),
        "kvm_exists": Path("/dev/kvm").exists(),
        "kvm_access": os.access("/dev/kvm", os.R_OK | os.W_OK),
        "kvm_loaded": Path("/sys/module/kvm").exists(),
        "kvm_amd_loaded": Path("/sys/module/kvm_amd").exists(),
        "mem_total_bytes": memory.get("MemTotal"),
        "mem_available_bytes": memory.get("MemAvailable"),
        "swap_total_bytes": memory.get("SwapTotal"),
        "swap_free_bytes": memory.get("SwapFree"),
        "disk_free_bytes": shutil.disk_usage("/").free if platform.system() == "Linux" else None,
        "packages": {name: command(argv) for name, argv in {
            "python": ["python3", "--version"], "glib": ["pkg-config", "--modversion", "glib-2.0"],
            "gcc": ["gcc", "-dumpfullversion"], "ninja": ["ninja", "--version"],
            "git": ["git", "--version"], "fio": ["fio", "--version"],
            "nvme": ["nvme", "version"]}.items()},
        "interpretation": "environment probe only; no FEMU or fio workload was run"
    }
    info["gate"] = evaluate(info)
    return info


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    info = collect()
    encoded = json.dumps(info, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)
    raise SystemExit(0 if info["gate"]["eligible"] else 2)
