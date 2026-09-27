#!/usr/bin/env python3
"""Run bounded native-mob and persisted-water checks on exact R39.3, unchanged.
R39.4 here is a QA revision, not a renamed gameplay pack. Uses isolated CI worlds.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,shutil,sys,zipfile
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

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','debug','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.candidate=a.candidate.resolve();a.debug=a.debug.resolve();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
    report={'qa_revision':'R39.4','gameplay_pack':'R39.3 unchanged','pass':False,'production_accepted':False,'expected_inputs':EXPECTED,'commit':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID')}
    try:
        actual={name:sha(a.candidate/name) for name in EXPECTED};report['actual_inputs']=actual
        if actual!=EXPECTED:raise ValueError('Not the exact accepted input set')
        plugins=ROOT/'.work/r394-water-plugins'
        with zipfile.ZipFile(a.debug/'diagnostics.zip') as z:
            report['harness_members']={name:extract(z,name,dest) for name,dest in (
                ('R37DungeonQa.jar',plugins/'R37DungeonQa.jar'),
                ('R38TrialQa.jar',plugins/'R38TrialQa.jar'),
                ('GameProtocols.java',ROOT/'.work/Folia/folia-server/src/minecraft/java/net/minecraft/network/protocol/game/GameProtocols.java'))}
        m=load('r394_water_harness',ROOT/'qa/field-r38/run-live.py')
        original_chunks=set(m.CHUNKS);m.TARGETS=tuple(m.TARGETS)+((-202,-213),(-204,-213))
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
    except (Exception,SystemExit) as error:
        report['error']=repr(error)
    finally:
        report['inputs_unchanged']=all((a.candidate/n).is_file() and sha(a.candidate/n)==v for n,v in EXPECTED.items())
        report['pass']=report['pass'] and report['inputs_unchanged']
        (a.output/'r394-water-regression.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return 0 if report['pass'] else 1
if __name__=='__main__':raise SystemExit(main())
