"""Collect executed receipts without turning earlier checks into new-source evidence."""
import hashlib
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from methane.provenance import LOADED_SOURCE

ROOT = Path(__file__).resolve().parent
repo = ROOT.parents[1]
receipts = ROOT / 'validation-receipts'
receipts.mkdir(exist_ok=True)

def preserve(path, name=None):
    p = Path(path)
    if not p.is_absolute():
        p = repo / p
    dest = receipts / (name or p.name)
    raw = p.read_bytes()
    if dest.exists():
        assert dest.read_bytes() == raw, 'Do not overwrite an earlier receipt'
    else:
        dest.write_bytes(raw)
    return dict(path=str(dest.relative_to(ROOT)), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))

stamp = json.loads((repo / 'build/release-1/release-source/source-under-test.json').read_bytes())
assert stamp['source']['content_hash'] == LOADED_SOURCE['content_hash']
tree = ET.parse(repo / 'build/release-1/release-source/pytest.xml')
suites = list(tree.getroot())
assert sum(int(s.attrib.get('tests', 0)) for s in suites) == 1089
assert not any(int(s.attrib.get('failures', 0)) or int(s.attrib.get('errors', 0)) for s in suites)
prior = '8486b4546cbc692df21f7f47acee0b0910dc4133d6769f85423fdbf43d833751'
records = []
def add(name, source, scope, paths, outcome='passed'):
    records.append(dict(name=name, execution_source=source, outcome=outcome, scope=scope, artifacts=[preserve(p, n) for p, n in paths]))

add('Final Python regression', LOADED_SOURCE['content_hash'], '1,089 passed; three warnings. Stable captured application content throughout the suite. Dirty Git flag includes the uncommitted research directory.', [('build/release-1/release-source/pytest.xml', None), ('/tmp/release-1-release-source.log', 'python-final.txt'), ('build/release-1/release-source/source-under-test.json', None)])
add('Documentation evidence', LOADED_SOURCE['content_hash'], 'All twenty topics passed with source_matches true. This does not calibrate assumptions.', [('build/release-1/release-source/documentation-evidence.json', None)])
add('Final JavaScript regression', LOADED_SOURCE['content_hash'], '85 passed. No skipped checks.', [('/tmp/release-1-release-js.log', 'javascript.txt')])
add('Full browser regression', prior, '97 passed, 19 fixture-specific skips. Original plant, solar and existing Model screenshot baselines unchanged. Subsequent reader estimate fix has targeted current-source coverage; this is not labelled as a second full final-source run.', [('/tmp/release-1-browser-final.log', 'browser-full.txt')])
add('New service Model interactions', prior, 'All 29 controls exercised; reset, error, request supersession, context, keyboard and narrow views checked separately by browser cases. Five simple topics have twenty measured interactions each.', [('build/release-1/receipts/service-interaction.json', None), ('/tmp/release-1-model-browser-final.log', 'model-browser.txt')])
add('Current archive and offline UI', LOADED_SOURCE['content_hash'], 'Five passed: original snapshot, component/cost lineage, offline Model, playback, and the original taxonomy service fixture. The taxonomy fixture deliberately keeps its historical identity.', [('/tmp/release-1-release-archive-browser.log', 'archive-browser-final.txt')])
add('Original decision estimate and repricing', LOADED_SOURCE['content_hash'], 'Current reader of the earlier 8486 archive: boundary 20 means decision interval 19. Original estimate reconciles; repricing preserves physical display. About 8 seconds for the whole cost report, outside the simple-example latency claim.', [('build/release-1/receipts/recorded-service-ui.json', None)])
add('Specialised study browser fixtures', prior, '12 field/Sites/uncertainty checks, two computation checks and three original service-accounting checks. Each uses its declared fixture; these counts are not additional numerical research cases.', [('/tmp/release-1-study-browser.log', 'study-browser.txt'), ('/tmp/release-1-computation-browser.log', 'computation-browser.txt'), ('/tmp/release-1-service-price-browser.log', 'service-price-browser.txt')])
add('Interactive and backend performance', prior, '240-hour active-batch reference: solar preview p95 147.8 ms/render 2.2 ms; battery learning p95 117.8 ms/render 0.6 ms. Backend payload, cached preview and lineage pass their separate budgets. Current release retains the same browser assets; source identity is not relabelled.', [('build/engineering/browser-performance-240h-batch.json', 'solar-performance.json'), ('build/model/active-batch-performance.json', 'battery-performance.json'), ('build/release-1/final-source/performance-gates.json', None), ('/tmp/release-1-performance-final-source.log', 'performance-browser.txt')])
add('Mutation sensitivity', 'Applicable file versions retained in the mutation outputs; not a whole-source proof', 'Six of six deliberate defects detected: chemistry, battery loss, planning efficiency, thermal sign, minimum run and forecast look-ahead.', [('build/release-1/receipts/mutations.json', None)])
add('Bounded formal verification', 'TLA specification SHA256 recorded in receipt', 'All four finite minimum-run abstractions passed. This does not prove the continuous implementation or physical realism.', [('build/release-1/receipts/formal-report.json', None)])
add('Final source offline reproduction', LOADED_SOURCE['content_hash'], '36-hour version-5 archive: inventory integrity and 4,270 independent checks passed without the application environment. Restored original-source numerical run has zero differing intervals and zero methane/cost delta in this execution.', [('build/release-1/release-source/offline-check.json', None), ('build/release-1/release-source/recomputation.json', None)])
attempts = [
    ('/tmp/release-1-recorded-browser.log', 'initial-mixed-archive-browser.txt', 'Five passed, three failed. Wrong-era service/taxonomy fixtures and a five-second full-repricing expectation; correct fixtures and the explicitly measured full-report path subsequently passed.'),
    ('build/release-1/receipts/formal-sandbox-attempt.json', 'formal-sandbox-attempt.json', 'Initial sandbox disallowed the local Java RMI socket. Same scoped checker passed with authorised local execution.'),
    ('build/release-1/receipts/recorded-service-ui-initial.json', 'recorded-service-ui-initial.json', 'Initial receipt labelled a playhead boundary as its interval index; corrected receipt explicitly preserves boundary 20 and interval 19.'),
]
initial=[]
for path, name, explanation in attempts:
    initial.append(dict(explanation=explanation, artifact=preserve(path,name)))
