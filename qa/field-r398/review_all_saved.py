#!/usr/bin/env python3
"""Read-only 54-chunk comparison from a completed, explicitly identified CI run.
No server launches, repairs, synthetic rooms, or mutations of source archives.
"""
from pathlib import Path,PurePosixPath
from collections import Counter
import argparse,hashlib,importlib.util,json,zipfile
ROOT=Path(__file__).resolve().parents[2]
PHASES=('baseline','candidate','restart','reverse','baseline-reverse','baseline-repeat')
FROZEN={'minecraft:ice','minecraft:packed_ice','minecraft:blue_ice','minecraft:frosted_ice'}
AQUATIC={'minecraft:water','minecraft:bubble_column','minecraft:kelp','minecraft:kelp_plant','minecraft:seagrass','minecraft:tall_seagrass'}
def need(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def save(p,r):p.write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n')
def extract(p,dest):
 dest.mkdir(exist_ok=False)
 with zipfile.ZipFile(p) as z:
  need(len(z.namelist())==len(set(z.namelist())) and z.testzip() is None,'Invalid saved archive')
  need(sum(i.file_size for i in z.infolist())<=1_073_741_824,'Unexpectedly large saved archive')
  for i in z.infolist():
   n=PurePosixPath(i.filename)
   need(not n.is_absolute() and '..' not in n.parts and '\\' not in i.filename,'Unsafe saved path')
   if i.is_dir():continue
   target=dest.joinpath(*n.parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(i))
def water(s):
 n=s['Name']
 if n=='minecraft:water':return 1+int(s.get('Properties',{}).get('level','0'))
 return 1 if n in AQUATIC else 0

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,default=ROOT/'evidence');p.add_argument('--run-id',type=int,required=True);a=p.parse_args()
 out=ROOT/'review';out.mkdir(exist_ok=False);work=ROOT/'.work/r398-read-only';work.mkdir(parents=True,exist_ok=False)
 e=a.evidence.resolve();provenance=json.loads((e/'r398-provenance.json').read_text());runtime=json.loads((e/'runtime.json').read_text())
 need(int(provenance['run_id'])==a.run_id,'Evidence is from a different run')
 need(runtime['candidate_core_sha256']==provenance['candidate_files']['server.jar'],'Core identity mismatch')
 observer=load('r398_read_observer',ROOT/'scripts/probe-never-overworld-trees-villages-r1.py')
 paired=load('r398_read_paired',ROOT/'scripts/probe-never-overworld-paired-r12.py');nbt=observer.load_nbt(ROOT)
 volumes={};hashes={};selected=None
 for name in PHASES:
  phase=json.loads((e/(name+'-phase.json')).read_text())
  need(phase.get('pass') is True and type(phase.get('exit_code')) is int and phase['exit_code']==0,'Unsuccessful retained phase '+name)
  need(phase['observed']['seed']==-4651369264513492755,'Wrong actual seed')
  points={(r['chunk_x'],r['chunk_z']) for r in phase['observed']['chunks']}
  need(len(points)==54 and len(phase['observed']['chunks'])==54,'Incomplete/duplicate target coverage')
  if selected is None:selected=points
  need(points==selected,'Different target selection')
  archive=e/(name+'-saved-regions.zip');hashes[name]=sha(archive);dest=work/name;extract(archive,dest)
  volumes[name]=paired.saved_volume(observer,nbt,dest/'world/dimensions/minecraft/overworld/region',sorted(points),{'normal_stop':True,'exit_code':0})
 pairs={'baseline_repeat':('baseline','baseline-repeat'),'baseline_order':('baseline','baseline-reverse'),'candidate_order':('candidate','reverse'),'candidate_restart':('candidate','restart'),'baseline_to_candidate':('baseline','candidate')}
 comparisons={k:{'different_states':0,'different_water_cells':0,'changed_chunks':set(),'state_pairs':Counter(),'examples':[]} for k in pairs}
 attribution={'candidate_order_differences':0,'identical_to_corresponding_baseline':0,'other_count':0,'other_examples':[]}
 frozen={k:{'count':0,'by_type':Counter(),'by_y':Counter(),'magma_adjacent':0,'examples':[]} for k in ('baseline','candidate','reverse')}
 for cx,cz in sorted(selected):
  for sy in range(-32,32):
   sections={name:volumes[name].section((cx,sy,cz)) for name in PHASES}
   need(all(len(v)==4096 for v in sections.values()),'Incomplete section')
   for label,(left,right) in pairs.items():
    aa,bb=sections[left],sections[right]
    if aa==bb:continue
    r=comparisons[label]
    for i,(before,after) in enumerate(zip(aa,bb)):
     if before==after:continue
     x=cx*16+(i&15);y=sy*16+(i>>8);z=cz*16+((i>>4)&15)
     need((x//16,z//16)==(cx,cz),'Coordinate reconstruction failed')
     r['different_states']+=1;r['changed_chunks'].add((cx,cz));r['state_pairs'][before['Name']+' => '+after['Name']]+=1
     if -511<=y<=128 and water(before)!=water(after):r['different_water_cells']+=1
     if len(r['examples'])<40:r['examples'].append({'position':[x,y,z],'before':before,'after':after})
     if label=='candidate_order':
      attribution['candidate_order_differences']+=1
      old=sections['baseline'][i];old_reverse=sections['baseline-reverse'][i]
      if before==old and after==old_reverse:attribution['identical_to_corresponding_baseline']+=1
      else:
       attribution['other_count']+=1
       if len(attribution['other_examples'])<2000:attribution['other_examples'].append({'position':[x,y,z],'forward':before,'reverse':after,'baseline_forward':old,'baseline_reverse':old_reverse})
   if sy>8:continue
   for name,r in frozen.items():
    for i,state in enumerate(sections[name]):
     y=sy*16+(i>>8)
     if not -511<=y<=128 or state['Name'] not in FROZEN:continue
     x=cx*16+(i&15);z=cz*16+((i>>4)&15);r['count']+=1;r['by_type'][state['Name']]+=1;r['by_y'][str(y)]+=1
     neighbours=[]
     for dx,dy,dz in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
      pos=(x+dx,y+dy,z+dz)
      try:s=volumes[name].at(*pos)
      except (KeyError,IndexError,ValueError):s=None
      neighbours.append({'position':pos,'state':s})
     magma=any(n['state'] and n['state']['Name']=='minecraft:magma_block' for n in neighbours)
     if magma:r['magma_adjacent']+=1
     if len(r['examples'])<2000:r['examples'].append({'position':[x,y,z],'state':state,'adjacent_magma':magma,'neighbours':neighbours})
 for r in comparisons.values():
  r['changed_chunks']=sorted(r['changed_chunks']);r['state_pairs']=dict(r['state_pairs']);r['examples_truncated']=r['different_states']>len(r['examples'])
 for r in frozen.values():
  r['by_type']=dict(r['by_type']);r['by_y']=dict(r['by_y']);r['examples_truncated']=r['count']>len(r['examples'])
 attribution['other_examples_truncated']=attribution['other_count']>len(attribution['other_examples'])
 need(all(sha(e/(name+'-saved-regions.zip'))==value for name,value in hashes.items()),'Source archive changed')
 report={'read_only':True,'source_run':a.run_id,'source_commit':provenance['commit'],'candidate_core_sha256':runtime['candidate_core_sha256'],'source_archives_sha256':hashes,'target_chunks':54,'checked_cells_per_phase':54*1024*256,'scope':'Every saved block state in all 54 target chunks, Y=-512..511, six prior server phases. Water comparison Y=-511..128 excludes waterlogged solids, as in the original gate. Not all screenshot locations or whole-world proof.','comparisons':comparisons,'attribution':attribution,'production_accepted':False,'original_strict_result':runtime.get('bounded_regression_pass')}
 save(out/'all-target-state-review.json',report);save(out/'frozen-block-review.json',{'source_run':a.run_id,'scope':'Actual saved frozen block IDs and adjacent states in 54 target chunks, -511..128. Other blocks are not inferred to be ice from screenshots.','phases':frozen})
 print('ALL_TARGET_COMPARISON',json.dumps({k:{q:v for q,v in r.items() if q not in ('examples','state_pairs')} for k,r in comparisons.items()}),flush=True)
 print('ORDER_ATTRIBUTION',json.dumps(attribution),flush=True)
 print('FROZEN_BLOCKS',json.dumps({k:{q:v for q,v in r.items() if q!='examples'} for k,r in frozen.items()}),flush=True)
 print('READ_ONLY_REVIEW_COMPLETE',a.run_id,flush=True)
if __name__=='__main__':main()
