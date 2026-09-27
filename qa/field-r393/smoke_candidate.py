#!/usr/bin/env python3
"""Bounded real-server registry/start/restart test for the full R39.3 pack.
Uses the existing repository's isolated CI EULA convention, never a user's world.
No player, template placement, combat or water-geometry acceptance is claimed.
"""
from pathlib import Path
import argparse,copy,gzip,hashlib,importlib.util,io,json,queue,shutil,subprocess,threading,time,unittest
EXPECTED={'server.jar':'411f628603ae531216c173fde1dbd8c702effb170889f72e5f2c0f1af81b6a32','NeverOverworld.zip':'a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be','NeverNether.zip':'5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'}
SEED=-4651369264513492755

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

REQUIRED_PACKS=('vanilla','file/NeverOverworld.zip','file/NeverNether.zip')
CONTENT_HASH='24d1e22d76bc77aa990a1c0e0910e8bbc2ca186be52f4db2a3382ea5b694d7e0'

def validate_enabled(root):
    def tag(parent,key,kind):
        value=parent.get(key)
        if not isinstance(value,tuple) or len(value)!=2 or value[0]!=kind:
            raise ValueError('Missing/wrong NBT tag: '+key)
        return value[1]
    data=tag(root,'Data',10);packs=tag(data,'DataPacks',10)
    result={}
    for key in ('Enabled','Disabled'):
        child,values=tag(packs,key,9)
        if (child!=8 and not (child==0 and not values)) or not isinstance(values,list) or any(not isinstance(v,str) for v in values):
            raise ValueError('Not a string list: '+key)
        if len(values)!=len(set(values)):raise ValueError('Duplicate pack: '+key)
        result[key.lower()]=values
    enabled=result['enabled'];disabled=result['disabled']
    if not set(REQUIRED_PACKS).issubset(enabled):raise ValueError('Required pack not saved as enabled')
    if set(enabled)-set(REQUIRED_PACKS)-{'paper'}:raise ValueError('Unexpected enabled overlay')
    if set(enabled)&set(disabled):raise ValueError('Enabled pack is also disabled')
    if [v for v in enabled if v in REQUIRED_PACKS]!=list(REQUIRED_PACKS):raise ValueError('Unexpected pack priority')
    result['pass']=True
    return result

