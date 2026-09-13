"""Inventory preserved local artifacts after all programmes finish; never delete them."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
REPORT=Path(__file__).resolve().parent
paths=set()
indexed=json.loads((REPORT/'programme-index.json').read_text())['entries']
for item in indexed:
    folder=REPORT/item['id']
    programme=json.loads((folder/'programme.json').read_text())
    for entry in programme['entries']:
        study=ROOT/'runs/studies'/entry['edition_id']
        paths.update(p for p in study.iterdir() if p.is_file())
        for name in ('inputs','attempts','reports','publication-index'):
            paths.update(p for p in (study/name).rglob('*') if p.is_file())
    for result in (folder/'calibration').glob('*/result.json'):
        data=json.loads(result.read_text())
        paths.update(Path(x['archive']) for x in data['source_runs'])
        paths.update(ROOT/x['qualification']['artifact'] for x in data['source_runs'] if x.get('qualification'))
for summary in REPORT.glob('retrieval-*-summary.json'):
    data=json.loads(summary.read_text())
    if data.get('archive'):paths.add(Path(data['archive']))
ignored=subprocess.run(['git','ls-files','--others','--ignored','--exclude-standard','-z','research/recovery-comparison'],cwd=ROOT,check=True,capture_output=True).stdout.decode().split('\0')
paths.update(ROOT/name for name in ignored if name and '__pycache__' not in Path(name).parts)
entries=[]
for path in sorted(paths):
    if not path.is_file():raise FileNotFoundError(path)
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    entries.append(dict(path=str(path.relative_to(ROOT)),bytes=path.stat().st_size,sha256=h.hexdigest()))
output=dict(version='recovery-local-artifacts/1',
    scope='Preservation inventory, not an independent numerical audit or a backup. Includes study manifests, inputs, attempts, reports, capsule manifests, calibration archives and ignored programme artifacts. Source-capsule file contents are bound by their original capsule manifests and are not enumerated again. Shared historical weather caches and build/profiling directories are not exhaustively inventoried.',
    files=entries,total_bytes=sum(x['bytes'] for x in entries))
with (REPORT/'local-artifacts.json').open('x') as stream:json.dump(output,stream,indent=2)
print(len(entries),'files;',output['total_bytes'],'bytes preserved locally')
