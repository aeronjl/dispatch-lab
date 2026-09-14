"""Check report claim identities with altered in-memory receipts; never change runs."""
import copy,json
from pathlib import Path
import report_data as rd
original=rd.read;data=rd.build(write=False);manifest=original(original(rd.ROOT/'active-programme.json')['path']);checks={}
folder=Path(original(rd.ROOT/'active-programme.json')['path']).parent
case=next((folder/'analysis').glob('seasonal-case-*.json'))
for key in ('study_id','source','design_id','environment_id','controller','label','seed','policy','case_id'):
    def changed(path,default=None,key=key):
        value=original(path,default)
        if Path(path)==case:value=copy.deepcopy(value);value[key]='different'
        return value
    rd.read=changed
    try:rd.build(write=False);checks['case/'+key]=False
    except (ValueError,KeyError):checks['case/'+key]=True
    finally:rd.read=original
value=original(rd.ROOT/'source-comparison.json');checks['comparison/valid']=rd.comparison_matches(value,manifest)
for key in ('after_programme','before_programme','after_source','before_source','complete','passed'):
    changed=copy.deepcopy(value);changed[key]=False if key in ('complete','passed') else 'different';checks['comparison/'+key]=not rd.comparison_matches(changed,manifest)
value=next(v for v in data['preservation'] if rd.preservation_matches(v));checks['preservation/valid']=True
for key in ('source_matches','case_set_matches','completed','matched_inputs','matched_traces','matched_outcomes','matched_events'):
    changed=copy.deepcopy(value);changed[key]=False if isinstance(value[key],bool) else value[key]-1;checks['preservation/'+key]=not rd.preservation_matches(changed)
for key in ('edition_id','source','sha256','integrity_passed','complete_archives_passed'):
    changed=copy.deepcopy(value);changed['offline'][key]=False if isinstance(value['offline'][key],bool) else 'different';checks['preservation/offline/'+key]=not rd.preservation_matches(changed)
group=next(g for g in data['studies'] if g['publication']);value=group['publication'];checks['publication/valid']=rd.publication_matches(value,group,manifest)
for key in ('source','study_id'):
    changed=copy.deepcopy(value);changed[key]='different';checks['publication/'+key]=not rd.publication_matches(changed,group,manifest)
changed=copy.deepcopy(value);changed['restored_reference']['status']='failed';checks['publication/reference']=not rd.publication_matches(changed,group,manifest)
checks['publication/missing']=not rd.publication_matches(None,group,manifest)
result=dict(version='release-2-report-contract-check/1',programme=manifest['id'],source=manifest['source']['content_hash'],checks=checks,passed=all(checks.values()),scope='Report identity and completion predicates checked with altered in-memory receipts. No source experiment, archive, or generated summary is modified. Physical and empirical claims remain separate.')
(rd.ROOT/'report-contract-check.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));assert result['passed']
