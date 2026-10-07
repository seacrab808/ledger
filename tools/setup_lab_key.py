"""Interactive public-key registration. SSH, not Python, prompts for the password."""
import argparse
import re
import subprocess
from pathlib import Path


def payload(public_key):
    match = re.fullmatch(r"ssh-ed25519[ \t]+([A-Za-z0-9+/=]+)(?:[ \t]+[^\r\n]*)?", public_key.strip())
    if not match:
        raise ValueError("Expected one ed25519 public key")
    # Keep only a validated base64 key and a fixed comment; never shell-interpolate user comments.
    key = "ssh-ed25519 " + match.group(1) + " ledger-phase1"
    return ("set -eu\numask 077\nmkdir -p \"$HOME/.ssh\"\n"
            "touch \"$HOME/.ssh/authorized_keys\"\n"
            "chmod 700 \"$HOME/.ssh\"\nchmod 600 \"$HOME/.ssh/authorized_keys\"\n"
            f"key='{key}'\n"
            "grep -qxF \"$key\" \"$HOME/.ssh/authorized_keys\" || "
            "printf '\\n%s\\n' \"$key\" >> \"$HOME/.ssh/authorized_keys\"\n"
            "printf '%s\\n' 'Public key registered; existing keys preserved.'\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.host):
        parser.error("Use a configured SSH host alias")
    script = payload(args.public_key.read_text(encoding="utf-8"))
    # Script bytes go through stdin with LF, not through Windows native command-line quoting.
    # Do not capture output: SSH must prompt in the user's terminal.
    result = subprocess.run(["ssh", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15",
                             args.host, "sh", "-s"], input=script.encode("utf-8"))
    raise SystemExit(result.returncode)
