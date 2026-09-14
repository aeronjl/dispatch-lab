"""Resume the two already-paused export workers sequentially; no numerical actions.

Checks the owned worker command before signalling it, to avoid signalling a reused
process identifier. The original export driver and calculation source are unchanged.
"""
import datetime,json,os,signal,subprocess,time
from pathlib import Path
receipt=Path('research/release-2/archive-resource-budget.json')
base=Path('research/release-2/preservation')
def wait_for(name):
    while not json.loads((base/(name+'.json')).read_text()).get('portable_bundle'):
        time.sleep(15)
def resume(name,pid):
    command=subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True).strip()
    expected='research/release-2/preserve.py --export --compact --only '+name
    if not command.endswith(expected):raise RuntimeError('Export worker identity changed; do not signal '+str(pid))
    os.kill(pid,signal.SIGCONT)
    value=json.loads(receipt.read_text());value.setdefault('resumptions',[]).append(dict(name=name,pid=pid,at=datetime.datetime.now(datetime.UTC).isoformat()))
    value['paused']=[v for v in value['paused'] if v['pid']!=pid];receipt.write_text(json.dumps(value,indent=2));print(name,'resumed',flush=True)
wait_for('interface');resume('corrected-support',64402)
wait_for('corrected-support');resume('provision',68488)
wait_for('provision')
value=json.loads(receipt.read_text());value['complete']=True;value['completed_at']=datetime.datetime.now(datetime.UTC).isoformat();receipt.write_text(json.dumps(value,indent=2));print('All paused exporters resumed and completed.',flush=True)
