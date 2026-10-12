"""Supervise only the experiment's own process group, with fixed shared-server budgets."""
import argparse
import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import time

BASE = Path('/home/miruware/ledger/artifacts/lmcache-runtime')

def footprint():
    total = 0
    for directory, _, names in os.walk(BASE, followlinks=False):
        for name in names:
            p = Path(directory)/name
            try:
                if not p.is_symlink():
                    total += p.stat().st_size
            except FileNotFoundError:
                pass  # pip removes/renames its own temporary files
    return total

def members(group):
    result = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if os.getpgid(int(entry.name)) != group:
                continue
            fields = (entry/'status').read_text().splitlines()
            rss = next((int(x.split()[1])*1024 for x in fields if x.startswith('VmRSS:')), 0)
            result[int(entry.name)] = rss
        except (OSError, ProcessLookupError, StopIteration):
            pass
    return result

def gpu_memory(pids):
    r = subprocess.run(['nvidia-smi', '--query-compute-apps=pid,used_memory',
                        '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=10)
    if r.returncode:
        raise RuntimeError('GPU monitor unavailable')
    total = 0
    for line in r.stdout.splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts)==2 and parts[0].isdigit() and int(parts[0]) in pids:
            if not parts[1].isdigit():
                raise RuntimeError('GPU memory unavailable for owned process')
            total += int(parts[1])*2**20
    return total

def run(command, label):
    os.nice(10)
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    before = footprint()
    status = {'label': label, 'started_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'RSS_limit': 8*2**30, 'GPU_limit': 4*2**30, 'artifact_limit': 10*2**30,
              'address_space': 'default; user-approved GPU virtual-address exception',
              'max_RSS': 0, 'max_GPU': 0, 'max_artifact_bytes': before,
              'command': command, 'status': 'running'}
    output = BASE/(label+'.status.json')
    with (BASE/(label+'.log')).open('w') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True, cwd=BASE)
        status['pid'] = process.pid
        try:
            disk = before
            disk_checked = 0.0
            while process.poll() is None:
                pids = members(process.pid)
                rss = sum(pids.values())
                gpu = gpu_memory(pids)
                if time.monotonic()-disk_checked>=10:
                    disk = footprint()
                    disk_checked = time.monotonic()
                status['max_RSS'] = max(status['max_RSS'], rss)
                status['max_GPU'] = max(status['max_GPU'], gpu)
                status['max_artifact_bytes'] = max(status['max_artifact_bytes'], disk)
                output.write_text(json.dumps(status, indent=2))
                if rss>8*2**30 or gpu>4*2**30 or disk>10*2**30:
                    raise RuntimeError('Owned experiment exceeded fixed resource budget')
                time.sleep(1)
            status['exit_code'] = process.returncode
            status['status'] = 'completed' if process.returncode==0 else 'failed'
        except Exception as exc:
            status['status'] = 'stopped-by-guard'
            status['reason'] = str(exc)
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        status['ended_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        output.write_text(json.dumps(status, indent=2))
    return status

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('command',nargs=argparse.REMAINDER)
    args=p.parse_args()
    if not args.command or not args.label.replace('-','').isalnum():
        raise SystemExit('Invalid guard arguments')
    result=run(args.command,args.label)
    raise SystemExit(0 if result['status']=='completed' else 1)
