"""Execute a current-source recovery example and preserve offline explanations.

This is a release integration fixture, separate from the frozen 104-case study.
"""
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from methane.bundle import make, unpack
from methane.documentation import calculation
from methane.evidence import save
from methane.model_topics import TOPICS
from methane.provenance import LOADED_SOURCE
from methane.reference import audit
from methane.services.verification_examples import CONTROLLER, fixture, weather_for
from methane.simulation import run

def execute(directory):
    directory = Path(directory)
    if directory.exists():
        raise ValueError("Choose a new output directory; existing evidence is immutable")
    c = fixture('successful-procedure')
    c = replace(c, scenario=replace(c.scenario, hours=36),
                sensors=replace(c.sensors, ambiguity_policy='retain-capacity/1'),
                recovery_policy=replace(c.recovery_policy,
                                        version='scheduled-load-tests/5', maximum_wait_hours=24))
    r = run(c, weather=weather_for(c, 'successful-procedure'), strategies=[CONTROLLER])
    checked = audit(r)
    assert r['status']=='complete' and checked['passed'], checked['failures']
    archive = save(r, directory/'archive')
    bundle = make(r, directory/'reproduction.zip')
    unpack(bundle, directory/'offline')
    values = {t:calculation(r,t,CONTROLLER,20) for t in TOPICS}
    assert len(values)==20
    assert values['recovery']['recovery']['recovery_obligation'] is not None
    (directory/'calculation-links.json').write_text(json.dumps(values, indent=2))
    summary = dict(schema='release-one-offline-integration/1',source=LOADED_SOURCE['content_hash'],
                   run_id=r['run_id'],archive=str(archive.resolve()),bundle=str(bundle.resolve()),
                   status=r['status'],metrics=r['metrics'][CONTROLLER],
                   independent_check=dict(passed=checked['passed'],checks=len(checked['checks'])),
                   topics=list(values),context='Current-source integration example; separate numerical edition from the frozen qualification. Illustrative human module replacement, not robotic repair.')
    (directory/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    execute(sys.argv[1])