def saved_enabled(folder,out,name):
    path=folder/'world/level.dat'
    raw=path.read_bytes()
    if len(raw)>16*1024*1024:raise ValueError('Oversized level.dat')
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as f:decoded=f.read(16*1024*1024+1)
    if len(decoded)>16*1024*1024:raise ValueError('Oversized decoded level.dat')
    source=Path(__file__).resolve().parents[2]/'scripts/build-never-overworld-external-structures-r19.py'
    spec=importlib.util.spec_from_file_location('r393_level_nbt',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    try:_,_,root=module._nbt_parse(decoded)
    except SystemExit as error:raise ValueError('Cannot parse saved level.dat: '+str(error)) from error
    result=validate_enabled(root)
    evidence=out/(name+'-level.dat');evidence.write_bytes(raw)
    result['level_dat_sha256']=sha(evidence)
    result['evidence_file']=evidence.name
    return result

class PackProofTests(unittest.TestCase):
    def fixture(self,enabled=None,disabled=None):
        return {'Data':(10,{'DataPacks':(10,{'Enabled':(9,(8,list(REQUIRED_PACKS) if enabled is None else enabled)), 'Disabled':(9,(8,[] if disabled is None else disabled))})})}
    def test_valid(self):self.assertTrue(validate_enabled(self.fixture())['pass'])
    def test_paper_allowed(self):self.assertTrue(validate_enabled(self.fixture(['vanilla','paper',*REQUIRED_PACKS[1:]]))['pass'])
    def test_missing_pack(self):
        with self.assertRaises(ValueError):validate_enabled(self.fixture(['vanilla']))
    def test_unexpected_overlay(self):
        with self.assertRaises(ValueError):validate_enabled(self.fixture([*REQUIRED_PACKS,'file/extra.zip']))
    def test_duplicate(self):
        with self.assertRaises(ValueError):validate_enabled(self.fixture([*REQUIRED_PACKS,'vanilla']))
    def test_wrong_priority(self):
        with self.assertRaises(ValueError):validate_enabled(self.fixture(list(reversed(REQUIRED_PACKS))))
    def test_disabled_required(self):
        with self.assertRaises(ValueError):validate_enabled(self.fixture(disabled=['file/NeverOverworld.zip']))
    def test_missing_data(self):
        with self.assertRaises(ValueError):validate_enabled({})
    def test_bad_list_type(self):
        root=self.fixture();root['Data'][1]['DataPacks'][1]['Enabled']=(9,(3,[1]))
        with self.assertRaises(ValueError):validate_enabled(root)
    def test_empty_end_typed_disabled(self):
        root=self.fixture();root['Data'][1]['DataPacks'][1]['Disabled']=(9,(0,[]))
        self.assertTrue(validate_enabled(root)['pass'])


def phase(candidate,folder,out,name):
    report={'pass':False};proc=None;reader=None;lines=[];events=queue.Queue()
    try:
        proc=subprocess.Popen(['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx3G','-jar',str(candidate/'server.jar'),'--nogui'],cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (out/(name+'.log')).open('w') as log:
                for line in proc.stdout:lines.append(line);log.write(line);log.flush();events.put(line)
            events.put(None)
        reader=threading.Thread(target=pump,daemon=True);reader.start()
        def wait(predicate,seconds):
            until=time.monotonic()+seconds
            while time.monotonic()<until:
                try:line=events.get(timeout=1)
                except queue.Empty:
                    if proc.poll() is not None:raise RuntimeError('Server exited before expected event')
                    continue
                if line is None:raise RuntimeError('Log ended before expected event')
                if predicate(line):return line.rstrip()
            raise TimeoutError('Expected server event not received')
        report['startup_line']=wait(lambda s:'Done (' in s,300)
        proc.stdin.write('stop\n');proc.stdin.flush();report['exit_code']=proc.wait(timeout=90);reader.join(timeout=5)
        if reader.is_alive():raise RuntimeError('Log reader did not finish')
        if report['exit_code']!=0:raise RuntimeError('Unclean server exit')
        report['saved_pack_proof']=saved_enabled(folder,out,name)
        report['fingerprint_log_lines']=[s.rstrip() for s in lines if '[NeverFolia][NeverOverworld]' in s and 'fingerprint' in s]
        if name=='r393-start' and not any(CONTENT_HASH in s for s in report['fingerprint_log_lines']):raise ValueError('New world fingerprint was not observed')
        patterns=('Failed to load registries','Failed to load datapacks','Unknown registry key','Block-attached entity at invalid position','Empty or non-existent pool','[ChunkTaskScheduler] Chunk system error','Failed to load function','Failed to parse','Couldn\'t load tag','Error loading registry data')
        report['targeted_errors']=[s.rstrip() for s in lines if any(p in s for p in patterns)]
        report['warnings_and_errors']=[s.rstrip() for s in lines if ' WARN]' in s or ' ERROR]' in s]
        report['pass']=report['exit_code']==0 and not report['targeted_errors']
    except Exception as error:report['error']=repr(error)
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=30)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if reader is not None:reader.join(timeout=5)
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','work','output'):p.add_argument('--'+name,type=Path)
    p.add_argument('--self-test',action='store_true')
    a=p.parse_args()
    if a.self_test:return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PackProofTests)).wasSuccessful() else 1
    if any(getattr(a,key) is None for key in ('candidate','work','output')):p.error('--candidate --work --output are required')
    a.candidate=a.candidate.resolve();a.work=a.work.resolve();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
    report={'pass':False,'scope':'Registry loading, enabled full packs, graceful start/stop and second startup only. No template placement, water geometry or mob behavior proof.','seed':str(SEED),'bind':'127.0.0.1:25599','inputs':EXPECTED,'production_accepted':False}
    try:
        tests=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PackProofTests))
        if not tests.wasSuccessful():raise ValueError('Saved pack proof regression failed')
        report['pack_proof_tests']=tests.testsRun
        java=subprocess.run(['java','-version'],capture_output=True,text=True,check=True)
        report['java_version']=java.stderr+java.stdout
        if 'version "25' not in report['java_version']:raise ValueError('Java 25 required')
        for name,value in EXPECTED.items():
            if sha(a.candidate/name)!=value:raise ValueError('Unexpected candidate bytes: '+name)
        a.work.mkdir(parents=True,exist_ok=False);packs=a.work/'world/datapacks';packs.mkdir(parents=True)
        for name in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(a.candidate/name,packs/name)
        (a.work/'eula.txt').write_text('eula=true\n')
        (a.work/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25599\nonline-mode=true\nenforce-secure-profile=true\nview-distance=2\nsimulation-distance=2\nmax-players=1\nenable-query=false\nenable-rcon=false\nenable-status=false\npause-when-empty-seconds=-1\n')
        report['first']=phase(a.candidate,a.work,a.output,'r393-start')
        if report['first']['pass']:report['restart']=phase(a.candidate,a.work,a.output,'r393-restart')
        report['copied_packs_unchanged']=all(sha(packs/name)==EXPECTED[name] for name in ('NeverOverworld.zip','NeverNether.zip'))
        report['pass']=report['first']['pass'] and report.get('restart',{}).get('pass',False) and report['copied_packs_unchanged']
    except Exception as error:report['error']=repr(error)
    finally:(a.output/'r393-startup.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return 0 if report['pass'] else 1
if __name__=='__main__':raise SystemExit(main())
