#!/usr/bin/env python3
"""Read retained block data and exact runtime sources. No saved-world changes."""
from pathlib import Path,PurePosixPath
from collections import Counter
import importlib.util,json,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'ice-review';OUT.mkdir(exist_ok=False)
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def save(p,d):p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n')
with zipfile.ZipFile('debug/diagnostics.zip') as z:
 for leaf in ('StructureTemplate.java','IcebergFeature.java','BlueIceFeature.java','SnowAndFreezeFeature.java','SurfaceSystem.java','ChunkTaskScheduler.java','NewChunkHolder.java'):
  names=[n for n in z.namelist() if n.endswith('/'+leaf) and '/src/minecraft/java/' in n]
  if not names:print('SOURCE_ABSENT',leaf);continue
  assert len(names)==1;raw=z.read(names[0]);(OUT/leaf).write_bytes(raw);lines=raw.decode().splitlines();hits=set()
  terms=('setBlock(', 'setBlockState(', 'getSeaLevel(', '63', 'frozenOceanExtension', 'new ChunkLightTask', 'neverOverworldNeighbours','StaticCache2D.create')
  for i,l in enumerate(lines):
   if any(t in l for t in terms):hits.update(range(max(0,i-7),min(len(lines),i+10)))
  print('PLACEMENT_SOURCE',leaf,'\n'.join(f'{i+1}: {lines[i]}' for i in sorted(hits)[:220]),flush=True)
obs=load('iceobs',ROOT/'scripts/probe-never-overworld-trees-villages-r1.py');paired=load('icepaired',ROOT/'scripts/probe-never-overworld-paired-r12.py');nbt=obs.load_nbt(ROOT)
phase=json.loads(Path('evidence/candidate-phase.json').read_text());targets=[(r['chunk_x'],r['chunk_z']) for r in phase['observed']['chunks']]
work=OUT/'retained-candidate';work.mkdir()
with zipfile.ZipFile('evidence/candidate-saved-regions.zip') as z:
 for n in z.namelist():
  p=PurePosixPath(n);assert not p.is_absolute() and '..' not in p.parts and '\\' not in n
  f=work.joinpath(*p.parts);f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(z.read(n))
v=paired.saved_volume(obs,nbt,work/'world/dimensions/minecraft/overworld/region',targets,{'normal_stop':True,'exit_code':0})
ice={'minecraft:ice','minecraft:packed_ice','minecraft:blue_ice','minecraft:frosted_ice'};aqua={'minecraft:water','minecraft:kelp','minecraft:kelp_plant','minecraft:seagrass','minecraft:tall_seagrass','minecraft:bubble_column'}
ct=Counter();rows=[];starts=[]
for (cx,cz),root in v.roots.items():
 for key,s in root.get('structures',{}).get('starts',{}).items():
  if s.get('id') not in (None,'INVALID'):starts.append({'id':key,'owner':[cx,cz],'children':s.get('Children',[])})
for cx,cz in targets:
 for sy in range(-32,9):
  for i,state in enumerate(v.section((cx,sy,cz))):
   if state['Name'] not in ice:continue
   pos=(cx*16+(i&15),sy*16+(i>>8),cz*16+((i>>4)&15));ct[state['Name']]+=1;near=[]
   for dx,dy,dz in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
    p=(pos[0]+dx,pos[1]+dy,pos[2]+dz)
    try:s=v.at(*p)
    except (KeyError,ValueError,IndexError):s=None
    near.append({'pos':p,'state':s})
   row={'pos':pos,'state':state,'neighbours':near,'all_neighbours_known':all(n['state'] is not None for n in near)}
   row['isolated_aquatic']=row['all_neighbours_known'] and all(n['state']['Name'] in aqua for n in near)
   row['adjacent_magma']=any(n['state'] is not None and n['state']['Name']=='minecraft:magma_block' for n in near)
   rows.append(row)
report={'read_only':True,'source_run':36337508038,'phase':'candidate','counts':dict(ct),'ice':rows,'structure_starts_in_selected_chunks':starts,'limits':'Nearby structure starts outside selected chunks are not assumed absent.'};save(OUT/'ice-details.json',report)
print('ICE_COUNTS',json.dumps(dict(ct)),flush=True)
for row in rows:
 if row['isolated_aquatic'] or row['adjacent_magma']:print('ICE_SPECIAL',json.dumps(row),flush=True)
print('ICE_STRUCTURE_IDS',sorted({s['id'] for s in starts}),flush=True)
