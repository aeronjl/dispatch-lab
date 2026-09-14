"""Finish original-source preservation in separate editions; never overwrite earlier reports."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from methane import studies


def compare(parent_id, edition_id):
    parent, child = studies.read_manifest(parent_id), studies.read_manifest(edition_id)
    before, after = studies.stored_report(parent_id), studies.stored_report(edition_id)
    originals = {c['case_id']:c for c in before['cases']}
    cases=[]
    for c in after['cases']:
        a=originals[c['case_id']];changes={}
        for k in a.get('outcomes',{}).keys() | c.get('outcomes',{}).keys():
            x,y=a.get('outcomes',{}).get(k),c.get('outcomes',{}).get(k)
            equal=math.isclose(x,y,rel_tol=1e-8,abs_tol=1e-5) if type(x) in (int,float) and type(y) in (int,float) else x==y
            if not equal:changes[k]=[x,y]
        trace=c['entry'].get('numerical_comparison')
        cases.append(dict(case_id=c['case_id'],label=c['label'],complete=a['entry']['status']==c['entry']['status']=='complete',
            inputs_match=all(a[k]==c[k] for k in ('config','policies','weather_hash','matching_inputs_hash')),
            applied_trace_matches=bool(trace and all(v['recorded_intervals']==v['recomputed_intervals'] and v['different_intervals']==0 and abs(v['methane_delta_kg'])<=1e-5 for v in trace.values())),
            numerical_comparison=trace,outcome_differences=changes,events_match=a['entry'].get('events')==c['entry'].get('events')))
    return dict(parent_edition_id=parent_id,edition_id=edition_id,parent_report=before['report_id'],report_id=after['report_id'],
        original_source=child['source_hash'],source_matches=parent['source_hash']==child['source_hash'] and parent['source_capsule_sha256']==child['source_capsule_sha256'],
        case_set_matches=set(originals)=={c['case_id'] for c in after['cases']},completed=after['completed_cases'],total=after['total_cases'],
        matched_inputs=sum(c['inputs_match'] for c in cases),matched_traces=sum(c['applied_trace_matches'] for c in cases),matched_outcomes=sum(not c['outcome_differences'] for c in cases),
        matched_events=sum(c['events_match'] for c in cases),cases=cases,
        scope='Original-source numerical repetition. No new environment, seed, calibrated equipment or corrected policy. Applied dispatch, reported outcomes and event summaries checked separately; not a claim of byte-identical plans or complete intermediate states.')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--export',action='store_true');parser.add_argument('--compact',action='store_true');parser.add_argument('--only',choices=('recovery','cleaning','information','corrected-support','provision','interface'));args=parser.parse_args()
    target=Path('research/release-2/preservation');target.mkdir(exist_ok=True)
    names=('recovery','cleaning','information','corrected-support','provision','interface')
    index=[]
    for name in names:
        if args.only and name!=args.only:continue
        pointer=Path('research/release-2/interface-preservation.json') if name=='interface' else Path('build/services/sensitivity-completion')/(name+'-reproduction.json')
        info=json.loads(pointer.read_text());path=target/(name+'.json')
        if path.exists():record=json.loads(path.read_text())
        else:
            record=compare(info['parent_edition_id'],info['edition_id']);path.write_text(json.dumps(record,indent=2,allow_nan=False))
        if record['completed']!=record['total'] or not record['source_matches'] or record['matched_inputs']!=record['total']:
            raise ValueError(name+': incomplete preservation or original-information mismatch')
        if name in ('provision','interface') and not record.get('publication'):
            paragraphs=[
                f"This edition repeats the original {name} study in its captured source and environment. It preserves the earlier experiment and adds no environmental samples or field evidence.",
                f"All {record['total']} cases completed. Matching counts are {record['matched_inputs']} for input identities, {record['matched_traces']} for applied dispatch traces, {record['matched_outcomes']} for all reported outcomes, and {record['matched_events']} for recorded event summaries. Numerical differences, when present, remain in the accompanying comparison record.",
                "Interpret the reproduction against its original publication. Earlier causal-matching qualifications, unsuccessful procedures, terminal reserves and unverified recovery remain part of that evidence. A numerical repetition of an old implementation does not qualify Release 2's new mechanisms.",
                "The comparison checks applied dispatch, reported physical/economic/diagnostic outcomes and event summaries. It does not require identical future plans, solver search details, archive bytes or every intermediate state. Supporting source records and verification seals are retained."
            ]
            pub=studies.publish_interpretation(record['edition_id'],record['report_id'],paragraphs,'Codex · agent-authored preservation account')
            record['publication']={k:pub[k] for k in ('edition_id','report_id','status','archive_verification')}
            path.write_text(json.dumps(record,indent=2,allow_nan=False))
        if args.export and not record.get('portable_bundle'):
            bundle=Path('build/release-2/preservation')/(name+'-reproduction.zip')
            if bundle.exists():raise ValueError('Unreceipted existing export; inspect before replacing '+str(bundle))
            exporter=studies.export
            if args.compact:
                from compact_export import export as exporter
            exporter(record['edition_id'],bundle,report_id=record.get('publication',{}).get('report_id',record['report_id']))
            record['portable_bundle']=dict(reader='compact/1' if args.compact else 'paged/1',path=str(bundle),bytes=bundle.stat().st_size,sha256=hashlib.file_digest(bundle.open('rb'),'sha256').hexdigest(),scope='Exported bytes; offline restore verification is a separate receipt')
            path.write_text(json.dumps(record,indent=2,allow_nan=False))
        compact={k:v for k,v in record.items() if k!='cases'};index.append(dict(question=name,**compact));print(json.dumps(dict(question=name,total=record['total'],matched_traces=record['matched_traces'],matched_outcomes=record['matched_outcomes'])),flush=True)
    if not args.only:(target/'index.json').write_text(json.dumps(index,indent=2,allow_nan=False))

if __name__=='__main__':main()
