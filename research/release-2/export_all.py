"""Three independent reading/export processes; no numerical study worker is added."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os,subprocess,sys
NAMES=('recovery','cleaning','information','corrected-support','provision','interface')
def one(name):
    with Path('/tmp/r2-export-'+name+'.log').open('w') as log:
        p=subprocess.run([sys.executable,'-u','research/release-2/preserve.py','--export','--compact','--only',name],env={**os.environ,'PYTHONPATH':'.:research/release-2'},stdout=log,stderr=log)
    print(name,p.returncode,flush=True)
    if p.returncode:raise RuntimeError('Preserved export failure: '+name)
with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(one,NAMES))
subprocess.run([sys.executable,'research/release-2/preserve.py'],env={**os.environ,'PYTHONPATH':'.:research/release-2'},check=True)
