import json,sys
from dataclasses import asdict
from pathlib import Path
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R.parent.parent))
from methane.services.configuration import ServiceSystem
ctx=json.loads((R/'review-context.json').read_text());f=R/'assumptions.json';reg=json.loads(f.read_text())
ctx['reference_optional_defaults']={'service_system':asdict(ServiceSystem())}
(R/'review-context.json').write_text(json.dumps(ctx,indent=2)+'\n')
paths={
'A01':['faults.capacity_cause'],'A02':['field_operations.reset_enabled','service_system.reset_hours'],
'A03':['scenario.flow_bias_fraction'],'A04':['sensors.noise_fraction'],'A05':['sensors.noise_fraction'],
'A06':['service_system.cleaning_model'],'A07':['service_system.inspection_model','faults.contact_stuck','service_system.inspection_zero_limit_v','service_system.inspection_span_tolerance_fraction'],
'A08':['service_system.cleaning_area_m2ph','service_system.area_m2_per_kw','service_system.row_accessible'],
'A09':['service_system.inspection_interface'],'A10':['field_operations.human_work_hours','field_operations.repair_success_probability'],
'A11':['service_system.environment_source','service_system.assumed_wind_mps','service_system.assumed_rain_mmph'],
'A12':['field_operations.soiling_per_day'],'A13':['field_operations.cleaning_removal_fraction','service_system.brush_life_m2','service_system.portable_adhered_removal'],
'A14':['field_operations.mission_failure_probability','service_system.outcome_randomness'],
'A15':['field_operations.mission_power_kw','field_operations.dock_kw','service_system.dock_standby_kw'],
'A16':['field_operations.cleaning_hours','field_operations.inspection_hours','service_system.travel_hours','service_system.verification_hours'],
'A17':['service_system.support_model','service_system.crew_response_lead_hours','service_system.crew_travel_hours'],
'A18':['field_operations.cleaning_kits','field_operations.service_kits','service_system.portable_water_capacity_l'],
'A19':['scenario.fault_start_hour','faults.lifecycle'],'A20':['scenario.capacity_fraction'],
'A21':['plant.specific_energy_kwh_per_kg','plant.min_load_fraction','plant.start_energy_kwh'],
'A22':['plant.auxiliary_kw','plant.cooling_electric_fraction'],
'A23':['plant.thermal_capacity_kwh_per_k','plant.heat_loss_kw_per_k','plant.heater_max_kw','plant.cooling_max_kw','plant.minimum_run_hours'],
'A24':['plant.co2_delivery_kg','plant.co2_delivery_every_hours','plant.initial_co2_kg','plant.initial_h2_kg'],
'A25':[],'A26':['scenario.hours','plant.initial_soc'],
'A27':['costs.cleaner_eur','costs.rover_eur','costs.dock_eur','costs.field_asset_years','costs.human_service_eur_per_hour'],
'A28':['costs.field_replaceable_share'],'A29':['service_system.verification_hours'],'A30':['plant.dt_hours'],'A31':[]}
missing=[]
for a in reg['items']:
 a['config_bindings']=[]
 for path in paths[a['id']]:
  v={**ctx['defaults'],**ctx['reference_optional_defaults']}
  try:
   for k in path.split('.'):v=v[k]
  except (KeyError,TypeError):missing.append(path);continue
  a['config_bindings'].append(dict(path=path,default=v,activation='Optional service defaults, only active when configured' if path.startswith('service_system.') else 'Recorded default',version=ctx['source']['content_hash']))
 if a['id']=='A21':a['binding']='Plant.specific_energy_kwh_per_kg, min_load_fraction, start_energy_kwh'
f.write_text(json.dumps(reg,indent=2,ensure_ascii=False)+'\n')
print('Unresolved bindings:',missing)
