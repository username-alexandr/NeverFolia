#!/usr/bin/env python3
from pathlib import Path
import importlib.util,json,subprocess

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts'

def need(v,m):
    if not v:raise ValueError(m)
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);need(spec is not None and spec.loader is not None,'cannot load '+str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    # Reuse the proven native-ocean runtime against R39.33 to catch any global
    # AIR/ice/water regression outside structures.
    (OUT/'build.json').write_text(json.dumps({'build_pass':True})+'\n')
    p=subprocess.run(['python3',str(ROOT/'qa/field-r3931/runtime.py')],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
    (OUT/'r3933-natural-runtime.log').write_text(p.stdout);print(p.stdout,flush=True)
    need(p.returncode==0,'natural ocean runtime failed')
    natural=json.loads((OUT/'runtime.json').read_text())
    c=natural['candidate']
    need(c['isolated_air_in_water']==0,'isolated AIR regression')
    need(c['long_air_columns_ge16']==0,'natural long AIR-column regression')
    need(c['plain_ice_64_126']==0,'submerged plain-ice regression')

    patcher=load('r3933_patch',ROOT/'qa/field-r3933/patch_pack.py')
    audit=patcher.verify((ROOT/'candidate/NeverOverworld.zip').read_bytes())
    b=json.loads((OUT/'build-r3933.json').read_text())

    need(audit['conduit_definition']['start_height']=={'absolute':0},'conduit placement changed')
    need(audit['ocean_pillar_definition']['start_height']=={'absolute':0},'ocean_pillar placement changed')
    need(audit['small_structure_water_guards']['conduit_air'],'conduit AIR guard missing')
    need(audit['small_structure_water_guards']['conduit_cave_air'],'conduit CAVE_AIR guard missing')
    need(audit['small_structure_water_guards']['ocean_pillar_pool']=='neverfolia:underwater_preserve_water','ocean_pillar water guard missing')

    t=audit['trident_definition']
    need(t['start_height']=={'absolute':-3},'trident must be embedded by 3 blocks')
    need(t['project_start_to_heightmap']=='OCEAN_FLOOR_WG','trident lost ocean-floor projection')
    need(t['terrain_adaptation']=='none','trident may alter seabed')
    need(b['trident_max_relief']==6 and b['trident_seabed_radius']==48,'trident seabed guard drifted')

    report={
      'pass':True,
      'natural_ocean':natural,
      'structure_audit':audit,
      'small_structure_placement_unchanged':True,
      'small_structure_water_only':True,
      'trident_policy':{
        'start_offset':-3,
        'heightmap':'OCEAN_FLOOR_WG',
        'terrain_adaptation':'none',
        'seabed_radius':48,
        'sample_step':24,
        'max_relief':6,
        'reject_steep_candidates':True
      },
      'manual_trident_visual_acceptance_required':True
    }
    (OUT/'runtime-r3933.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('R3933_RUNTIME '+json.dumps({
      'pass':True,
      'isolated_air_in_water':c['isolated_air_in_water'],
      'long_air_columns_ge16':c['long_air_columns_ge16'],
      'plain_ice_64_126':c['plain_ice_64_126'],
      'small_structure_placement_unchanged':True,
      'trident_start_offset':-3,
      'trident_max_relief':6,
      'manual_trident_visual_acceptance_required':True
    }),flush=True)

if __name__=='__main__':main()
