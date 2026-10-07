"""Execute a reviewed local script in a new authenticated SSH session; save output locally."""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.remote_probe import ssh_command

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--script', type=Path, required=True)
    parser.add_argument('--interpreter', choices=['python3', 'bash'], default='python3')
    parser.add_argument('--transport', choices=['native', 'wsl'], default='wsl')
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    script = args.script.read_bytes().replace(b'\r\n', b'\n')
    command = [*ssh_command(args.host, args.transport), args.interpreter]
    command += ['-I', '-'] if args.interpreter == 'python3' else ['-s']
    result = subprocess.run(command, input=script, capture_output=True, timeout=args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result.stdout)
    if result.returncode:
        error = args.output.with_suffix(args.output.suffix + '.stderr')
        error.write_bytes(result.stderr)
        print('Remote command failed. Inspect the private output files; do not publish credentials/paths.')
    else:
        print('Remote script completed; output saved locally.')
    raise SystemExit(result.returncode)
