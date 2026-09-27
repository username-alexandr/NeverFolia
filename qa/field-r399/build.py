#!/usr/bin/env python3
"""Incremental real-Java build of mine guard on exact R396. Not full Gradle."""
from pathlib import Path
import hashlib,importlib.util,io,json,os,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';WORK=ROOT/'.work/r399-build';CAND=ROOT/'candidate'
BASE='ae152b6caaa26bc75fde1d917ba23d03856959266b63b8224642cbfa644f2d19'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
MINE='net/minecraft/world/level/chunk/NeverOverworldDryMinesR12'
POLICY='net/minecraft/world/level/chunk/NeverOverworldWaterPolicyR38.class'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(args,name):
    r=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    (OUT/name).write_text(r.stdout);print(r.stdout,flush=True);need(r.returncode==0,'Failed '+name)
def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(len(z.namelist())==len(set(z.namelist())) and z.testzip() is None,'Invalid ZIP')
        return {n:z.read(n) for n in z.namelist()}

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False);CAND.mkdir(exist_ok=False)
    base=ROOT/'baseline/server.jar';need(sha(base)==BASE,'Wrong R396 baseline')
    paired={'NeverOverworld.zip':PACK,'NeverNether.zip':NETHER}
    for n,h in paired.items():need(sha(ROOT/'baseline/world/datapacks'/n)==h,'Wrong paired '+n)
    patch=load('r399_patch',ROOT/'scripts/apply-never-overworld-dry-mine-r399.py')
    run(['python3',str(ROOT/'scripts/apply-never-overworld-dry-mine-r399.py'),'--self-test'],'transform-tests.log')
    original=patch.SOURCE.read_bytes();source=WORK/'src'/patch.REL
    source.parent.mkdir(parents=True);source.write_bytes(patch.transform(original))
    (OUT/'NeverOverworldDryMinesR12.java').write_bytes(source.read_bytes())
    (OUT/'NeverOverworldDryMinesR12.before.java').write_bytes(original)
    base_raw=base.read_bytes();outer=members(base_raw)
    nested=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested)==1,'Wrong nested kernel');nested=nested[0];inner=members(outer[nested])
    need(MINE+'.class' in inner and POLICY in inner,'Required R396 classes missing')
    libs=WORK/'libs';libs.mkdir()
    for i,(n,raw) in enumerate(outer.items()):
        if n.endswith('.jar') and n.startswith(('META-INF/libraries/','META-INF/versions/')):
            (libs/(str(i)+'-'+Path(n).name)).write_bytes(raw)
    api=[]
    for p in libs.glob('*.jar'):
        with zipfile.ZipFile(p) as z:
            if 'org/bukkit/Bukkit.class' in z.namelist():api.append(p)
    with zipfile.ZipFile(ROOT/'debug/diagnostics.zip') as z:
        sources=[n for n in z.namelist() if n.endswith('/NeverOverworldDryMinesR12.java') and '/src/minecraft/java/' in n]
        need(len(sources)==1,'Expected exact materialized R38 source')
        need(z.read(sources[0])==original,'Materialized source differs from inspected source')
        if not api:
            options=[]
            for n in z.namelist():
                if 'folia-api' in n and n.endswith('.jar'):
                    raw=z.read(n)
                    with zipfile.ZipFile(io.BytesIO(raw)) as a:
                        if 'org/bukkit/Bukkit.class' in a.namelist():options.append(raw)
            need(len(options)==1,'No unique actual API')
            p=libs/'folia-api.jar';p.write_bytes(options[0]);api.append(p)
    need(len(api)==1,'Ambiguous API')
    cp=os.pathsep.join(map(str,sorted(libs.glob('*.jar'))));classes=WORK/'classes';classes.mkdir()
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),str(source)],'mine-javac.log')
    replacements={p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class')}
    allowed={MINE+'.class',MINE+'$Mask.class'}
    need(set(replacements)==allowed,'Unexpected compiled class set')
    need(all(int.from_bytes(raw[6:8],'big')==69 for raw in replacements.values()),'Wrong class version')
    plugin_classes=WORK/'plugin-classes';plugin_classes.mkdir()
    run(['javac','--release','25','-proc:none','-cp',str(classes)+os.pathsep+cp,'-d',str(plugin_classes),str(ROOT/'qa/field-r399/R399MineQa.java')],'plugin-javac.log')
    with zipfile.ZipFile(WORK/'R399MineQa.jar','w',zipfile.ZIP_DEFLATED) as z:
        for p in plugin_classes.rglob('*.class'):z.write(p,p.relative_to(plugin_classes).as_posix())
        z.writestr('plugin.yml',"name: R399MineQa\nversion: '1'\nmain: R399MineQa\napi-version: '26.2'\nfolia-supported: true\n")
    packaging=ROOT/'qa/field-r395/jar_packaging.py';run(['python3',str(packaging)],'packaging-tests.log')
    zp=load('r399_zip',packaging);new_inner=zp.rewrite_zip(outer[nested],replacements)
    rows=[];changed_rows=0
    for line in outer['META-INF/versions.list'].decode().splitlines():
        fields=line.split('\t');need(len(fields)==3,'Unexpected versions row')
        if 'META-INF/versions/'+fields[2]==nested:
            need(fields[0]==hashlib.sha256(outer[nested]).hexdigest(),'Invalid input kernel digest')
            fields[0]=hashlib.sha256(new_inner).hexdigest();changed_rows+=1
        rows.append('\t'.join(fields))
    need(changed_rows==1,'No unique kernel checksum row')
    new_outer=zp.rewrite_zip(base_raw,{nested:new_inner,'META-INF/versions.list':('\n'.join(rows)+'\n').encode()})
    ni=members(new_inner);no=members(new_outer)
    need(set(inner)==set(ni) and set(outer)==set(no),'Unexpected JAR membership change')
    changed={n for n in inner if inner[n]!=ni[n]}
    need(MINE+'.class' in changed and changed<=allowed,'Unrelated changed class')
    need(inner[POLICY]==ni[POLICY],'R396 water hotfix was altered')
    need({n for n in outer if outer[n]!=no[n]}=={nested,'META-INF/versions.list'},'Outer JAR drift')
    (CAND/'server.jar').write_bytes(new_outer)
    for n in paired:shutil.copyfile(ROOT/'baseline/world/datapacks'/n,CAND/n)
    report={'build_pass':True,'kind':'Incremental javac --release 25 on exact R396; not full Gradle',
        'base_core_sha256':BASE,'candidate_core_sha256':sha(CAND/'server.jar'),
        'pack_sha256':PACK,'nether_sha256':NETHER,'changed_bundled_entries':sorted(changed),
        'preserved_bundled_entries':len(inner)-len(changed),'preserved_r396_policy_sha256':hashlib.sha256(inner[POLICY]).hexdigest(),
        'source_sha256':sha(source),'production_accepted':False,'ocean_closure_installed':False}
    (OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
