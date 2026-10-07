"""Run the read-only Linux probe through an existing authenticated SSH alias."""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def wsl_path(path):
    value = Path(path).resolve().as_posix()
    if not re.match(r"^[A-Za-z]:/", value):
        raise ValueError("WSL transport requires a Windows drive path")
    return "/mnt/" + value[0].lower() + value[2:]


def ssh_command(alias, transport="native", distro="Ubuntu"):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", alias):
        raise ValueError("Expected configured SSH alias")
    options = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "ConnectTimeout=15"]
    if transport == "native":
        return ["ssh", *options, alias]
    if os.name != "nt":
        raise ValueError("WSL transport is for a Windows client")
    home = subprocess.check_output(["wsl", "-d", distro, "--", "printenv", "HOME"], text=True).strip()
    if not home.startswith("/") or "\n" in home:
        raise ValueError("Invalid WSL home")
    config = Path.home() / ".ssh/config"
    known = Path.home() / ".ssh/known_hosts"
    return ["wsl", "-d", distro, "--", "env", "SSH_AUTH_SOCK=" + home + "/.ssh/ledger-agent.sock",
            "ssh", "-F", wsl_path(config), "-o", "UserKnownHostsFile=" + wsl_path(known),
            *options, alias]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Private SSH alias; never written into result")
    parser.add_argument("--transport", choices=["native", "wsl"], default="native")
    parser.add_argument("--wsl-distro", default="Ubuntu")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    script = (ROOT / "tools/preflight_linux.py").read_bytes().replace(b"\r\n", b"\n")
    command = ssh_command(args.host, args.transport, args.wsl_distro)
    run = subprocess.run([*command, "python3", "-"], input=script, capture_output=True, timeout=120)
    if run.returncode not in (0, 2):
        raise SystemExit("Remote probe did not execute successfully; private SSH stderr omitted.")
    try:
        info = json.loads(run.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SystemExit("No valid probe JSON returned; SSH/banner output omitted.")
    if "gate" not in info:
        raise SystemExit("Unexpected remote result")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info, ensure_ascii=False, indent=2))
    raise SystemExit(0 if info["gate"]["eligible"] else 2)
