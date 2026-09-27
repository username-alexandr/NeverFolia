#!/usr/bin/env python3
"""Private CI worlds; fresh process evidence, saved-state comparisons, no user files."""
from pathlib import Path
from collections import Counter
import hashlib,importlib.util,json,os,queue,shutil,subprocess,threading,time,uuid,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';WORK=ROOT/'.work/r40-runtime'
CENTERS=((7,1),(1,-4),(-197,-217),(-169,-250),(-189,-223),(-1699,-769),(-202,-213))
TARGETS=sorted({(cx+dx,cz+dz) for cx,cz in CENTERS for dx in (-1,0,1) for dz in (-1,0,1)},key=lambda p:f'{p[0]},{p[1]}')
SEED=-4651369264513492755
AQUATIC={'minecraft:water','minecraft:bubble_column','minecraft:kelp','minecraft:kelp_plant','minecraft:seagrass','minecraft:tall_seagrass'}
BAD=('Failed to load registries','Failed to load datapacks','Overworld settings missing','Unknown registry key','Block-attached entity at invalid position','Chunk system error','Missing chunkholder when required','Exception in thread','Cannot retain R40')
def need(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
observer=load('r40_observer',ROOT/'scripts/probe-never-overworld-trees-villages-r1.py');paired=load('r40_paired',ROOT/'scripts/probe-never-overworld-paired-r12.py');nbt=observer.load_nbt(ROOT)
def volume(folder):return paired.saved_volume(observer,nbt,folder/'world/dimensions/minecraft/overworld/region',TARGETS,{'normal_stop':True,'exit_code':0})
def state_key(s):return (s['Name'],tuple(sorted(s.get('Properties',{}).items())))
def saved(folder,phase,live):
 v=volume(folder);full={};water={};counts={};encoding={}
 for cx,cz in TARGETS:
  h=hashlib.sha256();wm=bytearray(640*256);ct=Counter()
  for sy in range(-32,32):
   section=v.section((cx,sy,cz));need(len(section)==4096,'Invalid section')
   for i,s in enumerate(section):
    k=state_key(s)
    if k not in encoding:
     b=json.dumps(k,separators=(',',':')).encode();encoding[k]=len(b).to_bytes(4,'big')+b
    h.update(encoding[k]);y=sy*16+(i>>8)
    if -511<=y<=128:
     ct[s['Name']]+=1
     if s['Name']=='minecraft:water':wm[((y+511)<<8)|(i&255)]=1+int(s.get('Properties',{}).get('level','0'))
     elif s['Name'] in AQUATIC:wm[((y+511)<<8)|(i&255)]=1
  key=f'{cx},{cz}';full[key]=h.hexdigest();water[key]=hashlib.sha256(wm).hexdigest();counts[key]=dict(ct)
 for row in live['chunks']:
  key=f"{row['chunk_x']},{row['chunk_z']}"
  need(row['water_sha256']==water[key],'Snapshot/saved water mismatch '+key)
  need(Counter(row['block_counts'])==Counter(counts[key]),'Snapshot/saved block counts mismatch '+key)
 report={'full_state_hashes':full,'water_hashes':water,'counts':counts,'scope':'Name+Properties, full Y=-512..511. No block-entity content/entities.'};save(OUT/(phase+'-saved.json'),report)
 reg=folder/'world/dimensions/minecraft/overworld/region'
 with zipfile.ZipFile(OUT/(phase+'-regions.zip'),'w',zipfile.ZIP_DEFLATED) as z:
  for p in sorted({reg/f'r.{cx//32}.{cz//32}.mca' for cx,cz in TARGETS}):z.write(p,p.relative_to(folder).as_posix())
  for p in reg.glob('c.*.*.mcc'):z.write(p,p.relative_to(folder).as_posix())
  for p in (folder/'world').rglob('level.dat'):z.write(p,p.relative_to(folder).as_posix())
 return report

def phase(name,variant,plugin,reverse=False,restart=None):
 folder=restart or WORK/name;jar=ROOT/variant/'server.jar';nonce=uuid.uuid4().hex;result={'pass':False,'variant':variant,'nonce':nonce,'reverse':reverse,'jar_sha256':sha(jar)};p=None;reader=None;lines=[];events=queue.Queue()
 proof=OUT/('proof-'+name);proof.mkdir(exist_ok=False)
 try:
  if restart is None:
   folder.mkdir();packs=folder/'world/datapacks';packs.mkdir(parents=True)
   for f in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(ROOT/variant/f,packs/f)
   (folder/'plugins').mkdir();shutil.copyfile(plugin,folder/'plugins/R40Qa.jar')
   (folder/'eula.txt').write_text('eula=true\n')
   (folder/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25640\nonline-mode=true\nenable-rcon=false\nenable-query=false\nenable-status=false\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n')
  prior=folder/'plugins/R40Qa/result.json'
  if prior.exists():shutil.copyfile(prior,OUT/(name+'-prior-result.json'));prior.unlink()
  cmd=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G',f'-Dneverfolia.qaNonce={nonce}',f'-Dneverfolia.qaReverse={str(reverse).lower()}',f'-Dneverfolia.r395OceanClosure=true',f'-Dneverfolia.r40OceanClosure={str(variant!="reference3910").lower()}',f'-Dneverfolia.r395ReportDirectory={proof}',f'-Dneverfolia.r40ReportDirectory={proof}','-jar',str(jar),'--nogui']
  result['command']=cmd;p=subprocess.Popen(cmd,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,encoding='utf-8',errors='replace')
  def pump():
   with (OUT/(name+'.log')).open('w') as log:
    for line in p.stdout:lines.append(line);log.write(line);log.flush();events.put(line)
   events.put(None)
  reader=threading.Thread(target=pump,daemon=True);reader.start();deadline=time.monotonic()+720;marker=False
  while time.monotonic()<deadline:
   try:l=events.get(timeout=1)
   except queue.Empty:
    if p.poll() is not None:break
    continue
   if l is None:break
   if 'R40 SAMPLE' in l:print(name,l.rstrip(),flush=True)
   if 'R40 NATURAL QA' in l:
    need('R40 NATURAL QA PASS '+nonce in l,'Current process QA failed');marker=True;break
  need(marker,'Current process did not complete QA');live=json.loads(prior.read_text());result['observed']=live
  need(live['pass'] is True and live['nonce']==nonce and live['seed']==SEED and live['reverse'] is reverse,'Bad result identity')
  target=list(reversed(TARGETS)) if reverse else TARGETS
  need(live['completed']==63 and [(r['chunk_x'],r['chunk_z']) for r in live['chunks']]==target,'Wrong or incomplete coordinates')
  p.stdin.write('stop\n');p.stdin.flush();result['exit_code']=p.wait(timeout=150);reader.join(timeout=20)
  need(result['exit_code']==0 and not reader.is_alive() and any('Done (' in l for l in lines),'Unclean shutdown')
  result['targeted_errors']=[l.rstrip() for l in lines if any(t in l for t in BAD)];need(not result['targeted_errors'],'Runtime error in sample')
  result['saved']=saved(folder,name,live)
  records=[json.loads(f.read_text()) for f in proof.glob('*.json')];selected=[r for r in records if (r['chunk_x'],r['chunk_z']) in set(TARGETS)]
  result['proof']={'target_records':len(selected),'all_records':len(records),'missing_target':sorted(set(TARGETS)-{(r['chunk_x'],r['chunk_z']) for r in selected}),'added':sum(r['added_air_to_water'] for r in selected),'missing_cache':sum(r['missing_cache_chunks'] for r in selected),'conflicts':sum(r['snapshot_write_conflicts'] for r in selected)}
  if restart is None:
   need(not result['proof']['missing_target'] and len(selected)==63,'Missing or duplicate proof')
   need(not result['proof']['missing_cache'] and not result['proof']['conflicts'],'Incomplete cache or conflicting writes')
   need(all(r['native_aquatic_cells']==r['preserved_aquatic_cells'] for r in records),'Original water not preserved')
  result['pass']=True
 except Exception as e:result['error']=repr(e)
 finally:
  if p is not None and p.poll() is None:
   try:p.stdin.write('stop\n');p.stdin.flush();p.wait(timeout=40)
   except Exception:
    p.terminate()
    try:p.wait(timeout=10)
    except subprocess.TimeoutExpired:p.kill();p.wait(timeout=10)
  if reader:reader.join(timeout=10)
  save(OUT/(name+'-phase.json'),result)
 print('R40_PHASE',name,json.dumps({k:v for k,v in result.items() if k in ('pass','error','exit_code','proof')}),flush=True)
 return result,folder

def compare(a,b,name):
 left=volume(a);right=volume(b);changed=Counter();others=0;protected_changes=0;changed_chunks=set();examples=[];preserved_air=0;changed_ice=0
 for cx,cz in TARGETS:
  boxes=paired.pdc_boxes(left.roots[(cx,cz)])
  need(boxes==paired.pdc_boxes(right.roots[(cx,cz)]),'Protection geometry differs '+str((cx,cz)))
  for sy in range(-32,32):
   for i,(old,new) in enumerate(zip(left.section((cx,sy,cz)),right.section((cx,sy,cz)))):
    x=cx*16+(i&15);y=sy*16+(i>>8);z=cz*16+((i>>4)&15)
    is_protected=-511<=y<=128 and any(bb[0]-1<=x<=bb[3]+1 and bb[1]-1<=y<=bb[4]+1 and bb[2]-1<=z<=bb[5]+1 for bb in boxes)
    if is_protected and old['Name'] in ('minecraft:air','minecraft:cave_air') and old==new:preserved_air+=1
    if old==new:continue
    changed_chunks.add((cx,cz));changed[old['Name']+' => '+new['Name']]+=1
    acceptable=old['Name'] in ('minecraft:air','minecraft:cave_air') and new=={'Name':'minecraft:water','Properties':{'level':'0'}} and -511<=y<=128
    if not acceptable:others+=1
    if is_protected:protected_changes+=1
    if 'ice' in old['Name'] or 'ice' in new['Name']:changed_ice+=1
    if len(examples)<100:examples.append({'pos':[x,y,z],'before':old,'after':new,'protected':is_protected})
 out={'changed_cells':sum(changed.values()),'changed_chunks':len(changed_chunks),'transitions':dict(changed),'non_air_water_changes':others,'protected_changes':protected_changes,'preserved_protected_air':preserved_air,'ice_changes':changed_ice,'examples':examples}
 save(OUT/(name+'.json'),out);print('R40_COMPARE',name,json.dumps({k:v for k,v in out.items() if k!='examples'}),flush=True);return out

def main():
 WORK.mkdir(parents=True,exist_ok=False);need(len(TARGETS)==63,'Bad sample')
 cp=(ROOT/'.work/r40-build/classpath.txt').read_text();classes=WORK/'classes';classes.mkdir()
 p=subprocess.run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),str(ROOT/'qa/field-r40/R40Qa.java')],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 (OUT/'observer-javac.log').write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'Observer compile failed')
 plugin=WORK/'R40Qa.jar'
 with zipfile.ZipFile(plugin,'w',zipfile.ZIP_DEFLATED) as z:
  for p in classes.rglob('*.class'):z.write(p,p.relative_to(classes).as_posix())
  z.writestr('plugin.yml',"name: R40Qa\nversion: '1'\nmain: R40Qa\napi-version: '26.2'\nfolia-supported: true\n")
 build=json.loads((OUT/'build40.json').read_text());report={'production_accepted':False,'phases':{},'comparisons':{},'build':build};folders={}
 for name,variant,rev in [('reference','reference3910',False),('control','control3x3',False),('wide','wide40',False),('control_reverse','control3x3',True),('wide_reverse','wide40',True)]:
  need(sha(ROOT/variant/'server.jar')==build['variants'][variant]['jar_sha256'],'Unexpected executable')
  report['phases'][name],folders[name]=phase(name,variant,plugin,rev)
  save(OUT/'runtime40.json',report)
 if report['phases']['wide']['pass']:report['phases']['restart'],folders['restart']=phase('restart','wide40',plugin,restart=folders['wide'])
 if all(r['pass'] for r in report['phases'].values()) and 'restart' in report['phases']:
  for label,a,b in [('widening','control','wide'),('widening_reverse','control_reverse','wide_reverse'),('schedule_effect','reference','control')]:report['comparisons'][label]=compare(folders[a],folders[b],label)
  report['restart_equal']=report['phases']['wide']['saved']['full_state_hashes']==report['phases']['restart']['saved']['full_state_hashes']
  report['bounded_pass']=report['restart_equal'] and all(report['comparisons'][k]['non_air_water_changes']==0 and report['comparisons'][k]['protected_changes']==0 for k in ('widening','widening_reverse'))
 else:report['bounded_pass']=False
 save(OUT/'runtime40.json',report);print('R40_FINAL',json.dumps({'bounded_pass':report['bounded_pass'],'phases':{k:r['pass'] for k,r in report['phases'].items()},'production_accepted':False}),flush=True)
 if not report['bounded_pass']:raise SystemExit('R40 not accepted; retained failures')
if __name__=='__main__':main()
