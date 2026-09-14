"""Restore completed historical exports as they become available, one at a time.

The original ordered restorer remains preserved. This driver changes work order
only; every complete extraction uses the same captured standalone checker.
"""
import hashlib,json,shutil,subprocess,sys,tempfile,time,zipfile
from pathlib import Path
base=Path('research/release-2/preservation')
names=('recovery','cleaning','information','corrected-support','provision','interface')
while True:
    pending=[name for name in names if not (base/(name+'-offline.json')).exists()]
    if not pending:break
    ready=[]
    for name in pending:
        record=json.loads((base/(name+'.json')).read_text())
        if record.get('portable_bundle'):ready.append((name,record))
    if not ready:
        time.sleep(15);continue
    name,record=ready[0];bundle=Path(record['portable_bundle']['path'])
    sha=hashlib.file_digest(bundle.open('rb'),'sha256').hexdigest()
    if sha!=record['portable_bundle']['sha256']:raise ValueError('Export identity changed')
    with zipfile.ZipFile(bundle) as z,tempfile.TemporaryDirectory(prefix='dispatch-r2-preservation-') as directory:
        root=Path(directory);expected=sum(i.file_size for i in z.infolist())
        if shutil.disk_usage(root).free<expected+5_000_000_000:raise RuntimeError('Insufficient space for safe disposable restoration')
        members=z.namelist()
        if len(members)!=len(set(members)):raise ValueError('Duplicate bundle entry')
        for entry in members:
            target=(root/entry).resolve()
            if not target.is_relative_to(root.resolve()) or '\\' in entry:raise ValueError('Unsafe bundle entry')
        print(name,'restoring',expected,'bytes',flush=True);z.extractall(root)
        out=subprocess.run([sys.executable,'-I','-S',str(root/'check_study.py'),str(root)],capture_output=True,text=True)
        result=json.loads(out.stdout);full=base/(name+'-offline-archives.json')
        full.write_text(json.dumps(result,indent=2))
        summary=dict(version='release-2-preservation-restore/1',edition_id=record['edition_id'],source=record['original_source'],bundle=str(bundle),sha256=sha,uncompressed_bytes=expected,process_exit=out.returncode,archives=len(result['archives']),integrity_passed=result['integrity_passed'],complete_archives_passed=result['complete_archives_passed'],failed_runs=[r['run_id'] for r in result['archives'] if not r['reference_passed']],method='Full temporary extraction; captured standalone checker run under python -I -S. No third-party packages or network. Duplicate extraction removed after verification; original ZIP retained.',detail=str(full),orchestrator='research/release-2/restore_ready.py')
        (base/(name+'-offline.json')).write_text(json.dumps(summary,indent=2))
        print(name,summary['archives'],summary['complete_archives_passed'],flush=True)
        if out.returncode:raise ValueError('Preserved failures remain in '+str(base/(name+'-offline.json')))
print('All six original-source exports restored and checked.',flush=True)
