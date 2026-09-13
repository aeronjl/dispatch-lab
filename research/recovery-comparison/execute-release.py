"""Run a frozen main programme, its declared sensitivity and calibration sequentially."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from methane.recovery_comparison import ROOT as REPORT_ROOT, run_programme, calibrate

main, sensitivity = [REPORT_ROOT / name for name in sys.argv[1:3]]
result = {}
for name, directory in [('main',main),('window',sensitivity)]:
    print('BEGIN',name,directory,flush=True)
    result[name]=str(run_programme(directory))
    print('REPORT',name,result[name],flush=True)
    if (directory/'cancel').exists():
        print('CANCELLED; remaining stages not started',flush=True)
        raise SystemExit(2)
print('BEGIN clock calibration',flush=True)
result['calibration']=str(calibrate(main))
print('CALIBRATION',result['calibration'],flush=True)
with (main/'release-result.json').open('x') as f:json.dump(result,f,indent=2)
print('COMPLETE',main/'release-result.json',flush=True)
