#!/usr/bin/env python3
"""Matched-order R399 checks. Existing R397 cross-order failure is not reclassified."""
from pathlib import Path
import collections,contextlib,hashlib,importlib.util,json,sys,types
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'qa/field-r395'))
from control_contract import validate_observation,success_marker,TARGETS

def need(ok,msg):
 if not ok:raise ValueError(msg)
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def compare_saved(legacy,left,right):
 observer=load(ROOT/'scripts/probe-never-overworld-trees-villages-r1.py','observer_'+left+right)
 paired=load(ROOT/'scripts/probe-never-overworld-paired-r12.py','paired_'+left+right)
 nbt=observer.load_nbt(ROOT)
 def volume(name):return paired.saved_volume(observer,nbt,legacy.WORK/name/'world/dimensions/minecraft/overworld/region',list(TARGETS),{'normal_stop':True,'exit_code':0})
 a,b=volume(left),volume(right);changed=0;unexpected=[];protected_changed=[];protected_air=0;protected_count=0;perchunk={};transitions=collections.Counter()
 for cx,cz in sorted(TARGETS):
  boxes=paired.pdc_boxes(a.roots[(cx,cz)])
  need(boxes==paired.pdc_boxes(b.roots[(cx,cz)]),'Protected geometry changed')
  protected=set()
  for q in boxes:
   for y in range(max(-511,q[1]-1),min(128,q[4]+1)+1):
    for z in range(max(cz*16,q[2]-1),min(cz*16+15,q[5]+1)+1):
     for x in range(max(cx*16,q[0]-1),min(cx*16+15,q[3]+1)+1):protected.add((x,y,z))
  protected_count+=len(protected)
  for pos in protected:
   v=a.at(*pos);protected_air+=int(v['Name'] in ('minecraft:air','minecraft:cave_air','minecraft:void_air'))
   if v!=b.at(*pos):protected_changed.append(pos)
  count=0
  for sy in range(-32,32):
   aa=a.section((cx,sy,cz));bb=b.section((cx,sy,cz));need(len(aa)==len(bb)==4096,'Incomplete section')
   if aa==bb:continue
   for i,(v,w) in enumerate(zip(aa,bb)):
    if v==w:continue
    pos=(cx*16+(i&15),sy*16+(i>>8),cz*16+((i>>4)&15));changed+=1;count+=1;transitions[v['Name']+' => '+w['Name']]+=1
    allowed=v['Name'] in ('minecraft:air','minecraft:cave_air','minecraft:void_air') and w=={'Name':'minecraft:water','Properties':{'level':'0'}} and -511<=pos[1]<=128 and pos not in protected
    if not allowed and len(unexpected)<30:unexpected.append({'position':pos,'before':v,'after':w})
  perchunk[f'{cx},{cz}']=count
 return {'left':left,'right':right,'changed_cells':changed,'changed_chunks':sum(v>0 for v in perchunk.values()),'transitions':dict(transitions),'unexpected_examples':unexpected,'protected_cells':protected_count,'protected_air':protected_air,'protected_changed':protected_changed,'per_chunk_changes':perchunk}

def main():
 path=ROOT/'qa/field-r395/run_runtime.py';raw=path.read_bytes()
 need(hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()=='00fb8fcffea1f30252ee2a223ae4c96aee1e2fe5','Unexpected base QA runner')
 text=raw.decode().replace('neverfolia.r395OceanClosure','neverfolia.r399OceanClosure').replace('neverfolia.r395ReportDirectory','neverfolia.r399ReportDirectory')
 legacy=types.ModuleType('r399_legacy');legacy.__file__=str(path);exec(compile(text,str(path),'exec'),legacy.__dict__)
 build=json.loads((legacy.OUT/'build.json').read_text())
 need(legacy.sha(ROOT/'candidate/server.jar')==build['candidate_core_sha256'],'Candidate mismatch')
 need(legacy.sha(ROOT/'candidate/NeverOverworld.zip')==legacy.PACK and legacy.sha(ROOT/'candidate/NeverNether.zip')==legacy.NETHER,'Pack mismatch')
 plugin=legacy.prepare_plugin();phases={}
 def phase(name,folder,enabled,reverse=False):
  resultfile=folder/'plugins/R395Qa/result.json'
  if resultfile.exists():resultfile.rename(legacy.OUT/(name+'-old-result.json'))
  with (legacy.OUT/(name+'-runner.log')).open('w') as log,contextlib.redirect_stdout(log):
   r=legacy.phase(name,folder,ROOT/'candidate/server.jar',enabled,reverse)
  try:
   need(resultfile.is_file(),'No fresh QA result');fresh=json.loads(resultfile.read_text());validate_observation(fresh,reverse)
   need(fresh==r.get('observed'),'Fresh and observed results differ')
   markers=[s for s in (legacy.OUT/(name+'.log')).read_text().splitlines() if 'R395 NATURAL QA' in s]
   need(len(markers)==1 and success_marker(markers[0]),'No unique current PASS');r['fresh_verified']=True
  except Exception as error:r['pass']=False;r['fresh_error']=repr(error)
  legacy.save(legacy.OUT/(name+'-phase.json'),r);phases[name]=r
  print('R399_PHASE',name,r.get('pass'),r.get('error'),r.get('fresh_error'),flush=True)
 for name,enabled,reverse in (('control_forward',False,False),('candidate',True,False),('control_reverse',False,True),('reverse',True,True)):
  folder=legacy.setup(name,plugin);phase(name,folder,enabled,reverse)
  if name=='candidate' and phases[name]['pass']:
   phase('restart',folder,True)
   phases['restart']['saved_same_world_water_equal']=phases[name]['saved']['water_hashes']==phases['restart']['saved']['water_hashes']
 report={'production_accepted':False,'candidate_core_sha256':build['candidate_core_sha256'],'scope':'Matched schedule, 54 natural target chunks; not global determinism or all screenshots','phase_status':{k:v['pass'] for k,v in phases.items()}}
 legacy.save(legacy.OUT/'r399-runtime.json',report)
 need(set(phases)=={'control_forward','candidate','restart','control_reverse','reverse'} and all(v['pass'] for v in phases.values()),'Phase failed; evidence retained')
 report['forward']=compare_saved(legacy,'control_forward','candidate')
 report['reverse']=compare_saved(legacy,'control_reverse','reverse')
 report['restart_water_equal']=phases['candidate']['saved']['water_hashes']==phases['restart']['saved']['water_hashes']
 report['inherited_cross_order_water_equal']=phases['candidate']['saved']['water_hashes']==phases['reverse']['saved']['water_hashes']
 report['no_non_air_changes']=not any(report[k]['unexpected_examples'] or report[k]['protected_changed'] for k in ('forward','reverse'))
 report['scope_pass']=report['no_non_air_changes'] and report['restart_water_equal'] and all(report[k]['changed_cells']>0 and report[k]['protected_air']>0 for k in ('forward','reverse'))
 report['global_generation_accepted']=False
 legacy.save(legacy.OUT/'r399-runtime.json',report);print('R399_RESULT',json.dumps(report),flush=True)
 need(report['scope_pass'],'Bounded checks failed; not an accepted candidate')
if __name__=='__main__':main()
