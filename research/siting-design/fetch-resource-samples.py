"""Read-only PVGIS feasibility probe; resource anchors are not proposed parcels.

Existing snapshots are reused. Outputs are provider PV estimates for a 1 kWp
reference system, not Dispatch Lab methane predictions or connection assessments.
"""
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
SITES = [('London', 51.5074, -0.1278), ('Seville', 37.3891, -5.9845), ('Copenhagen', 55.6761, 12.5683)]
rows = []
for name, lat, lon in SITES:
    params = dict(lat=lat, lon=lon, peakpower=1, loss=14, angle=30, aspect=0,
                  pvtechchoice='crystSi', mountingplace='free', usehorizon=1,
                  raddatabase='PVGIS-SARAH3', outputformat='json')
    url = 'https://re.jrc.ec.europa.eu/api/v5_3/PVcalc?' + urlencode(params)
    key = hashlib.sha256(url.encode()).hexdigest()
    folder = ROOT / 'data' / key
    folder.mkdir(parents=True, exist_ok=True)
    meta = folder / 'request.json'
    if meta.exists():
        saved = json.loads(meta.read_text())
    else:
        saved = dict(name=name, request_url=url, params=params,
                     retrieved_at=datetime.now(UTC).isoformat(),
                     publisher='European Commission Joint Research Centre / PVGIS',
                     attribution_url='https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis_en')
        try:
            with urlopen(Request(url, headers={'User-Agent': 'DispatchLab-siting-design/1'}), timeout=40) as response:
                raw = response.read()
                saved.update(status=response.status, content_type=response.headers.get('Content-Type'))
            saved['raw_sha256'] = hashlib.sha256(raw).hexdigest()
            (folder / 'response.json').write_bytes(raw)
        except Exception as exc:
            saved.update(status='unavailable', error=type(exc).__name__ + ': ' + str(exc))
        meta.write_text(json.dumps(saved, indent=2) + '\n')
    row = dict(name=name, latitude=lat, longitude=lon, request=str(meta.relative_to(ROOT)), status=saved['status'])
    if saved['status'] == 200:
        raw = (folder / 'response.json').read_bytes()
        if hashlib.sha256(raw).hexdigest() != saved['raw_sha256']:
            raise ValueError('Saved raw response hash changed')
        payload = json.loads(raw)
        row.update(inputs=payload['inputs'], annual=payload['outputs']['totals']['fixed'],
                   monthly=payload['outputs']['monthly']['fixed'], raw_sha256=saved['raw_sha256'])
    else:
        row['error'] = saved.get('error')
    rows.append(row)
    print(name, row['status'], row.get('annual',{}).get('E_y'), flush=True)
out = dict(version='siting-resource-probe/1',
           scope='Three existing regional weather anchors. Coordinates are city reference points, not selected land or deployment recommendations. PVGIS modelled PV output for a 1 kWp reference system; no plant simulation or profitability calculation.',
           sites=rows)
with (ROOT / 'resource-samples.json').open('x') as stream:
    json.dump(out, stream, indent=2, allow_nan=False)
