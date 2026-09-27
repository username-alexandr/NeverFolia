#!/usr/bin/env python3
"""Incremental Java 25 candidate, not a claim of full Gradle compilation.
Rebuilds the exact LIGHT hook and two new classes; every other class is preserved.
The experimental closure requires -Dneverfolia.r395OceanClosure=true.
"""
from pathlib import Path
import copy,hashlib,io,json,os,shutil,subprocess,urllib.request,zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';OUT.mkdir(exist_ok=True)
WORK=ROOT/'.work/r395-build';WORK.mkdir(parents=True,exist_ok=False)
CAND=ROOT/'candidate';CAND.mkdir(exist_ok=False)
BASE='411f628603ae531216c173fde1dbd8c702effb170889f72e5f2c0f1af81b6a32'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
LIGHT_SOURCE='e3679bc3c336156e16dc9740d1ae16ab19112dfbeb19915f034f46c92250f283'
LIGHT='ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask'

def digest(raw):return hashlib.sha256(raw).hexdigest()
def sha(path):return digest(Path(path).read_bytes())
def need(ok,msg):
    if not ok:raise ValueError(msg)
def find(folder,pattern,expected):
    items=[p for p in Path(folder).rglob(pattern) if p.is_file() and sha(p)==expected]
    need(len(items)==1,'Missing or ambiguous exact input '+pattern);return items[0]
def run(command,name):
    p=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (OUT/name).write_text(p.stdout);print(p.stdout,flush=True)
    need(p.returncode==0,'Command failed: '+name)
    return p.stdout

def rewrite_zip(raw,replacements):
    buffer=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as src,zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as dst:
        need(len(src.namelist())==len(set(src.namelist())),'Duplicate ZIP entries')
        need(not any(n.upper().endswith(('.SF','.RSA','.DSA','.EC')) and n.startswith('META-INF/') for n in src.namelist()),'Signed JAR requires separate build')
        for info in src.infolist():dst.writestr(copy.copy(info),replacements.get(info.filename,src.read(info)))
        for n in sorted(set(replacements)-set(src.namelist())):
            info=zipfile.ZipInfo(n,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;dst.writestr(info,replacements[n])
    value=buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(value)) as z:need(z.testzip() is None,'Repacked ZIP CRC failure')
    return value

