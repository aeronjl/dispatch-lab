"""Independent expectations and observation challenges, not empirical calibration."""
import sys,json,math,hashlib,itertools
from pathlib import Path
from decimal import Decimal,localcontext
from dataclasses import replace,asdict
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent.parent))
from methane.config import Plant,Sensors
from methane.reactor import step,ThermalInput,REACTION_KWH_PER_KG
from methane.sensing import Diagnosis,update,observe
from methane.services.inspection import classify
from methane.services.configuration import ServiceSystem
from methane.provenance import LOADED_SOURCE

checks=[]
def check(name,actual,expected,tolerance=1e-9):
    passed=abs(actual-expected)<=tolerance if isinstance(expected,(int,float)) and not isinstance(expected,bool) else actual==expected
    checks.append(dict(claim=name,actual=actual,expected=expected,tolerance=tolerance,passed=passed))

p=Plant();s=Sensors();o=ServiceSystem()
check('Rounded reaction mass: 4 H2 + CO2 = CH4 + 2 H2O',4*2+44,16+2*18)
check('Reaction heat kWh per kg methane',REACTION_KWH_PER_KG,float(Decimal(165000)/16/3600))
thermal=[]
with localcontext() as ctx:
    ctx.prec=45
    for cap,loss,amb,start,heater,methane,cooling in itertools.product((.15,.3,.6),(0,.04,.08,.16),(-5,20,35),(20,250,400),(0,60),(0,10),(0,40)):
        C,U,A,T,H,M,Q=map(lambda x:Decimal(str(x)),(cap,loss,amb,start,heater,methane,cooling))
        net=H+M*Decimal(165000)/16/3600-Q
        expected=T+net/C if U==0 else A+net/U+(T-A-net/U)*(-U/C).exp()
        result=step(replace(p,thermal_capacity_kwh_per_k=cap,heat_loss_kw_per_k=loss),ThermalInput(start,amb,heater,methane,cooling))
        actual=result.state.temperature_c
        thermal.append(dict(capacity=cap,loss=loss,ambient=amb,start=start,heater=heater,methane=methane,cooling=cooling,expected=float(expected),actual=actual,error=abs(actual-float(expected))))
check('Independent exponential temperature grid maximum error',max(t['error'] for t in thermal),0,1e-9)
contacts=[]
for name,values,expected in [('open',(0,0,24),False),('closed',(24,0,24),True),('ambiguous',(12,0,24),None),('dropout',(None,0,24),None),('bad-zero',(27,3,27),None),('bad-span',(24,0,18),None),('allowed-offset',(25,1,25),True)]:
    r=classify(*values,o);check('Contact '+name,r['value'],expected);contacts.append(dict(case=name,operands=values,result=r))
# Equal electrical contact values cannot identify the hidden component cause.
a=classify(24,0,24,o);b=classify(24,0,24,o)
check('Shared stuck contact and genuine trip are observation-equivalent',a,b)

# Deliberate errors are stress amplitudes, not sensor specifications/probabilities.
# Constant 5 kg/h inflow and equal outflow keep a 30 kg true inventory.
sensor_cases=[]
for bias,drift,outflow_error in itertools.product((0,.3),(0,.6),(0,-.6)):
    d=Diagnosis(p.electrolyser_kw);prior={'h2_inventory_kg':30}
    history=[]
    for hour in range(1,7):
        obs=dict(power_kw=275,hydrogen_flow_kg=5*(1+bias),h2_inventory_kg=30+hour*drift,h2_outflow_kg=5+outflow_error)
        d,incident,event=update(p,s,d,prior,obs,275)
        history.append(dict(hour=hour,observations=obs,diagnosis=asdict(d),event=event))
        prior=obs
    sensor_cases.append(dict(flow_bias=bias,inventory_drift_kg_per_hour=drift,outflow_error_kg=outflow_error,history=history))
check('Biased flow isolated with ideal balance',sensor_cases[4]['history'][-1]['diagnosis']['flow_isolated'],True)
check('Same biased flow not isolated with inventory drift',sensor_cases[6]['history'][-1]['diagnosis']['flow_isolated'],False)
# Directly demonstrate the current inventory error vanishes at zero production.
row={'h2_produced_kg':0,'h2_consumed_kg':1,'applied':{'electrolyser_kw':0},'state':{'h2_kg':30,'battery_kwh':200,'co2_kg':500,'temperature_c':250,'electrolyser_on':False,'reactor_on':False,'commitment_hours':0}}
check('Inventory measurement exact at zero production under current observation model',observe(p,s,None,row,7,1)['h2_inventory_kg'],30)

bounds=dict(h2_kg_per_kg_ch4=4*2/16,co2_kg_per_kg_ch4=44/16,water_kg_per_kg_ch4=2*18/16,electrolyser_water_kg_per_kg_h2=18/2,
    supply_limited_ch4_kg_per_day=300/(44/16),initial_co2_ch4_kg=500/(44/16),h2_buffer_ch4_kg=60/(4*2/16),
    nominal_electrolyser_h2_kgph=450/55,thermal_time_constant_hours=.3/.08,
    continuous_warmup_20_to_250_hours=-.3/.08*math.log((20+60/.08-250)/(60/.08)),
    t4_5000m2_daily_cleaning_lower_bound_units=math.ceil(5000/400))
result=dict(schema_version='realism-independent-checks/1',source=LOADED_SOURCE['content_hash'],passed=all(c['passed'] for c in checks),
    checks=checks,thermal_cases=len(thermal),thermal=thermal,contacts=contacts,sensor_challenges=sensor_cases,bounds=bounds,
    scope='Independent decimal thermal expectations and chemistry; contact and diagnosis counterexamples use production functions with declared observations. Challenge amplitudes are not empirical error distributions. Thermal helper examples may be outside operating limits and are not feasible dispatch claims.')
out=ROOT/'experiments'/'mechanism-checks.json';out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:v for k,v in result.items() if k in ('passed','checks','thermal_cases','bounds')},indent=2))
assert result['passed']
