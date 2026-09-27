#!/usr/bin/env python3
"""Bounded native-mob and persisted-water checks on exact unchanged R39.3.
R39.4 is the QA revision, not a relabelled gameplay pack. Isolated CI worlds only.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[2]
EXPECTED={'server.jar':'411f628603ae531216c173fde1dbd8c702effb170889f72e5f2c0f1af81b6a32','NeverOverworld.zip':'a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be','NeverNether.zip':'5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'}

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def extract(z,basename,destination):
    names=[n for n in z.namelist() if n.rsplit('/',1)[-1]==basename]
    if not names:raise ValueError('Missing diagnostic member '+basename)
    blobs={hashlib.sha256(z.read(n)).hexdigest() for n in names}
    if len(blobs)!=1:raise ValueError('Conflicting diagnostic members '+repr(names))
    destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(z.read(names[0]))
    return {'source':names,'sha256':sha(destination)}

def dependencies(candidate,debug,output):
    plugins=ROOT/'.work/r394-water-plugins';plugins.mkdir(parents=True,exist_ok=True)
    libs=ROOT/'.work/r394-runtime-libs';libs.mkdir(parents=True,exist_ok=True);sources=[]
    with zipfile.ZipFile(debug/'diagnostics.zip') as z:
        report={name:extract(z,name,dest) for name,dest in (
            ('R37DungeonQa.jar',plugins/'R37DungeonQa.jar'),
            ('GameProtocols.java',ROOT/'.work/Folia/folia-server/src/minecraft/java/net/minecraft/network/protocol/game/GameProtocols.java'))}
        for n in z.namelist():
            if n.endswith('.jar') and any(v in n.rsplit('/',1)[-1] for v in ('folia-api','paper-api')):
                dest=libs/('debug-'+str(len(sources))+'.jar');dest.write_bytes(z.read(n));sources.append({'source':n,'sha256':sha(dest)})
    with zipfile.ZipFile(candidate/'server.jar') as z:
        for i,n in enumerate(z.namelist()):
            if n.endswith('.jar') and n.startswith(('META-INF/libraries/','META-INF/versions/')):
                dest=libs/('bundled-'+str(i)+'.jar');dest.write_bytes(z.read(n));sources.append({'source':n,'sha256':sha(dest)})
    classes=ROOT/'.work/r394-trial-classes';classes.mkdir(parents=True,exist_ok=True)
    source=ROOT/'qa/field-r38/R38TrialQaPlugin.java';text=source.read_bytes()
    blob=hashlib.sha1(f'blob {len(text)}\0'.encode()+text).hexdigest()
    if blob!='8725a4268e9425e48118cb0307d9a67f444b31fd':raise ValueError('Original trial fixture source changed')
    run=subprocess.run(['javac','--release','25','-cp',os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar'))),'-d',str(classes),str(source)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (output/'trial-javac.log').write_text(run.stdout);print(run.stdout,flush=True)
    (output/'compile-classpath.json').write_text(json.dumps(sources,indent=2)+'\n')
    if run.returncode:raise ValueError('Original trial fixture compilation failed')
    with zipfile.ZipFile(plugins/'R38TrialQa.jar','w',zipfile.ZIP_DEFLATED) as z:
        for p in classes.rglob('*.class'):z.write(p,str(p.relative_to(classes)))
        z.write(ROOT/'qa/field-r38/plugin.yml','plugin.yml')
    report['R38TrialQa.jar']={'compiled_against_actual_core':True,'source_blob':blob,'sha256':sha(plugins/'R38TrialQa.jar')}
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','debug','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.candidate=a.candidate.resolve();a.debug=a.debug.resolve();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
    report={'qa_revision':'R39.4','gameplay_pack':'R39.3 unchanged','pass':False,'production_accepted':False,'expected_inputs':EXPECTED,'commit':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID')}
    try:
        actual={name:sha(a.candidate/name) for name in EXPECTED};report['actual_inputs']=actual
        if actual!=EXPECTED:raise ValueError('Not the exact accepted input set')
        report['harness_members']=dependencies(a.candidate,a.debug,a.output);plugins=ROOT/'.work/r394-water-plugins'
        m=load('r394_water_harness',ROOT/'qa/field-r38/run-live.py');original_chunks=set(m.CHUNKS);m.TARGETS=tuple(m.TARGETS)+((-202,-213),(-204,-213))
        m.CHUNKS=sorted({(cx+dx,cz+dz) for cx,cz in m.TARGETS for dx in (-1,0,1) for dz in (-1,0,1)})
        if len(original_chunks)!=48 or len(m.CHUNKS)!=63:raise ValueError('Unexpected coverage')
        report['target_chunks']=m.CHUNKS;report['new_remote_chunks']=sorted(set(m.CHUNKS)-original_chunks)
        original_save=m.save
        def scoped_save(path,data):
            if path.name=='r38-live-qa.json':
                data['scope']='Exact unchanged R39.3 pack: 63 saved target chunks, original 48 plus 15 near remote screenshots, native mob fixtures, LIGHT audit, restart and reverse generation. Not all seeds or visual acceptance.'
                data['qa_revision']='R39.4';data['gameplay_pack']='R39.3';data['target_chunks']=m.CHUNKS;data['production_accepted']=False
            original_save(path,data)
        m.save=scoped_save
        sys.argv=['run-live.py','--jar',str(a.candidate/'server.jar'),'--overworld',str(a.candidate/'NeverOverworld.zip'),'--nether',str(a.candidate/'NeverNether.zip'),'--controller-plugin',str(plugins/'R37DungeonQa.jar'),'--trial-plugin',str(plugins/'R38TrialQa.jar'),'--output',str(a.output/'live'),'--work',str(ROOT/'.work/r394-water-worlds'),'--source-sha',os.environ.get('GITHUB_SHA','unknown')]
        m.main();report['pass']=True
    except (Exception,SystemExit) as error:report['error']=repr(error)
    finally:
        report['inputs_unchanged']=all((a.candidate/n).is_file() and sha(a.candidate/n)==v for n,v in EXPECTED.items());report['pass']=report['pass'] and report['inputs_unchanged'];(a.output/'r394-water-regression.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return 0 if report['pass'] else 1
if __name__=='__main__':raise SystemExit(main())
