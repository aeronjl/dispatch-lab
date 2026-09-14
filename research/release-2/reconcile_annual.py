"""New reporting derivation over committed annual hours; no simulation or overwrite.

The original worker was stopped during repeated summary decoding. Its complete
hourly records and source capsule stay unchanged. This version calculates one
case summary under an explicitly separate reporting identity.
"""
import hashlib,json,time
from datetime import datetime,UTC
from pathlib import Path
from methane.provenance import LOADED_SOURCE, LOADED_CAPSULE
from methane.siting.store import Store,atomic,encode
from methane.siting.production import directory,entries
from methane.siting.summary import calculate

store=Store();sid='eb104280b3cbe4bf0dec35384108891b91025799b25c93f76a07da0edc9e4635'
m=store.get('study',sid);case=m['cases'][0];d=directory(store,sid);target=d/case['case_id']/'summary.json'
if target.exists():raise ValueError('Original summary already exists; create a new report edition instead of overwriting it')
items=entries(store,sid,case['case_id']);assert sum(x['interval_count'] for x in items)==8760
begin=time.perf_counter()
def progress(done,total):
 print(f'Read {done}/{total} recorded hours',flush=True)
value=calculate(store,sid,case,progress)
receipt=dict(schema_version='site-case-summary-derivation/1',study_id=sid,case_id=case['case_id'],execution_source=m['source']['content_hash'],report_source=LOADED_SOURCE['content_hash'],report_capsule_sha256=LOADED_CAPSULE['sha256'],script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),recorded_hours=8760,decoded_partitions=len(items),seconds=time.perf_counter()-begin,at=datetime.now(UTC).isoformat(),scope='Whole-case reporting over unchanged committed hours. Cost assumptions are the original case assumptions. The original final summary was never published. No hourly decision, weather, fault or checkpoint is changed; remaining policy cases are unexecuted.')
value['calculation_source']=receipt
atomic(d/case['case_id']/'summary-source-capsule.json',encode(LOADED_CAPSULE))
atomic(d/case['case_id']/'summary-calculation.json',encode(receipt))
atomic(target,encode(value))
atomic(d/'cancel',b'Optional policy cases cancelled by product-scope revision.\n')
atomic(d/'progress.json',encode(dict(status='cancelled',fraction=.25,description='Representative annual case complete; remaining policy cases preserved as optional templates',updated_at=datetime.now(UTC).isoformat())))
atomic(Path('research/release-2/annual-reconciliation.json'),encode(receipt))
print(json.dumps(receipt),flush=True)
