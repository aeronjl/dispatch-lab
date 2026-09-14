"""Record the authored review in narrative-review.md against the reviewed source."""
import hashlib,json
from pathlib import Path
p=Path('docs/assumption-review.json');r=json.loads(p.read_text())
for g in r['groups'].values():
 g['bindings']={f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in g['bindings']}
p.write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n')
