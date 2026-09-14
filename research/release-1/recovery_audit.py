"""Audit original recovery records across period boundaries, without replanning.

The standard full-run reference applies to complete single-period archives.
The separate chronology checker handles continuous physical states; this script
checks recovery receipts and immutable windows across the entire chronology.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from methane.provenance import LOADED_SOURCE
from methane.reference import audit
from methane.recovery_loop_reference import audit_run
from methane.siting import production
from methane.siting.store import Store

def check(programme,destination):
    p=json.loads(Path(programme).read_bytes());store=Store(p['store_root']);results=[]
    for g in p['groups']:
        study=store.get('study',g['study_id'])
        for case in study['cases']:
            summary=production.directory(store,g['study_id'])/case['case_id']/'summary.json'
            while not summary.exists() and production.state(store,g['study_id'])['status'] in ('running','ready'):
                time.sleep(2)
            entries=production.entries(store,g['study_id'],case['case_id'])
            rows=[];first=None
            for entry in entries:
                r=production.load_period(store,entry['period_sha256'])
                if first is None:first=r
                rows.extend(r['records'][case['controller']])
            if first is None:
                results.append(dict(study=g['study_id'],case=case['case_id'],status='incomplete',reason='No saved interval'));continue
            joined=dict(first,records={case['controller']:rows})
            checks=audit_run(joined)
            failed=[c for c in checks if not c['passed']]
            full=None
            if len(entries)==1 and len(rows)==first['config']['scenario']['hours']:
                report=audit(first)
                full=dict(passed=report['passed'],checks=len(report['checks']),failures=report['failures'])
            complete=len(rows)==case['hours']
            status='incomplete' if not complete else 'failed' if failed or full and not full['passed'] else 'passed'
            item=dict(study=g['study_id'],case=case['case_id'],group=g['name'],source=study['source']['content_hash'],hours=len(rows),periods=[e['period_sha256'] for e in entries],status=status,recovery_checks=len(checks),recovery_failures=failed,full_single_period_reference=full,
                scope='Original public receipts, required test increments, immutable outer deadlines, appointment boundaries and blocked/escalated requests across the full chronology. Version-1 local recovery has no version-3/4/5 loop claim. Single-period archives additionally receive the complete independent physical/service/cost reference; continuous physical states have their separate Decimal chronology check.')
            results.append(item);print(g['name'],case['case_id'],status,len(checks),full and full['passed'],flush=True)
    output=dict(version='release-recovery-audit/1',checker_source=LOADED_SOURCE['content_hash'],programme_sha256=hashlib.sha256(Path(programme).read_bytes()).hexdigest(),cases=results)
    dest=Path(destination)
    with dest.open('x') as f:json.dump(output,f,indent=2)
    if any(c['status']!='passed' for c in results):raise SystemExit(1)

if __name__=='__main__':check(sys.argv[1],sys.argv[2])
