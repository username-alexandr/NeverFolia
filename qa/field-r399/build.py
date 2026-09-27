#!/usr/bin/env python3
"""Incremental R399 build on exact tested R396; never a full Gradle-build claim."""
from pathlib import Path
import hashlib,io,json,os,shutil,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'qa/field-r395'))
from jar_packaging import rewrite_zip
OUT=ROOT/'artifacts';OUT.mkdir(exist_ok=True)
WORK=ROOT/'.work/r395-build';WORK.mkdir(parents=True,exist_ok=False)
CAND=ROOT/'candidate';CAND.mkdir(exist_ok=False)
BASE='ae152b6caaa26bc75fde1d917ba23d03856959266b63b8224642cbfa644f2d19'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
LIGHT='ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask'
PYRAMID='net/minecraft/world/level/chunk/status/ChunkPyramid'
def need(ok,msg):
 if not ok:raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def run(cmd,name):
 p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 (OUT/name).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'Command failed: '+name)
def pick(folder,name,expected):
 ps=[p for p in folder.rglob(name) if p.is_file() and sha(p.read_bytes())==expected]
 need(len(ps)==1,'Missing/ambiguous exact input: '+name);return ps[0]
base=pick(ROOT/'baseline','server.jar',BASE);raw=base.read_bytes()
for name,digest in (('NeverOverworld.zip',PACK),('NeverNether.zip',NETHER)):
 shutil.copyfile(pick(ROOT/'baseline',name,digest),CAND/name)
libs=WORK/'libs';libs.mkdir()
with zipfile.ZipFile(io.BytesIO(raw)) as z:
 nested=[n for n in z.namelist() if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
 need(len(nested)==1,'Unexpected bundled server');nested=nested[0];server=z.read(nested);versions=z.read('META-INF/versions.list').decode()
 for i,n in enumerate(z.namelist()):
  if n.endswith('.jar') and n.startswith(('META-INF/libraries/','META-INF/versions/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(z.read(n))
cp=os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')))
with zipfile.ZipFile(ROOT/'debug/diagnostics.zip') as z:
 src=[]
 for target,digest in ((LIGHT,'e3679bc3c336156e16dc9740d1ae16ab19112dfbeb19915f034f46c92250f283'),(PYRAMID,'24c0e2b6c1cf7f644031126573055a4994f697bc61286e36727b1661da9074f5')):
  names=[n for n in z.namelist() if n.endswith('/src/minecraft/java/'+target+'.java')];need(len(names)==1,'Missing exact source '+target)
  b=z.read(names[0]);need(sha(b)==digest,'Materialized source changed');text=b.decode()
  if target==LIGHT:
   anchor='                net.minecraft.world.level.chunk.NeverOverworldWaterAuditR38.end(task.world, task.fromChunk, waterAuditR38);'
   need(text.count(anchor)==1,'LIGHT anchor mismatch')
   text=text.replace(anchor,'                net.minecraft.world.level.chunk.NeverOverworldOceanClosureR399.apply(task.world, task.neverOverworldNeighbours, task.fromChunk);\n'+anchor)
  else:
   anchor='.step(ChunkStatus.LIGHT, s -> s.addRequirement(ChunkStatus.INITIALIZE_LIGHT, 1).setTask(ChunkStatusTasks::light))'
   need(text.count(anchor)==1,'Pyramid anchor mismatch')
   text=text.replace(anchor,'.step(ChunkStatus.LIGHT, s -> s.addRequirement(ChunkStatus.INITIALIZE_LIGHT, 1).addRequirement(ChunkStatus.FEATURES, 3).setTask(ChunkStatusTasks::light))')
  p=WORK/'src'/(target+'.java');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);src.append(str(p))
  (OUT/Path(p).name).write_text(text)
classes=WORK/'classes';classes.mkdir()
src += [str(p) for p in sorted((ROOT/'native/overworld-r399').glob('*.java'))]
run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes)]+src,'core-javac.log')
run(['javac','--release','25','-classpath',str(classes),'-d',str(classes),str(ROOT/'qa/field-r399/ConnectivityTest.java')],'test-javac.log')
run(['java','-Xmx256M','-cp',str(classes),'ConnectivityTest'],'solver-tests.log')
changes={p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class') if not p.name.startswith('ConnectivityTest')}
need(all(int.from_bytes(b[6:8],'big')==69 for b in changes.values()),'Wrong class version')
for family in (LIGHT,PYRAMID):
 with zipfile.ZipFile(io.BytesIO(server)) as z:old={n for n in z.namelist() if n==family+'.class' or n.startswith(family+'$')}
 new={n for n in changes if n==family+'.class' or n.startswith(family+'$')};need(old==new,'Inner class family differs: '+family)
newserver=rewrite_zip(server,changes)
lines=[];found=0
for line in versions.splitlines():
 parts=line.split('\t');need(len(parts)==3,'Versions manifest invalid')
 if 'META-INF/versions/'+parts[2]==nested:
  need(parts[0]==sha(server),'Base manifest mismatch');parts[0]=sha(newserver);found+=1
 lines.append('\t'.join(parts))
need(found==1,'Versions row missing')
newjar=rewrite_zip(raw,{nested:newserver,'META-INF/versions.list':('\n'.join(lines)+'\n').encode()})
(CAND/'server.jar').write_bytes(newjar)
with zipfile.ZipFile(io.BytesIO(server)) as a,zipfile.ZipFile(io.BytesIO(newserver)) as b:
 unchanged=[n for n in a.namelist() if n not in changes];need(all(a.read(n)==b.read(n) for n in unchanged),'Unrelated entry modified')
report={'base_core_sha256':BASE,'candidate_core_sha256':sha(newjar),'overworld_sha256':PACK,'nether_sha256':NETHER,'build_kind':'incremental Java 25 on R396; NOT full Gradle','changed_classes':{n:sha(v) for n,v in changes.items()},'unchanged_entries':len(unchanged),'r396_policy_preserved':True,'witness_chunks':25,'feature_dependency_radius':3,'production_accepted':False}
(OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
