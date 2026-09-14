"""Current lifecycle example, original source bundle and isolated stdlib restoration."""
from dataclasses import replace
from pathlib import Path
import json, subprocess, sys, hashlib
from methane.bundle import make, unpack
from methane.config import Config, Scenario
from methane.evidence import save
from methane.lifecycle.fixtures import illustrative
from methane.reference import audit
from methane.simulation import run
from methane.provenance import LOADED_SOURCE

root=Path('build/release-2')/('offline-'+LOADED_SOURCE['content_hash'][:12]);root.mkdir(parents=True,exist_ok=True)
config=illustrative(Config(scenario=Scenario(hours=72,horizon_hours=24,solver_seconds=.1,capacity_fraction=1,flow_bias_fraction=0)),commission=True,aged=True)
record=root/'recording.json'
if record.exists():
    from methane.evidence import load
    result=load(json.loads(record.read_text())['archive'])
else:
    result=run(config,strategies=['Greedy']); archive=save(result,root/'archives')
    record.write_text(json.dumps(dict(archive=str(archive),run_id=result['run_id']),indent=2))
checks=audit(result)
(root/'independent.json').write_text(json.dumps(checks,allow_nan=False))
if not checks['passed']:raise ValueError('Saved independent lifecycle failures')
path=root/'reproduction.zip'
if not path.exists():make(result,path)
restored=unpack(path,root/'restored')
subprocess.run([sys.executable,'-I','-S',str((restored/'check_bundle.py').resolve()),str(restored.resolve()),'--out',str((root/'offline-check.json').resolve())],check=True,stdout=subprocess.DEVNULL)
receipt=dict(version='release-2-offline/1',run_id=result['run_id'],source=result['provenance']['source'],checker_source=LOADED_SOURCE,bundle=str(path),sha256=hashlib.file_digest(path.open('rb'),'sha256').hexdigest(),bytes=path.stat().st_size,restored=str(restored),independent_passed=True,offline_passed=True,model_pages=len(list((restored/'model').glob('*.html'))),scope='72-hour Greedy lifecycle execution, captured original source, stdlib physical/accounting check, saved Model explanations and examples. No network needed. Numerical decision rerun is recorded separately.')
Path('research/release-2/offline.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps({k:v for k,v in receipt.items() if k not in ('source','checker_source')}))
