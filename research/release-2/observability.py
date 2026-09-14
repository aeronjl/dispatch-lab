"""Bounded identifiability experiment using production physics and observation interfaces.

A controlled load intervention, not a comparison of autonomous policies or a
prediction of field detection rates. No fault schedule enters sensing.update.
"""
from dataclasses import asdict, replace
from pathlib import Path
import json
from methane.config import Plant, Sensors
from methane.physics import State, transition, ACTION_KEYS
from methane.sensing import Diagnosis, observe, update
from methane.simulation import initial_observation
from methane.provenance import LOADED_SOURCE


def sequence(capacity, requests, *, noise, seed, estimate=450, probes=False):
    p=replace(Plant(),h2_capacity_kg=200)
    s=Sensors(noise_fraction=noise,ambiguity_policy='retain-capacity/1')
    state=State.initial(p); prior=initial_observation(state); d=Diagnosis(estimate)
    result=[]; previous_request=None
    for hour, request in enumerate(requests):
        action=dict.fromkeys(ACTION_KEYS,0.0);action['electrolyser_kw']=min(request,capacity)
        before=state
        state,row=transition(p,state,action,1000,20,0,capacity=capacity)
        measured=observe(p,s,before,row,seed,hour,rng_policy='named-channels/1')
        d,incident,event=update(p,s,d,prior,measured,request,probe=probes,strict_probe=True,consecutive_probe_power=previous_request)
        result.append(dict(hour=hour,requested_kw=request,observation=measured,diagnosis=asdict(d),event=event,incident=incident,retrospective_truth=dict(capacity_kw=capacity,applied_kw=action['electrolyser_kw']),physical_audits_passed=all(c['passed'] for c in row['audits'])))
        prior=measured;previous_request=request
    return result


def main():
    requests=[0,0,135,135,180,180,225,225,270,270,450,450]
    cases=[]
    for noise in (0,.02):
        for seed in (7,42,101):
            a=sequence(450,requests,noise=noise,seed=seed);b=sequence(225,requests,noise=noise,seed=seed)
            limited=sequence(450,[180]*14,noise=noise,seed=seed,estimate=180,probes=True)
            upward=sequence(450,[v for v in (180,225,270,315,360,405,450) for _ in range(2)],noise=noise,seed=seed,estimate=180,probes=True)
            checks=dict(below_capacity_indistinguishable=all(x['observation']==y['observation'] and x['diagnosis']==y['diagnosis'] for x,y in zip(a[:8],b[:8])),inactive_not_healthy=all(r['diagnosis']['status']=='insufficient evidence' for r in a[:2]+b[:2]),capacity_loss_detected=any(r['event']=='Capacity loss confirmed' for r in b[8:]),limited_probes_do_not_restore_nameplate=limited[-1]['diagnosis']['capacity_kw']==180,upward_success_confirms_nameplate=upward[-1]['diagnosis']['capacity_kw']==450,all_physics_checks=all(r['physical_audits_passed'] for rows in (a,b,limited,upward) for r in rows))
            cases.append(dict(seed=seed,noise=noise,checks=checks,healthy=a,derated=b,resource_limited_repaired=limited,upward_repaired=upward))
    value=dict(version='release-2-observability/1',source=LOADED_SOURCE,scope='Controlled loads with sufficient DC power and 200 kg H2 capacity to isolate observational identifiability. Illustrative ideal channels plus named Gaussian noise. Not a field detection rate or proof over all noise draws.',cases=cases,passed=all(all(c['checks'].values()) for c in cases))
    path=Path('research/release-2/observability.json');path.write_text(json.dumps(value,indent=2,allow_nan=False))
    print(json.dumps(dict(passed=value['passed'],cases=[dict(seed=c['seed'],noise=c['noise'],checks=c['checks']) for c in cases])))
    if not value['passed']:raise ValueError('Inspect saved controlled-load failures')

if __name__=='__main__':main()
