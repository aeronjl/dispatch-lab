"""Check this design artifact and its saved probe; not a plant qualification."""
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
checks = []


def check(name, condition, detail):
    checks.append(dict(name=name, passed=bool(condition), detail=detail))


sources = json.loads((ROOT / 'sources.json').read_text())['sources']
ids = [s['id'] for s in sources]
check('source identities', len(ids) == len(set(ids)), len(ids))
design = (ROOT / 'design.md').read_text()
citations = set(re.findall(r'\[\[([\w-]+)\]\]', design))
catalogue = json.loads((ROOT / 'data-catalogue.json').read_text())
check('citation bindings', citations <= set(ids), sorted(citations - set(ids)))
check('catalogue source bindings', all(s in ids for r in catalogue for s in r['sources']), len(catalogue))
check('source URL structure', all(s['url'].startswith('https://') for s in sources), 'Structural check only; reviewed source pages are not snapshotted.')
samples = json.loads((ROOT / 'retrieval-20260913/resource-samples.json').read_text())['sites']
check('public probe complete', len(samples) == 3 and all(s['status'] == 200 for s in samples), [s['name'] for s in samples])
for s in samples:
    request_path = ROOT / 'retrieval-20260913' / s['request']
    request = json.loads(request_path.read_text())
    raw_path = request_path.with_name('response.json')
    raw = json.loads(raw_path.read_text())
    check(s['name'] + ' raw integrity', sha(raw_path) == s['raw_sha256'] == request['raw_sha256'], sha(raw_path))
    check(s['name'] + ' extraction', s['annual'] == raw['outputs']['totals']['fixed'] and s['monthly'] == raw['outputs']['monthly']['fixed'] and s['inputs'] == raw['inputs'], 'Saved extraction equals provider payload exactly.')
    delta = sum(r['E_m'] for r in s['monthly']) - s['annual']['E_y']
    check(s['name'] + ' monthly reconciliation', abs(delta) <= .1, dict(difference_kwh=delta, rounding_tolerance_kwh=.1))
    check(s['name'] + ' calendar', [m['month'] for m in s['monthly']] == list(range(1,13)), '12 monthly means, not hourly chronology.')
    check(s['name'] + ' reference fixture', s['inputs']['pv_module']['peak_power'] == 1 and s['inputs']['pv_module']['system_loss'] == 14 and s['inputs']['mounting_system']['fixed']['slope']['value'] == 30 and s['inputs']['mounting_system']['fixed']['azimuth']['value'] == 0, '1 kWp / 14% / 30° south')
check('matched meteo editions', all(s['inputs']['meteo_data'] == samples[0]['inputs']['meteo_data'] for s in samples), samples[0]['inputs']['meteo_data'])
report = (ROOT / 'report.html').read_text()
check('rendered citation tokens', not re.search(r'\[\[[\w-]+\]\]', report), 'No unresolved authored tokens.')
anchors = set(re.findall(r'\bid="([^"]+)"', report))
missing = []
for link in re.findall(r'href="([^"]+)"', report):
    if link.startswith('#'):
        if link[1:] not in anchors:
            missing.append(link)
    elif not link.startswith(('https://', 'http://')):
        if not (ROOT / link).exists() and link != 'validation.json':
            missing.append(link)
check('report local links', not missing, missing)
check('offline presentation', 'https://' not in (ROOT / 'report.css').read_text() and not re.search(r'<(?:script[^>]+src|link[^>]+href)="https?://', report), 'External citations remain links; rendering has no external dependencies.')
files = ['design.md', 'report.html', 'report.css', 'report.js', 'sources.json', 'data-catalogue.json', 'integration-inventory.json', 'retrieval-20260913/resource-samples.json', 'build_report.py', 'validate.py', 'check-browser.cjs']
result = dict(checked_at=datetime.now(UTC).isoformat(), scope='Design artifact integrity and public-data probe only. No GIS connector, annual simulator, investment model or controller is implemented or qualified by these checks.', files={f:sha(ROOT/f) for f in files}, checks=checks)
(ROOT / 'validation.json').write_text(json.dumps(result, indent=2)+'\n')
print(f'{sum(c["passed"] for c in checks)}/{len(checks)} design/data checks passed')
if not all(c['passed'] for c in checks):
    raise SystemExit(1)
