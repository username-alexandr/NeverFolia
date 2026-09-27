#!/usr/bin/env python3
"""Isolated synthetic FULL-chunk regression; not natural-generation acceptance."""
from pathlib import Path
import hashlib,json,os,queue,shutil,subprocess,threading,time,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts'
WORK=ROOT/'.work/r398-guard-live'
EXPECTED={'NeverOverworld.zip':'a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be','NeverNether.zip':'5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'}
BASE='411f628603ae531216c173fde1dbd8c702effb170889f72e5f2c0f1af81b6a32'
def need(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def main():
 WORK.mkdir(parents=True,exist_ok=False);OUT.mkdir(exist_ok=True)
 build=json.loads((OUT/'build.json').read_text());need(sha(ROOT/'baseline/server.jar')==BASE,'Wrong baseline')
 need(sha(ROOT/'candidate/server.jar')==build['candidate_core_sha256'],'Wrong candidate')
 for name,value in EXPECTED.items():need(sha(ROOT/'candidate'/name)==value,'Pack changed: '+name)
 libs=sorted((ROOT/'.work/r395-build/libs').glob('*.jar'));need(bool(libs),'Actual runtime dependencies absent')
 classes=WORK/'classes';classes.mkdir()
 cmd=['javac','--release','25','-proc:none','-classpath',os.pathsep.join(map(str,libs)),'-d',str(classes),str(ROOT/'qa/field-r398/R398FullChunkQa.java')]
 result=subprocess.run(cmd,capture_output=True,text=True);(OUT/'r398-qa-javac.log').write_text(result.stdout+result.stderr);print(result.stdout+result.stderr,flush=True);need(result.returncode==0,'Fixture javac failed')
 plugin=WORK/'R398FullQa.jar'
 with zipfile.ZipFile(plugin,'w',zipfile.ZIP_DEFLATED) as z:
  for p in classes.rglob('*.class'):z.write(p,p.relative_to(classes).as_posix())
  z.writestr('plugin.yml',"name: R398FullQa\nversion: '1'\nmain: R398FullChunkQa\napi-version: '26.2'\nfolia-supported: true\n")
 def setup(name):
  folder=WORK/name;folder.mkdir();packs=folder/'world/datapacks';packs.mkdir(parents=True)
  for file in EXPECTED:shutil.copyfile(ROOT/'candidate'/file,packs/file)
  (folder/'plugins').mkdir();shutil.copyfile(plugin,folder/'plugins/R398FullQa.jar')
  (folder/'eula.txt').write_text('eula=true\n')
  (folder/'server.properties').write_text('level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25608\nonline-mode=true\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\nenable-rcon=false\nenable-query=false\nenable-status=false\n')
  return folder
 def phase(name,folder,jar,fixed):
  record={'pass':False};process=None;reader=None;lines=[];events=queue.Queue()
  try:
   command=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G',f'-Dneverfolia.qaFullGuard={str(fixed).lower()}','-Dneverfolia.r395OceanClosure=false','-jar',str(jar),'--nogui']
   record['command']=command;record['jar_sha256']=sha(jar)
   process=subprocess.Popen(command,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
   def pump():
    with (OUT/(name+'.log')).open('w') as f:
     for line in process.stdout:lines.append(line);f.write(line);f.flush();events.put(line)
    events.put(None)
   reader=threading.Thread(target=pump,daemon=True);reader.start();deadline=time.monotonic()+300;ready=False;done=False
   while time.monotonic()<deadline and not (ready and done):
    try:line=events.get(timeout=1)
    except queue.Empty:
     need(process.poll() is None,'Server exited early');continue
    need(line is not None,'Log ended before test result')
    if 'Done (' in line:ready=True
    if 'R398 FULL QA' in line:done=True
   need(ready and done,'Incomplete actual server run')
   record['fixture']=json.loads((folder/'plugins/R398FullQa/result.json').read_text())
   process.stdin.write('stop\n');process.stdin.flush();record['exit_code']=process.wait(timeout=120);reader.join(timeout=10)
   bad=('Failed to load registries','Failed to load datapacks','[ChunkTaskScheduler] Chunk system error','Missing chunkholder when required','Exception in thread','Exception executing task')
   record['targeted_errors']=[s.strip() for s in lines if any(x in s for x in bad)]
   need(record['exit_code']==0,'Abnormal stop');need(not record['targeted_errors'],'Runtime error')
   need(record['fixture'].get('pass') is True and len(record['fixture'].get('cases',[]))==4,'FULL regression failed')
   need(record['fixture']['expect_full_guard']==fixed,'Wrong fixture mode')
   need(all(sha(folder/'world/datapacks'/k)==v for k,v in EXPECTED.items()),'Pack copy changed')
   record['pass']=True
  except Exception as error:record['error']=repr(error)
  finally:
   if process is not None and process.poll() is None:
    try:process.stdin.write('stop\n');process.stdin.flush();process.wait(timeout=30)
    except Exception:
     process.terminate()
     try:process.wait(timeout=10)
     except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
   if reader is not None:reader.join(timeout=10)
   save(OUT/(name+'.json'),record)
  print(name,json.dumps({k:v for k,v in record.items() if k in ('pass','error','exit_code','fixture')},ensure_ascii=False),flush=True)
  return record
 report={'scope':'Synthetic direct FULL cleanup calls on baseline and candidate, plus repeated server start. Not an actual lighting-engine relight request; not natural water acceptance.','production_accepted':False,'candidate_sha256':build['candidate_core_sha256'],'phases':{}}
 report['phases']['baseline']=phase('r398-full-baseline',setup('baseline'),ROOT/'baseline/server.jar',False)
 fixed_folder=setup('candidate');report['phases']['candidate']=phase('r398-full-candidate',fixed_folder,ROOT/'candidate/server.jar',True)
 if report['phases']['candidate']['pass']:report['phases']['restart']=phase('r398-full-restart',fixed_folder,ROOT/'candidate/server.jar',True)
 report['pass']=len(report['phases'])==3 and all(r.get('pass') for r in report['phases'].values())
 save(OUT/'r398-full-guard.json',report);need(report['pass'],'FULL guard regression failed; all evidence retained')
if __name__=='__main__':main()
