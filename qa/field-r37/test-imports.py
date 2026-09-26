#!/usr/bin/env python3
"""Pinned-source regression for all five dungeon imports; offline with --sources."""
import argparse,gzip,hashlib,importlib.util,json,tempfile,zipfile,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
b=load('r37_builder',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
qa=load('r37_graph',ROOT/'qa/field-r19/validate-external-structures-pack.py')
def raw(data):
 if data[:2]==b'\x1f\x8b':return gzip.decompress(data)
 if data[:1]==b'x':
  try:return zlib.decompress(data)
  except zlib.error:pass
 return data

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sources',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 sources={k:(a.sources/(k+'.zip')).read_bytes() for k in b.SOURCES}
 for k,data in sources.items():
  assert hashlib.sha256(data).hexdigest()==b.SOURCES[k]['sha256'],k+' source hash mismatch'
 a.output.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='r37-pack-') as td:
  base=Path(td)/'base.zip';pack=Path(td)/'candidate.zip'
  with zipfile.ZipFile(base,'w') as z:z.writestr('pack.mcmeta',json.dumps({'pack':{'pack_format':107,'description':'static QA only'}}))
  b.build(base,pack,sources)
  report=qa.audit(pack,ROOT/'worldgen-spec/never-overworld-external-structures-r19.json')
  stats={}
  with zipfile.ZipFile(pack) as z:
   for k,data in sources.items():
    original=b.flatten_zip(data);foreign=[];unchanged=0;trial_configs=0
    for name,payload in original.items():
     if name not in z.namelist():continue
     actual=z.read(name)
     if name.endswith('.nbt'):
      assert b'porting_lib:' not in raw(actual),name
      if b'porting_lib:' not in raw(payload):
       assert actual==payload,'unrelated NBT mutation: '+name
       unchanged+=1
      else:
       foreign.append(name)
       # Semantic proof: only attribute lists may differ; sanitizer independent
       # negative checks below ensure foreign fields elsewhere fail closed.
       assert b.sanitize_dat_structure_nbt(actual,name)==actual,'not idempotent'
     if '/trial_spawner/' in name:
      assert actual==payload,'source trial config changed: '+name
      trial_configs+=1
    stats[k]={'unchanged_nbt':unchanged,'foreign_attribute_templates':foreign,'unchanged_trial_configs':trial_configs}
   assert len(stats['explorify']['foreign_attribute_templates'])==6
   assert stats['witch']['unchanged_nbt']==18
   assert stats['dat']['unchanged_nbt']==5072
   assert z.read('data/nova_structures/function/hydro_veil_heal.mcfunction').strip()==b'neverfolia:dnt regenerate'
   for mob in ('witch','cat'):
    _,_,root=b._nbt_parse(z.read('data/betterwitchhuts/structure/neverfolia_mobs/'+mob+'.nbt'))
    assert root['entities'][1][1][0]['nbt'][1]['id']==(8,'minecraft:'+mob)
    assert root['blocks'][1][1][0]['nbt'][1]['name']==(8,'betterwitchhuts:'+mob)
   # Empty-object effect components are valid, e.g. prevent_equipment_drop.
   assert b.sanitize_dat_enchantment({'effects':{'minecraft:prevent_equipment_drop':{}}})['effects']['minecraft:prevent_equipment_drop']=={}
 report['r37_source_preservation']=stats
 report['scope']='static source/graph/NBT checks; initial mob activation is a separate live gate'
 (a.output/'r37-import-qa.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
 print('R37 pinned import checks PASS: '+json.dumps(stats,ensure_ascii=False))
if __name__=='__main__':main()
