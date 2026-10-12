"""Relay immutable checksum-verified wheels with at most one remote wheel retained."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.remote_probe import ssh_command, wsl_path

def remote(host, code):
    r=subprocess.run([*ssh_command(host,'wsl'),'python3','-I','-'],input=code,
                     text=True,encoding='utf-8',capture_output=True,timeout=45)
    if r.returncode:raise RuntimeError('Private remote relay command failed')
    return r.stdout.strip()

def copy(host, source, target):
    command=ssh_command(host,'wsl'); at=command.index('ssh');command[at]='scp'
    r=subprocess.run([*command[:-1],'-q',wsl_path(source),host+':'+target],capture_output=True,timeout=600)
    if r.returncode:raise RuntimeError('Private SCP failed')

def run(host):
    lock=json.loads((ROOT/'external/lmcache-runtime.lock.json').read_text())
    base=ROOT/'artifacts/lmcache-relay';base.mkdir(exist_ok=True)
    packages=sorted(lock['packages'],key=lambda x:x['wheel_bytes'],reverse=True)
    for index,item in enumerate(packages):
        name=Path(urlsplit(item['url']).path).name
        target='/home/miruware/ledger/artifacts/lmcache-runtime/wheels/'+name
        path=base/name
        if not path.exists():
            digest=hashlib.sha256()
            with urllib.request.urlopen(item['url'],timeout=120) as src,path.open('xb') as out:
                while data:=src.read(2**20):out.write(data);digest.update(data)
        else:
            digest=hashlib.sha256(path.read_bytes())
        if digest.hexdigest()!=item['sha256']:raise RuntimeError('Local wheel hash mismatch')
        copy(host,path,target)
        remote(host,f"import pathlib;pathlib.Path({target+'.ready'!r}).write_text('checksum verification follows before install')")
        end=time.monotonic()+600
        while remote(host,f"import pathlib;print(pathlib.Path({target!r}).exists())")=='True':
            if time.monotonic()>end:raise RuntimeError('Remote wheel not consumed; inspect guard')
            time.sleep(1)
        print(index+1,'/',len(packages),item['name'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',required=True);a=p.parse_args();run(a.host)
