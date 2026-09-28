#!/usr/bin/env python3
"""Add opt-in ice policy to the pinned GitHub R3911, never replace local R3911 silently."""
from pathlib import Path
import hashlib,importlib.util,io,json,os,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3913';CAND=ROOT/'candidate'
LIGHT='ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask'
HELPER='net/minecraft/world/level/chunk/NeverOverworldIceFragmentsR3913.class'
def need(ok,s):
    if not ok:raise ValueError(s)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(b):return hashlib.sha256(b).hexdigest()
def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(len(set(z.namelist()))==len(z.namelist()) and z.testzip() is None,'Invalid ZIP')
        return {n:z.read(n) for n in z.namelist()}
def run(cmd,label):
    p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    (OUT/label).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,label+' failed')
def main():
    WORK.mkdir(parents=True,exist_ok=False);control=ROOT/'control';control.mkdir(exist_ok=False)
    inherited=json.loads((OUT/'build.json').read_text());need(inherited['build_pass'],'Missing successful wide-ocean base')
    source_jar=CAND/'server.jar';need(sha(source_jar)==inherited['candidate_core_sha256'],'Changed wide-ocean base')
    shutil.copyfile(source_jar,control/'server.jar');shutil.copyfile(OUT/'build.json',OUT/'r3911-github-base-build.json')
    raw=source_jar.read_bytes();outer=members(raw);names=[n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(names)==1,'Wrong bundled core');nested=names[0];inner=members(outer[nested]);need(HELPER not in inner,'Ice patch already installed')
    source=OUT/'compiled-source'/(LIGHT+'.java');text=source.read_text()
    anchor='                net.minecraft.world.level.chunk.NeverOverworldOceanClosureR399.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R3911_MANUAL_WIDE_OCEAN'
    need(text.count(anchor)==1,'Unknown actual LIGHT hook')
    text=text.replace(anchor,anchor+'\n                net.minecraft.world.level.chunk.NeverOverworldIceFragmentsR3913.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R3913_ICE_FRAGMENTS',1)
    src=WORK/'src';light=src/(LIGHT+'.java');light.parent.mkdir(parents=True);light.write_text(text)
    helper=src/'NeverOverworldIceFragmentsR3913.java';shutil.copyfile(ROOT/'native/overworld-r3913/NeverOverworldIceFragmentsR3913.java',helper)
    cp=str(ROOT/'.work/manual-r3911/classes')+os.pathsep+(ROOT/'.work/manual-r3911/classpath.txt').read_text()
    classes=WORK/'classes';classes.mkdir();repeat=WORK/'repeat-classes';repeat.mkdir()
    for folder,label in ((classes,'ice-core-javac.log'),(repeat,'ice-repeat-javac.log')):
        run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(folder),str(light),str(helper)],label)
    changes={p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class')}
    repeated={p.relative_to(repeat).as_posix():p.read_bytes() for p in repeat.rglob('*.class')}
    need(changes==repeated,'Non-repeatable compilation')
    oldfamily={n for n in inner if n==LIGHT+'.class' or n.startswith(LIGHT+'$')}
    need(set(changes)==oldfamily|{HELPER},'Unexpected compiled class set')
    need(all(int.from_bytes(b[6:8],'big')==69 for b in changes.values()),'Wrong Java target')
    path=ROOT/'qa/field-r395/jar_packaging.py';spec=importlib.util.spec_from_file_location('r3913zip',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    patched=mod.rewrite_zip(outer[nested],changes);versions=[];count=0
    for line in outer['META-INF/versions.list'].decode().splitlines():
        fields=line.split('\t');need(len(fields)==3,'Invalid version manifest')
        if 'META-INF/versions/'+fields[2]==nested:
            need(fields[0]==digest(outer[nested]),'Wrong prior bundled hash');fields[0]=digest(patched);count+=1
        versions.append('\t'.join(fields))
    need(count==1,'Missing unique bundled manifest')
    result=mod.rewrite_zip(raw,{nested:patched,'META-INF/versions.list':('\n'.join(versions)+'\n').encode()})
    after=members(patched);need(set(after)==set(inner)|{HELPER},'Unexpected entry membership')
    need(all(inner[n]==after[n] for n in inner if n not in changes),'Unrelated class changed')
    guards=dict(inherited['preserved_hotfix_classes'])
    need(all(digest(after[n])==s for n,s in guards.items()),'Lost a snow/dry-mine fix')
    source_jar.write_bytes(result)
    qa=WORK/'R3913IceQa.java';q=(ROOT/'qa/field-r3913/R3913IceQa.java').read_text()
    marker='if(NeverOverworldIceFragmentsR3913.ice(states[i]))ice++;'
    need(q.count(marker)==1,'Unexpected natural observer')
    q=q.replace(marker,'if(states[i].is(Blocks.ICE)||states[i].is(Blocks.PACKED_ICE)||states[i].is(Blocks.BLUE_ICE))ice++;')
    qa.write_text(q);qa_classes=WORK/'qa-classes';qa_classes.mkdir()
    run(['javac','--release','25','-proc:none','-cp',str(classes)+os.pathsep+cp,'-d',str(qa_classes),str(qa)],'ice-qa-javac.log')
    with zipfile.ZipFile(WORK/'R3913IceQa.jar','w',zipfile.ZIP_DEFLATED) as z:
        for p in qa_classes.rglob('*.class'):z.write(p,p.relative_to(qa_classes).as_posix())
        z.writestr('plugin.yml',"name: R3913IceQa\nversion: '2'\nmain: R3913IceQa\napi-version: '26.2'\nfolia-supported: true\n")
    report={'build_pass':True,'version':'R39.13-ICE-TEST-v2','kind':'Incremental javac 25, GitHub R3911 plus piece-scoped bounded ice cleanup; NOT full Gradle',
        'parent_github_r3911_sha256':digest(raw),'candidate_core_sha256':digest(result),'local_r3911_not_used':True,
        'known_local_r3911_sha256':'c326e2818343c4798792784ad3877422d9e89213c282dd073dc7089b576f2daf',
        'pack_sha256':inherited['pack_sha256'],'nether_sha256':inherited['nether_sha256'],'preserved_hotfix_classes':guards,
        'unchanged_parent_entries':sum(1 for n in inner if n not in changes),'changed_or_added_classes':{n:digest(b) for n,b in changes.items()},
        'repeat_compilation_identical':True,'native_ice_default_enabled':False,'production_accepted':False,'visual_tested':False}
    (OUT/'r3913-build.json').write_text(json.dumps(report,indent=2)+'\n');(OUT/'R3913IceQa-compiled.java').write_text(q)
    shutil.copytree(src,OUT/'r3913-compiled-source');print('R3913_BUILD '+json.dumps(report),flush=True)
if __name__=='__main__':main()
