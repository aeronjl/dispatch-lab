"""Cross-source checkpoint compatibility experiment, never an original-study resume."""
import argparse, hashlib, json, time
from pathlib import Path
from methane.config import Config
from methane.provenance import LOADED_SOURCE
from methane.simulation import run
from methane.siting.checkpoint import Continuation, unpack
from methane.siting.environment import weather
from methane.siting.production import entries, read_blob
from methane.siting.store import Store, digest
p=argparse.ArgumentParser();p.add_argument('output');a=p.parse_args()
root=Path('/Users/aeron/sota/dispatch-lab'); store=Store(root/'runs/sites')
study_id='86739b2587f654df7cd73960106296a01de78b1445a1795f4e915ede69e0e028'
study=store.get('study',study_id);case=study['cases'][0];entry=entries(store,study_id,case['case_id'])[-1];checkpoint=read_blob(store,entry['checkpoint_sha256'])
c=Config.from_dict(case['config']);w=weather(store,case['environment_id'],c);start=entry['next_hour'];binding=digest(dict(case=case,environment=case['environment_id'],source=study['source']['content_hash']))
cont=Continuation(case['hours'],start+24,binding,checkpoint=checkpoint,utilities=case.get('utilities'))
clock=time.perf_counter();r=run(c,w,[case['controller']],continuation=cont);out=cont.output;elapsed=time.perf_counter()-clock
fields=('hour','requested','applied','state','observations_after','diagnosis_after','lifecycle','field_operations','co2_delivered_kg','co2_rejected_kg','forced_trip')
rows=[{k:v for k,v in row.items() if k in fields} for row in r['records'][case['controller']]]
restored=unpack(out['graph']);services=restored['services']
value=dict(version='checkpoint-cross-source-continuation/1',execution_source=LOADED_SOURCE,original_study=study_id,original_checkpoint=entry['checkpoint_sha256'],start_hour=start,end_hour=out['next_hour'],elapsed_seconds=elapsed,status=r['status'],rows=rows,rows_sha256=digest(rows),checkpoint_nodes=len(out['graph']['nodes']),aliases=dict(ledger=services.executive.ledger is services.ledger,effect_port=services.executive._effect_port is services._effects,surface=services._effects.surface is services.optical.surface),scope='Explicit compatibility experiment from an old checkpoint, not a resumed original study or qualification inherited from old source. Complete physical, observation, service and lifecycle interval records are compared; chronology starts at the same committed boundary.')
path=root/a.output;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,allow_nan=False));print(json.dumps({k:v for k,v in value.items() if k not in ('rows','execution_source')}),flush=True)