value = dict(
    version='release-one-validation/1', assembled_at=datetime.now(timezone.utc).isoformat(),
    release_source=LOADED_SOURCE['content_hash'], release_revision=LOADED_SOURCE['revision'],
    records=records, retained_attempts=initial,
    other_initial_findings=[
        'Initial full regression: 1,081 passed and four freshness/source failures while edits were still active. Stable-source reruns passed 1,086, then 1,088 after probe bounds, then 1,089 after original-estimate tracing.',
        'Review found future raw inspection readings in a teaching chart, categorical channels labelled as intervals, a hidden focused control and an undefined inactive deadline; fixed and verified.',
        'First targeted original-estimate regression used a teaching list instead of a run fixture; corrected to an actual recorded two-hour execution before final regression.',
    ],
    numerical_programme=dict(cases=104, hours=8352, source='55aa6d80fd4462f04cb5095cdff6a9ae28bc15fb67c074f7d980592a749c3b44', chronological_checks='All 104 passed independent Decimal physical/causal chronology checks', recovery_checks=57247, full_single_period_reference_checks=778718, full_single_period_cases=95, continuous_cases=9, audit='recovery-audit.json'),
    limits=[
        'The frozen numerical programme retains stale original assumption-review bindings. Its separately dated source review is not original evidence; final application metadata is fresh.',
        'No new empirical calibration, capability certification, annual return or unseen-weather reliability claim.',
        'Actual participant comprehension remains Release 3. Current walkthrough is agent-led.',
        'Simple-input performance is fixture-specific. Full report repricing remains about eight seconds; optimiser examples use separate progress/cancellation.',
        'Large source capsules, runs and bundles remain local and require durable backup separately from Git.',
    ],
    lint=dict(status='passed', formatted_files=346, command='.venv/bin/ruff check .; .venv/bin/ruff format --check .; git diff --check'),
)
with (ROOT/'validation.json').open('x') as f:
    json.dump(value,f,indent=2)
print('Preserved',len(records),'scoped validation records')
