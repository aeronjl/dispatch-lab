"""Read-only performance diagnosis from a committed annual checkpoint."""
import cProfile,json,pstats,time
from pathlib import Path
from methane.config import Config
from methane.simulation import run
from methane.siting.production import entries,read_blob
from methane.siting.checkpoint import Continuation
from methane.siting.environment import weather
from methane.siting.store import Store,digest
s=Store();m=json.load(open(json.load(open('research/release-2/active-programme.json'))['path']));g=next(g for g in m['studies'] if g['key']=='annual');study=s.get('study',g['id']);c=study['cases'][0];e=entries(s,g['id'],c['case_id'])[-1];checkpoint=read_blob(s,e['checkpoint_sha256']);config=Config.from_dict(c['config']);w=weather(s,c['environment_id'],config);start=e['next_hour'];binding=digest(dict(case=c,environment=c['environment_id'],source=study['source']['content_hash']));cont=Continuation(c['hours'],start+8,binding,checkpoint=checkpoint,utilities=c.get('utilities'))
print('Profiling checkpoint',start,flush=True);profile=cProfile.Profile();profile.enable();r=run(config,w,[c['controller']],continuation=cont);profile.disable();profile.dump_stats('build/release-2/continuation.prof');pstats.Stats(profile).strip_dirs().sort_stats('cumtime').print_stats(35);print('Completed',r['status'],len(r['records'][c['controller']]),flush=True)