base=find(ROOT/'baseline','server.jar',BASE)
nether=find(ROOT/'baseline','NeverNether.zip',NETHER)
pack=find(ROOT/'r393','*.zip',PACK)
libs=WORK/'libs';libs.mkdir()
base_raw=base.read_bytes()
with zipfile.ZipFile(base) as z:
    nested=[n for n in z.namelist() if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested)==1,'Expected one exact bundled server');nested=nested[0];server_raw=z.read(nested)
    versions=z.read('META-INF/versions.list').decode()
    for i,n in enumerate(z.namelist()):
        if n.endswith('.jar') and n.startswith(('META-INF/libraries/','META-INF/versions/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(z.read(n))
api_providers=[]
for p in libs.glob('*.jar'):
    with zipfile.ZipFile(p) as z:
        if 'org/bukkit/Bukkit.class' in z.namelist():api_providers.append(p)
with zipfile.ZipFile(ROOT/'debug/diagnostics.zip') as z:
    names=[n for n in z.namelist() if n.endswith('/src/minecraft/java/'+LIGHT+'.java')]
    need(len(names)==1,'Missing materialized LIGHT source');source=z.read(names[0]);need(digest(source)==LIGHT_SOURCE,'Wrong materialized LIGHT')
    if not api_providers:
        api=[]
        for name in z.namelist():
            if 'folia-api' not in name or not name.endswith('.jar'):continue
            raw=z.read(name)
            with zipfile.ZipFile(io.BytesIO(raw)) as candidate:
                if 'org/bukkit/Bukkit.class' in candidate.namelist():api.append((name,raw))
        need(len(api)==1,'Missing/ambiguous API class provider in pinned artifacts: '+str([n for n in z.namelist() if n.endswith('.jar')]))
        provider=libs/'folia-api.jar';provider.write_bytes(api[0][1]);api_providers.append(provider)
need(len(api_providers)==1,'Ambiguous Bukkit API on exact runtime classpath')
(OUT/'api-provider.json').write_text(json.dumps({'path':api_providers[0].name,'sha256':sha(api_providers[0]),'source':'pinned R38 runtime/debug artifacts'},indent=2)+'\n')
print('ACTUAL BUKKIT API',api_providers[0].name,sha(api_providers[0]),flush=True)
text=source.decode()
anchor='                net.minecraft.world.level.chunk.NeverOverworldWaterAuditR38.end(task.world, task.fromChunk, waterAuditR38);'
need(text.count(anchor)==1,'Unexpected LIGHT insertion site')
call='                net.minecraft.world.level.chunk.NeverOverworldOceanClosureR395.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R395_FINAL_AIR_CLOSURE\n'
text=text.replace(anchor,call+anchor)
light=WORK/'src'/Path(LIGHT+'.java');light.parent.mkdir(parents=True);light.write_text(text)
(OUT/'ChunkLightTask-R395.java').write_text(text)
classes=WORK/'classes';classes.mkdir()
cp=os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')))
java_sources=[str(p) for p in sorted((ROOT/'native/overworld-r395').glob('*.java'))]+[str(light)]
run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes)]+java_sources,'core-javac.log')
run(['javac','--release','25','-classpath',str(classes),'-d',str(classes),str(ROOT/'qa/field-r395/OceanConnectivityTest.java')],'solver-javac.log')
run(['java','-cp',str(classes),'OceanConnectivityTest'],'solver-tests.log')
replacements={p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class') if not p.name.startswith('OceanConnectivityTest')}
need(all(raw[:4]==b'\xca\xfe\xba\xbe' and int.from_bytes(raw[6:8],'big')==69 for raw in replacements.values()),'Wrong Java class version')
with zipfile.ZipFile(io.BytesIO(server_raw)) as z:
    old_family={n for n in z.namelist() if n==LIGHT+'.class' or n.startswith(LIGHT+'$')}
new_family={n for n in replacements if n==LIGHT+'.class' or n.startswith(LIGHT+'$')}
need(old_family==new_family,'Unexpected LIGHT inner-class set')
new_server=rewrite_zip(server_raw,replacements)
lines=versions.splitlines();updated=[];found=0
for line in lines:
    parts=line.split('\t');need(len(parts)==3,'Unrecognized versions manifest')
    if 'META-INF/versions/'+parts[2]==nested:
        need(parts[0]==digest(server_raw),'Original bundled hash mismatch');parts[0]=digest(new_server);found+=1
    updated.append('\t'.join(parts))
need(found==1,'No exact bundled versions row')
new_bundler=rewrite_zip(base_raw,{nested:new_server,'META-INF/versions.list':('\n'.join(updated)+'\n').encode()})
(CAND/'server.jar').write_bytes(new_bundler)
shutil.copyfile(pack,CAND/'NeverOverworld.zip');shutil.copyfile(nether,CAND/'NeverNether.zip')
with zipfile.ZipFile(io.BytesIO(server_raw)) as old,zipfile.ZipFile(io.BytesIO(new_server)) as new:
    untouched=[n for n in old.namelist() if n not in replacements]
    need(all(old.read(n)==new.read(n) for n in untouched),'Unrelated bundled entry changed')
report={'build_kind':'incremental javac --release 25 against exact R38 runtime and API; not full Gradle',
    'base_core_sha256':BASE,'candidate_core_sha256':digest(new_bundler),'pack_sha256':PACK,'nether_sha256':NETHER,
    'changed_or_added_classes':{n:digest(v) for n,v in sorted(replacements.items())},'unchanged_bundled_entries':len(untouched),
    'runtime_tested':False,'production_accepted':False,'experimental_default_enabled':False}
(OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n')

client_classes=WORK/'client-classes';client_classes.mkdir()
metadata_url='https://maven.fabricmc.net/net/fabricmc/fabric-loader/0.19.3/fabric-loader-0.19.3.json'
with urllib.request.urlopen(metadata_url,timeout=30) as response:loader=json.load(response)
matches=[entry for group in loader['libraries'].values() if isinstance(group,list) for entry in group if 'sponge-mixin' in entry.get('name','')]
need(len(matches)==1,'Ambiguous pinned Fabric Mixin dependency')
entry=matches[0];group,artifact,version=entry['name'].split(':');repository=entry.get('url','https://maven.fabricmc.net/')
need(repository.rstrip('/')=='https://maven.fabricmc.net','Unexpected Mixin repository')
url=repository.rstrip('/')+'/'+group.replace('.','/')+'/'+artifact+'/'+version+'/'+artifact+'-'+version+'.jar'
with urllib.request.urlopen(url,timeout=30) as response:raw=response.read()
mixin=libs/'fabric-sponge-mixin.jar';mixin.write_bytes(raw)
client_sources=[str(p) for p in (ROOT/'client/neverland-enchantment-ui/src').rglob('*.java')]
run(['javac','--release','25','-proc:none','-classpath',cp+os.pathsep+str(mixin),'-d',str(client_classes)]+client_sources,'client-javac.log')
compat=run(['javap','-classpath',str(mixin),'org.spongepowered.asm.mixin.MixinEnvironment$CompatibilityLevel'],'mixin-compatibility.log')
need('JAVA_25' in compat,'Fabric Mixin does not declare Java 25 compatibility')
translations={'aerials_bane':'Гроза летающих','antidote':'Противоядие','conductivity_curse':'Проклятие проводимости','ghasted':'Сила гаста','gravity':'Гравитация','hydro_veil':'Водяная завеса','illagers_bane':'Гроза разбойников','multishot':'Тройной выстрел','outreach':'Досягаемость','photosynthesis':'Фотосинтез','piercing':'Сквозной выстрел','power':'Мощь','spiteful':'Мстительность','swift_soar':'Стремительный полёт','traveler':'Путешественник','wax_wings':'Восковые крылья','wither_coated':'Иссушающее покрытие','non_survival_enchant':'Служебное зачарование'}
mod={'schemaVersion':1,'id':'neverland_enchantment_ui','version':'0.1.0-r395','name':'NeverLand Enchantment UI','environment':'client','description':'Hides technical Nova controller books from creative lists; preserves registries, mobs and legitimate custom enchants. Russian display names included.','mixins':['neverland-enchantment-ui.mixins.json'],'depends':{'fabricloader':'>=0.19.3','minecraft':'26.2','java':'>=25'}}
config={'required':True,'minVersion':'0.8','package':'cc.neverland.client','compatibilityLevel':'JAVA_25','client':['CreativeBookMixin'],'injectors':{'defaultRequire':1}}
with zipfile.ZipFile(CAND/'NeverLand-Enchantment-UI-Fabric-26.2-r395.jar','w',zipfile.ZIP_DEFLATED) as z:
    for p in client_classes.rglob('*.class'):z.write(p,p.relative_to(client_classes).as_posix())
    z.writestr('fabric.mod.json',json.dumps(mod,indent=2));z.writestr('neverland-enchantment-ui.mixins.json',json.dumps(config,indent=2))
    z.writestr('assets/neverland_enchantment_ui/lang/ru_ru.json',json.dumps({'enchantment.dnt.'+k:v for k,v in translations.items()},ensure_ascii=False,indent=2))
(OUT/'client-build.json').write_text(json.dumps({'compile_pass':True,'real_client_launch_tested':False,'dependency':entry['name'],'dependency_sha256':digest(raw),'mod_sha256':sha(CAND/'NeverLand-Enchantment-UI-Fabric-26.2-r395.jar')},indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
