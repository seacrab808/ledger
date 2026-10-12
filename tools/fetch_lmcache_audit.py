"""Fetch exact audit sources into ignored project artifacts and verify their hashes."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def fetch():
    record = json.loads((ROOT / 'records/lmcache-audit.json').read_text(encoding='utf-8'))
    for item in record['source_files']:
        relative = Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid source path')
        target = ROOT / 'artifacts/lmcache-audit' / relative
        url = item['url'].replace('https://github.com/LMCache/LMCache/blob/',
                                  'https://raw.githubusercontent.com/LMCache/LMCache/')
        if not url.startswith('https://raw.githubusercontent.com/LMCache/LMCache/' + record['commit'] + '/'):
            raise ValueError('Unexpected source URL')
        data = urllib.request.urlopen(url, timeout=30).read()
        if hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('Source hash mismatch: ' + item['path'])
        if target.exists() and target.read_bytes() != data:
            raise ValueError('Existing audit file differs: ' + item['path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    print('Verified', len(record['source_files']), 'pinned audit sources; no runtime experiment.')

if __name__ == '__main__':
    fetch()
