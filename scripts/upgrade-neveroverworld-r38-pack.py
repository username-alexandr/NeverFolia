#!/usr/bin/env python3
"""Replace only the pinned D&T drowned function; no other NBT, loot or controllers."""
import argparse,hashlib,json,zipfile,os,tempfile
from pathlib import Path
FUNCTION='data/nova_structures/function/jockey/make_drowned_into_jockey.mcfunction'
OUTPUT=b'# R38: one owning-entity spawn/ride/consume transaction.\nneverfolia:dnt drowned_mount\n'
KNOWN={
 'execute at @s run summon minecraft:zombie_nautilus ~ ~ ~ {PersistenceRequired:1b,Tags:["dnt_jockey_mount_tmp"]}\nexecute at @s run ride @s mount @e[type=minecraft:zombie_nautilus,tag=dnt_jockey_mount_tmp,distance=..2,sort=nearest,limit=1]',
 'execute summon zombie_nautilus run execute at @s run ride @n[type=drowned] mount @s\nneverfolia:dnt clear_saddle',
}
def upgrade(path):
 with zipfile.ZipFile(path) as src:
  if len(src.namelist())!=len(set(src.namelist())):raise ValueError('duplicate ZIP entry')
  if FUNCTION not in src.namelist():return {'pack':path.name,'function_present':False,'modified':False}
  previous=src.read(FUNCTION)
  if previous==OUTPUT:return {'pack':path.name,'function_present':True,'modified':False}
  if previous.decode().strip() not in KNOWN:raise ValueError('Unknown drowned-controller source contract')
  with tempfile.NamedTemporaryFile(dir=path.parent,suffix='.zip',delete=False) as t:temporary=Path(t.name)
  try:
   with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as target:
    for info in src.infolist():target.writestr(info,OUTPUT if info.filename==FUNCTION else src.read(info.filename))
   with zipfile.ZipFile(temporary) as target:
    for name in src.namelist():
     if name!=FUNCTION and target.read(name)!=src.read(name):raise ValueError('Unrelated file mutation: '+name)
   os.replace(temporary,path)
  finally:temporary.unlink(missing_ok=True)
 return {'pack':path.name,'function_present':True,'modified':True,'previous_function_sha256':hashlib.sha256(previous).hexdigest(),'new_function_sha256':hashlib.sha256(OUTPUT).hexdigest()}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--report',type=Path);a=p.parse_args();r=upgrade(a.input)
 if a.report:a.report.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps(r))
if __name__=='__main__':main()
