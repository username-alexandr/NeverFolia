#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,queue,secrets,shutil,subprocess,threading,time,zipfile
import mansion_reference as fix
s=fix.s;ROOT=fix.ROOT;OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3918-mansion'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'

def one(folder,name):
    items=[p for p in Path(folder).rglob(name) if p.is_file() and not p.is_symlink()]
    s.need(len(items)==1,'Missing/ambiguous '+name);return items[0]
def exact(folder,name,digest):
    p=one(folder,name);s.need(s.sha(p.read_bytes())==digest,'Wrong pinned input '+name);return p
def save(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def compile_qa(core):
    libs=WORK/'libs';classes=WORK/'qa-classes';libs.mkdir(parents=True,exist_ok=False);classes.mkdir()
    with zipfile.ZipFile(core) as z:
        for i,n in enumerate(z.namelist()):
            if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(z.read(n))
    cp=os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')))
    source=Path(__file__).with_name('R3918ResourceQa.java')
    p=subprocess.run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes),str(source)],capture_output=True,text=True,timeout=120)
    (OUT/'resource-qa-javac.log').write_text(p.stdout+p.stderr);s.need(p.returncode==0,'QA compilation: '+p.stderr)
    target=WORK/'R3918ResourceQa.jar'
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
        for f in classes.rglob('*.class'):z.write(f,f.relative_to(classes).as_posix())
        z.writestr('plugin.yml',"name: R3918ResourceQa\nversion: '1'\nmain: R3918ResourceQa\napi-version: '26.2'\nfolia-supported: true\n")
    return target

