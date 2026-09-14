"""Qualify the separately identified compact reading source, not a new simulation."""
import hashlib,json,time,zipfile
from pathlib import Path
from compact_export import pages,VERSION
from methane import studies
from methane.documentation import calculation
from methane.provenance import LOADED_SOURCE
root=Path('build/release-2')/('compact-preflight-'+LOADED_SOURCE['content_hash'][:12]);root.mkdir(parents=True,exist_ok=True)
r=json.loads(Path('research/release-2/preservation/recovery.json').read_text());edition=r['edition_id'];report=studies.stored_report(edition);case=next(c for c in report['cases'] if c['entry'].get('archive'));result=studies.archive_for(edition,case['entry']);start=time.perf_counter();archive=root/'reader.zip';count=0;checks={};reader=root/'reader';reader.mkdir(exist_ok=True)
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for name,content in pages(result,'original-recording.json.gz'):
  z.writestr(name,content);p=reader/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content);count+=1
  if name.endswith('-h0000.json'):
   packet=json.loads(content);controller=packet['context']['controller']
   for key,value in packet['topics'].items():
    if key!='service-work':checks[controller+'/'+key]=value['calculation']==calculation(result,key,controller,0)
receipt=dict(version=VERSION,original_run=result['run_id'],original_source=result['provenance']['source']['content_hash'],reader_source=LOADED_SOURCE['content_hash'],adapter_sha256=hashlib.sha256(Path('research/release-2/compact_export.py').read_bytes()).hexdigest(),reader=str(reader),members=count,zip_bytes=archive.stat().st_size,elapsed_seconds=time.perf_counter()-start,checks=checks,passed=all(checks.values()),scope='All saved first-interval topic objects agree with the identified production calculation functions. Full 120-hour reading output is saved. Original execution source is unchanged; these are derived reading tables.')
Path('research/release-2/compact-preflight-2.json').write_text(json.dumps(receipt,indent=2));print(json.dumps({k:v for k,v in receipt.items() if k!='checks'}),flush=True)
