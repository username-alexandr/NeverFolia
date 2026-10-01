#!/usr/bin/env python3
from pathlib import Path
import importlib.util,json,subprocess,sys

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts'

def need(v,m):
    if not v:raise ValueError(m)

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);need(spec is not None and spec.loader is not None,'cannot load '+str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    p=subprocess.run(['python3',str(ROOT/'qa/field-r3931/runtime.py')],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
    (OUT/'r3932-runtime-base.log').write_text(p.stdout);print(p.stdout,flush=True)
    need(p.returncode==0,'R39.31 natural runtime failed on R39.32 candidate')
    base=json.loads((OUT/'runtime.json').read_text())
    c=base['candidate']
    need(c['isolated_air_in_water']==0,'isolated ocean AIR regression')
    need(c['long_air_columns_ge16']==0,'long ocean AIR-column regression')
    need(c['plain_ice_64_126']==0,'submerged plain-ice regression')

    patcher=load('r3932_patch',ROOT/'qa/field-r3932/patch_pack.py')
    audit=patcher.verify((ROOT/'candidate/NeverOverworld.zip').read_bytes())
    need(audit['conduit_definition']['project_start_to_heightmap']=='OCEAN_FLOOR_WG','conduit not seabed anchored')
    need(audit['trident_definition']['project_start_to_heightmap']=='OCEAN_FLOOR_WG','trident monument not seabed anchored')
    need(audit['conduit_definition']['start_height']=={'absolute':0},'conduit has seabed offset')
    need(audit['trident_definition']['start_height']=={'absolute':0},'trident monument has seabed offset')
    need(audit['ocean_pillar']['cave_air']==0,'ocean pillar cave-air regression')
    need(audit['trident_pool_elements']>=300,'trident water-preservation coverage incomplete')

    report={
      'pass':True,
      'natural_ocean':base,
      'underwater_structure_audit':audit,
      'ancient_cistern_open_ocean_rejected':True,
      'manual_structure_visual_acceptance_required':True
    }
    (OUT/'runtime-r3932.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('R3932_RUNTIME '+json.dumps({
      'pass':True,
      'isolated_air_in_water':c['isolated_air_in_water'],
      'long_air_columns_ge16':c['long_air_columns_ge16'],
      'plain_ice_64_126':c['plain_ice_64_126'],
      'trident_pool_elements':audit['trident_pool_elements'],
      'conduit_pool_elements':audit['conduit_pool_elements'],
      'ancient_cistern_open_ocean_rejected':True
    }),flush=True)

if __name__=='__main__':main()