def phase(name,core,folder):
    nonce=secrets.token_hex(16);result=folder/'plugins/R3918ResourceQa/result.json';report={'pass':False,'nonce':nonce};proc=None;reader=None;lines=[];events=queue.Queue()
    try:
        if result.exists():
            s.need(result.is_file() and not result.is_symlink(),'Invalid previous report')
            shutil.copyfile(result,OUT/(name+'-previous.json'));result.unlink()
        args=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G','-Dneverfolia.r399OceanClosure=true','-Dneverfolia.r3913IceFragments=true','-Dneverfolia.qaNonce='+nonce,'-jar',str(core),'--nogui']
        proc=subprocess.Popen(args,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (OUT/(name+'-server.log')).open('w',encoding='utf-8') as log:
                for line in proc.stdout:lines.append(line);log.write(line);log.flush();events.put(line)
            events.put(None)
        reader=threading.Thread(target=pump,daemon=True);reader.start();deadline=time.monotonic()+300;done=False;passed=False
        while time.monotonic()<deadline:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if 'Done (' in line:done=True
            if 'R3918 RESOURCE QA FAIL' in line:raise ValueError('Current fixture failed')
            if 'R3918 RESOURCE QA PASS nonce='+nonce in line:passed=True
            if done and passed:break
        s.need(done and passed,'No completed current server check')
        observed=json.loads(result.read_text());report['observed']=observed
        s.need(observed.get('pass') is True and observed.get('nonce')==nonce and observed.get('seed')==-4651369264513492755,'Not a fresh valid result')
        expected={'fresh_nonce','actual_seed','owned_region','malformed_identifier_interpretation','old_unresolved_template','canonical_template_dimensions','canonical_template_air_block','loaded_pool:minecraft:illager_mansion/illager_mansion_room','loaded_pool:minecraft:illager_mansion/illager_mansion_room_basement'}
        checks=observed.get('checks',[]);s.need(len(checks)==len(expected) and {x['name'] for x in checks}==expected and all(x.get('pass') is True for x in checks),'Missing/failed registry checks')
        proc.stdin.write('stop\n');proc.stdin.flush();report['exit_code']=proc.wait(timeout=120);reader.join(timeout=15)
        s.need(report['exit_code']==0 and not reader.is_alive(),'Unclean shutdown')
        bad=('Failed to load datapacks','Overworld settings missing','Unable to read or access the world gen settings','Empty or non-existent pool:','Block-attached entity at invalid position','porting_lib:','Exception loading structure')
        report['targeted_errors']=[x.strip() for x in lines if any(t in x for t in bad)]
        s.need(not report['targeted_errors'],'Targeted server errors');report['pass']=True
    except Exception as e:report['error']=repr(e)
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=40)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=15)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if reader:reader.join(timeout=15)
        save(name+'-phase.json',report);print('R3918_PHASE',name,json.dumps(report),flush=True)
    return report

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False);report={'pass':False,'all_reported_bugs_fixed':False,'production_accepted':False,'user_kit_published':False}
    try:
        pack=exact(ROOT/'integrated-input','NeverOverworld-R3915-Combined.zip',fix.BASE)
        core=exact(ROOT/'swift-input','server-r3915.jar',fix.CORE)
        nether=exact(ROOT/'inputs','NeverNether.zip',NETHER)
        raw,build=fix.build(pack.read_bytes());target=OUT/'NeverOverworld-R3918-References.zip'
        with target.open('xb') as f:f.write(raw)
        save('mansion-build.json',build);report['build']=build
        finalfiles=s.read_zip(raw);netherfiles=s.read_zip(nether.read_bytes())
        s.need(all(p not in netherfiles or netherfiles[p]==finalfiles[p] for p in fix.POOLS),'Nether shadows corrected resources')
        before=json.loads(one(ROOT/'integrated-input','combined-resource-after.json').read_text())
        s.need(before['inputs']['pack_sha256']==fix.BASE,'Wrong prior audit')
        audit=s.load('r3918_full_audit',ROOT/'scripts/audit-neveroverworld-r39-resources.py')
        after=audit.audit_files(core,target);save('resource-after.json',after)
        a={(x['kind'],x['id']) for x in before['missing']};b={(x['kind'],x['id']) for x in after['missing']}
        s.need(not after['errors'],'Resource decoding failed')
        s.need(a-b=={('template','minecraft:minecraft/empty')} and not b-a,'Unexpected resource delta')
        s.need({x['id'] for x in before['roots']}=={x['id'] for x in after['roots']},'Root coverage changed')
        report['resource_delta']={'before':before['counts'],'after':after['counts'],'removed':sorted(a-b),'introduced':sorted(b-a),'full_resource_acceptance':after['pass']}
        save('resource-delta.json',report['resource_delta']);print('R3918_RESOURCE_DELTA',json.dumps(report['resource_delta']),flush=True)
        # Source-only evidence for a separate future reconstruction; not applied.
        nbt=s.load('r3918_decor_reader',ROOT/'scripts/build-never-overworld-external-structures-r19.py');decor=[]
        prefix='data/nova_structures/structure/lone_citadel/room_content/'
        for path,payload in sorted(finalfiles.items()):
            if path.startswith(prefix) and path.endswith('.nbt') and any(term in Path(path).name for term in ('mirror','center','furnace')):
                root=nbt._nbt_parse(payload)[2];palette=root.get('palette',(9,(10,[])))[1][1];joints=[]
                for block in root.get('blocks',(9,(10,[])))[1][1]:
                    state=palette[block['state'][1]]
                    if state.get('Name')==(8,'minecraft:jigsaw'):joints.append({'pos':block.get('pos'),'state':state,'nbt':block.get('nbt')})
                decor.append({'path':path,'sha256':s.sha(payload),'size':root.get('size'),'joints':joints})
        save('citadel-source-inspection.json',decor)
        print('CITADEL_REVIEW',json.dumps(decor),flush=True)
        plugin=compile_qa(core)
        folder=WORK/'server';packs=folder/'world/datapacks';packs.mkdir(parents=True);(folder/'plugins').mkdir()
        shutil.copyfile(target,packs/'NeverOverworld.zip');shutil.copyfile(nether,packs/'NeverNether.zip');shutil.copyfile(plugin,folder/'plugins/R3918ResourceQa.jar')
        (folder/'eula.txt').write_text('eula=true\n')
        (folder/'server.properties').write_text('level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25618\nonline-mode=true\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\nenable-rcon=false\nenable-query=false\nenable-status=false\n')
        report['runtime']=phase('mansion-first',core,folder);s.need(report['runtime']['pass'],'Initial runtime failed')
        report['restart']=phase('mansion-restart',core,folder);s.need(report['restart']['pass'],'Restart failed')
        s.need(s.sha(core.read_bytes())==fix.CORE and s.sha(pack.read_bytes())==fix.BASE and s.sha(nether.read_bytes())==NETHER,'Original input changed')
        s.need(s.sha((packs/'NeverOverworld.zip').read_bytes())==build['output_sha256'],'Test copy changed')
        report.update({'pass':True,'core_sha256':fix.CORE,'nether_sha256':NETHER,'scope':'Two exact namespace-separator corrections; no new model or server compilation. Actual loading/resource resolution plus restart, not complete mansion jigsaw generation.'})
    except Exception as e:report['error']=repr(e)
    finally:
        save('mansion-result.json',report);print('R3918_MANSION_RESULT',json.dumps({k:v for k,v in report.items() if k not in ('runtime','restart','build')}),flush=True)
    s.need(report['pass'],'Mansion reference stage failed')
if __name__=='__main__':main()
