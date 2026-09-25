#!/usr/bin/env python3
"""Run a packaged diagnostic JAR and finite active-physics QA in a NEW local world.

This is not the frozen order-comparison protocol, old-world migration, or release
acceptance. Requires explicit Minecraft EULA consent. Only its child is supervised.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('physics_supervisor',ROOT/'qa/nevernether-r8/probe_supervisor.py')
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('java','jar','pack','qa-plugin','new-directory'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--accept-eula',action='store_true');a=p.parse_args()
    if not a.accept_eula:p.error('Explicit EULA acknowledgement required')
    env=S.checked_environment()
    for path in (a.java,a.jar,a.pack,a.qa_plugin):
        if not path.is_file():p.error('Missing input: '+str(path))
    if a.new_directory.exists():p.error('Requires a new disposable directory')
    with zipfile.ZipFile(a.jar) as archive:
        if archive.testzip() is not None:raise ValueError('Corrupt server JAR')
        if 'io.papermc.paperclip.Main' not in archive.read('META-INF/MANIFEST.MF').decode():raise ValueError('Not the expected Paperclip entry point')
    with zipfile.ZipFile(a.pack) as archive:
        if archive.testzip() is not None:raise ValueError('Corrupt data pack')
        profile=json.loads(archive.read('data/neverfolia/nevernether/height_profile.json'))
        if profile.get('profile')!='NN-R14-SUBSTRATE-1-ROOF512':raise ValueError('Wrong height profile')
    identities={k:sha(path) for k,path in [('java_sha256',a.java),('jar_sha256',a.jar),('pack_sha256',a.pack),('qa_plugin_sha256',a.qa_plugin)]}
    world=a.new_directory.resolve();world.mkdir(parents=True,exist_ok=False)
    (world/'world/datapacks').mkdir(parents=True);(world/'plugins').mkdir()
    shutil.copyfile(a.pack,world/'world/datapacks/NeverNether.zip');shutil.copyfile(a.qa_plugin,world/'plugins/roof-physics-qa.jar')
    (world/'.nevernether-r8-isolated').write_text('NEW disposable packaged-JAR physics QA\n')
    (world/'eula.txt').write_text('eula=true\n')
    (world/'server.properties').write_text('level-name=world\nlevel-seed=7270913\ninitial-enabled-packs=vanilla,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25597\nonline-mode=false\nenforce-secure-profile=false\nview-distance=2\nsimulation-distance=2\nenable-status=false\nmax-tick-time=-1\npause-when-empty-seconds=-1\n')
    result=S.execute([str(a.java.resolve()),'-Xms512M','-Xmx2304M','-XX:ActiveProcessorCount=4','-Dpaper.disablePluginRemapping=true','-Dneverfolia.qa.stageProbe=true','-jar',str(a.jar.resolve()),'--nogui'],world,300,env=env)
    report_path=world/'plugins/NN-STAGE-R8-QA/report.json'
    report=json.loads(report_path.read_text()) if report_path.is_file() else {}
    unchanged=all(sha(path)==identities[k] for k,path in [('java_sha256',a.java),('jar_sha256',a.jar),('pack_sha256',a.pack),('qa_plugin_sha256',a.qa_plugin)])
    rows=report.get('observations',[])
    passed=(result['stage']=='completed' and result['process_exit_code']==0 and not result['forced_stop'] and unchanged
            and report.get('probe')=='NN-ROOF-PHYSICS-R14' and report.get('simulation_frozen') is False
            and report.get('above_roof_placement_attempts',0)>=2 and len(rows)==272
            and all(r.get('passed') is True for r in rows))
    evidence={'schema':1,'protocol':'NN-ROOF-PHYSICS-R14','passed':passed,'identities':identities,'inputs_unchanged':unchanged,
        'process':result,'physics_report':report,'release_ready':False,
        'scope':'Packaged JAR; 100 active ticks in one forced test chunk, two falling blocks, powered piston and scheduled lava. Not general fluid determinism, actual client packets or all dungeon acceptance.'}
    S.write_json(world/'physics-execution.json',evidence)
    print(json.dumps({k:v for k,v in evidence.items() if k not in ('process','physics_report')},indent=2))
    return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
