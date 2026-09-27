#!/usr/bin/env python3
"""R38 live regressions: isolated loopback fixtures, ordinary player, saved chunks.
Every probe has its own log and work path; a failed controller never erases water
or runtime evidence. This is bounded regression coverage, not every seed/boss.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,shutil,sys,zipfile
ROOT=Path(__file__).resolve().parents[2]
SEED=-4651369264513492755
TARGETS=((0,0),(-4,3),(0,-1),(3,0),(2,3),(12,4))
CHUNKS=sorted({(cx+dx,cz+dz) for cx,cz in TARGETS for dx in (-1,0,1) for dz in (-1,0,1)})
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def sha(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,data):path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
def require(ok,message):
 if not ok:raise AssertionError(message)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('jar','overworld','nether','controller-plugin','trial-plugin','output'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--source-sha',required=True);p.add_argument('--work',type=Path);a=p.parse_args()
 for name in ('jar','overworld','nether','controller_plugin','trial_plugin','output'):setattr(a,name,getattr(a,name).resolve())
 out=a.output;out.mkdir(parents=True,exist_ok=True)
 work=(a.work or ROOT/'.work/field-r38').resolve();work.mkdir(parents=True,exist_ok=False)
 observer=load('r38_observer',ROOT/'scripts/probe-never-overworld-trees-villages-r1.py')
 paired=load('r38_paired',ROOT/'scripts/probe-never-overworld-paired-r12.py');Server=paired.make_server(observer)
 field20=load('r38_field20',ROOT/'qa/field-r20/probe-user-seed.py');nbt=observer.load_nbt(ROOT)
 client_module=load('r38_client',ROOT/'qa/field-r38/loopback_client.py')
 protocols=ROOT/'.work/Folia/folia-server/src/minecraft/java/net/minecraft/network/protocol/game/GameProtocols.java'
 if not protocols.exists():protocols=ROOT.parent/'materialized/folia-server/src/minecraft/java/net/minecraft/network/protocol/game/GameProtocols.java'
 text=protocols.read_text();split=text.index('CLIENTBOUND_TEMPLATE')
 sb={n:i for i,n in enumerate(re.findall(r'\.addPacket\([^,]+\.([A-Z_]+),',text[text.index('SERVERBOUND_TEMPLATE'):split]))}
 cb={n:i for i,n in enumerate(re.findall(r'\.addPacket\([^,]+\.([A-Z_]+),',text[split:]),1)}
 report={'schema':1,'source_sha':a.source_sha,'seed':SEED,'jar_sha256':sha(a.jar),'overworld_sha256':sha(a.overworld),'nether_sha256':sha(a.nether),'phases':{},'scope':'48 saved target chunks; full LIGHT-chain water provenance; two normal trial configurations; two requested generation orders and restart; not all worlds, bosses or runtime physics'}
 def setup(name,plugin=None):
  folder=work/name;folder.mkdir();(folder/'world/datapacks').mkdir(parents=True)
  for source,target in ((a.overworld,'NeverOverworld.zip'),(a.nether,'NeverNether.zip')):shutil.copyfile(source,folder/'world/datapacks'/target)
  if plugin:(folder/'plugins').mkdir();shutil.copyfile(plugin,folder/'plugins'/plugin.name)
  (folder/'eula.txt').write_text('eula=true\n')
  (folder/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nonline-mode=false\nenforce-secure-profile=false\nserver-ip=127.0.0.1\nserver-port=25595\nview-distance=2\nsimulation-distance=2\nspawn-protection=0\nenable-status=false\npause-when-empty-seconds=-1\nnetwork-compression-threshold=-1\ngamemode=survival\ndifficulty=normal\n')
  return folder
 def load_targets(server,reverse=False):
  if reverse:
   for pos in reversed(CHUNKS):server.load_dimension([pos],'minecraft:overworld',dwell=0,serial_generation=True)
  else:server.load_dimension(CHUNKS,'minecraft:overworld',dwell=4,serial_generation=False)
  # Equal post-generation fluid-tick exposure in both order variants.
  # Reverse singleton loads otherwise unload immediately, unlike forward batches.
  server.load_dimension(CHUNKS,'minecraft:overworld',dwell=10,serial_generation=False)
 def saved(folder):
  return paired.saved_volume(observer,nbt,folder/'world/dimensions/minecraft/overworld/region',CHUNKS,{'normal_stop':True,'exit_code':0})
 def water_hashes(volume):
  hashes={}
  for cx,cz in CHUNKS:
   digest=hashlib.sha256()
   for y in range(-511,129):
    buf=bytearray(256)
    for z in range(16):
     for x in range(16):
      state=volume.at(cx*16+x,y,cz*16+z)
      require(isinstance(state,dict) and 'Name' in state,'unreadable persisted cell')
      if state['Name']=='minecraft:water':buf[z*16+x]=1+int(state.get('Properties',{}).get('level','0'))
      elif state.get('Properties',{}).get('waterlogged')=='true' or state['Name'] in {'minecraft:kelp','minecraft:kelp_plant','minecraft:seagrass','minecraft:tall_seagrass','minecraft:bubble_column'}:buf[z*16+x]=1
    digest.update(buf)
   hashes[f'{cx},{cz}']=digest.hexdigest()
  return hashes
 def run_phase(name,folder,plugin_kind=None,reverse=False,audit=None):
  server=None;client=None;phase={'pass':False,'normal_stop':False};log=out/(name+'.log')
  try:
   args=['-Dneverfolia.debugFloodSeams=true']
   if audit:args+=['-Dneverfolia.waterAuditDirectory='+str(audit)]
   server=Server(a.jar,folder,log,java_args=args);server.wait(r'Done \(',timeout=300)
   if plugin_kind=='controller':
    server.wait(r'R37 DUNGEON QA (?:PASS|FAIL)',timeout=120)
    result=json.loads((folder/'plugins/R37DungeonQa/result.json').read_text());save(out/'r38-live-controller.json',result);phase['controller']=result
   if plugin_kind=='trial':
    server.wait('R38 TRIAL FIXTURE READY',timeout=120)
    client=client_module.Client(25595,cb['CLIENTBOUND_KEEP_ALIVE'],cb['CLIENTBOUND_PLAYER_POSITION'],sb['SERVERBOUND_KEEP_ALIVE'])
    server.wait(r'R38 NATURAL TRIAL QA (?:PASS|FAIL)',timeout=160)
    result=json.loads((folder/'plugins/R38TrialQa/result.json').read_text());save(out/'r38-natural-trial.json',result);phase['trial']=result
    client.close();save(out/'r38-loopback-client.json',client.events);client=None
   if plugin_kind!='controller':server.disable_random_ticks();load_targets(server,reverse)
   phase['exit_code']=server.stop();phase['normal_stop']=phase['exit_code']==0
   require(phase['normal_stop'],'server did not stop normally')
   text=log.read_text(errors='replace')
   bad=[line for line in text.splitlines() if any(v in line for v in ('Missing chunkholder when required','[ChunkTaskScheduler] Chunk system error','Block-attached entity at invalid position','Empty or non-existent pool: betterwitchhuts:mobs','Empty or non-existent pool: nova_structures:pale_residence/decor_inside','Unknown registry key in ResourceKey[minecraft:root / minecraft:attribute]: porting_lib:'))]
   phase['targeted_console_errors']=bad
   if plugin_kind!='controller':
    volume=saved(folder);phase['water_hashes']=water_hashes(volume);phase['seams']=field20.seam_audit(volume,CHUNKS)
    phase['surface_water_columns']=len(field20.surface_water_columns(volume,CHUNKS))
    phase['camera_samples_diagnostic_only']=[{'pos':pos,'state':volume.at(*pos)} for pos in ((14,52,11),(8,52,14),(-53,23,50))]
    require(phase['seams']['max_boundary_water_air_faces']<=192,'large saved chunk-boundary water wall')
    require(phase['surface_water_columns']>0,'ocean disappeared')
   require(not bad,'targeted console error')
   require(all(phase[key].get('pass') is True for key in ('controller','trial') if key in phase),'live entity check failed')
   phase['pass']=True
  except Exception as error:phase['error']=repr(error)
  finally:
   if client:client.close();save(out/'r38-loopback-client.json',client.events)
   if server:server.close()
  report['phases'][name]=phase;save(out/'r38-live-qa.json',report);print(name,json.dumps({k:v for k,v in phase.items() if k in ('pass','error','exit_code')}),flush=True)
  return phase
 controller=run_phase('r38-controller',setup('controller',a.controller_plugin),'controller')
 audit=out/'r38-water-audit';trial=setup('trial',a.trial_plugin)
 first=run_phase('r38-trial-water',trial,'trial',audit=audit)
 rows={p.stem:json.loads(p.read_text()) for p in audit.glob('*.json')}
 missing=[pos for pos in CHUNKS if f'{pos[0]}_{pos[1]}' not in rows]
 water={'sampled_chunks':len(CHUNKS),'audited_chunks':len(rows),'missing_target_chunks':missing,'failing_chunks':[r for r in rows.values() if not r.get('pass')], 'totals':{k:sum(r[k] for r in rows.values()) for k in ('native_water','preserved_native_water','removed_native_water','changed_native_water_state','explicit_dry_mine_changes','new_water','below_native_surface_additions')}}
 water['pass']=bool(rows) and not missing and not water['failing_chunks'];report['water_provenance']=water;save(out/'r38-water-provenance.json',water)
 if first['normal_stop']:
  for jar in (trial/'plugins').glob('*.jar'):jar.rename(jar.with_suffix('.disabled'))
  restart=run_phase('r38-restart',trial)
  report['restart_same_water']=first.get('water_hashes') is not None and restart.get('water_hashes')==first.get('water_hashes')
 else:report['restart_same_water']=False
 second_audit=out/'r38-reverse-audit'
 reverse=run_phase('r38-reverse-water',setup('reverse'),reverse=True,audit=second_audit)
 reverse_rows={p.stem:json.loads(p.read_text()) for p in second_audit.glob('*.json')}
 report['reverse_audit_complete']=all(f'{cx}_{cz}' in reverse_rows for cx,cz in CHUNKS)
 report['reverse_audit_pass']=bool(reverse_rows) and all(r.get('pass') is True for r in reverse_rows.values())
 inherited=[];overlay=[]
 for cx,cz in CHUNKS:
  k=f'{cx}_{cz}';left=rows.get(k);right=reverse_rows.get(k)
  if not left or not right:continue
  if left.get('before_water_sha256')!=right.get('before_water_sha256'):inherited.append([cx,cz])
  elif left.get('after_water_sha256')!=right.get('after_water_sha256'):overlay.append([cx,cz])
 report['generation_order']={'inherited_pre_light_differences':inherited,'overlay_differences_for_identical_input':overlay,'saved_water_equal':first.get('water_hashes') is not None and first.get('water_hashes')==reverse.get('water_hashes')}
 report['pass']=all(v.get('pass') for v in report['phases'].values()) and water['pass'] and report['restart_same_water'] and report['reverse_audit_complete'] and report['reverse_audit_pass'] and not inherited and not overlay and report['generation_order']['saved_water_equal']
 save(out/'r38-live-qa.json',report)
 with zipfile.ZipFile(out/'r38-water-evidence.zip','w',zipfile.ZIP_DEFLATED) as z:
  for folder in (audit,second_audit):
   for path in folder.glob('*.json'):z.write(path,str(path.relative_to(out)))
 require(report['pass'],'R38 acceptance failed; see r38-live-qa.json (all evidence retained)')
if __name__=='__main__':main()
