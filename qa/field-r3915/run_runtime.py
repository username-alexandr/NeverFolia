#!/usr/bin/env python3
"""Isolated offline loopback QA only. User/public server authentication is unchanged."""
from pathlib import Path
import hashlib,importlib.util,json,queue,re,secrets,shutil,subprocess,threading,time,zipfile
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'.work/r3915';OUT=ROOT/'artifacts'
CORE='9571073a77086b04ce54594fe2b91737fdf9daf4019d4ce585016f77c03912f6'
BASE='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10';SEED=-4651369264513492755
BAD=('Failed to load datapacks','Failed to load registries','Overworld settings missing','Failed to load function','Failed to parse','Unknown registry key','Chunk system error','Exception in server tick loop','The server has not responded for','NoSuchMethodError','NoClassDefFoundError')
def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,obj):(OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
def exact(name,expected):
    ps=list((ROOT/'inputs').rglob(name));need(len(ps)==1 and sha(ps[0])==expected,'Incorrect input '+name);return ps[0]
def wire_config():
    debug=list((ROOT/'debug').rglob('diagnostics.zip'));need(len(debug)==1,'Missing pinned protocol source')
    with zipfile.ZipFile(debug[0]) as z:
        names=[p for p in z.namelist() if p.endswith('/src/minecraft/java/net/minecraft/network/protocol/game/GameProtocols.java')]
        need(len(names)==1,'Ambiguous protocol source');raw=z.read(names[0]);text=raw.decode()
    split=text.index('CLIENTBOUND_TEMPLATE');sb={n:i for i,n in enumerate(re.findall(r'\.addPacket\([^,]+\.([A-Z_]+),',text[text.index('SERVERBOUND_TEMPLATE'):split]))};cb={n:i for i,n in enumerate(re.findall(r'\.addPacket\([^,]+\.([A-Z_]+),',text[split:]),1)}
    cfg={'play_keepalive':cb['CLIENTBOUND_KEEP_ALIVE'],'play_position':cb['CLIENTBOUND_PLAYER_POSITION'],'play_keepalive_reply':sb['SERVERBOUND_KEEP_ALIVE']}
    save('protocol-source.json',{'source':names[0],'sha256':hashlib.sha256(raw).hexdigest(),'mapping':cfg})
    spec=importlib.util.spec_from_file_location('r3915_loopback',ROOT/'qa/field-r38/loopback_client.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m.Client,cfg

def setup(name,pack,nether,plugin):
    folder=WORK/('world-'+name);packs=folder/'world/datapacks';packs.mkdir(parents=True,exist_ok=False);plugins=folder/'plugins';plugins.mkdir()
    shutil.copyfile(pack,packs/'NeverOverworld.zip');shutil.copyfile(nether,packs/'NeverNether.zip');shutil.copyfile(plugin,plugins/'R3915SwiftQa.jar')
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25615\nonline-mode=false\nenforce-secure-profile=false\nnetwork-compression-threshold=-1\ngamemode=survival\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\nenable-rcon=false\nenable-query=false\nenable-status=false\n')
    return folder

def phase(name,jar,folder,baseline,Client,cfg):
    nonce=secrets.token_hex(16);report={'pass':False,'nonce':nonce,'baseline':baseline};proc=None;reader=None;client=None;lines=[];events=queue.Queue();result=folder/'plugins/R3915SwiftQa/result.json'
    try:
        if result.exists():
            with (OUT/(name+'-previous-result.json')).open('xb') as f:f.write(result.read_bytes())
            result.unlink()
        # These match the actual pinned R3913 kit flags, not the local R3911 line.
        args=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G','-Dneverfolia.r399OceanClosure=true','-Dneverfolia.r3913IceFragments=true','-Dneverfolia.qaNonce='+nonce,'-Dneverfolia.qaBaseline='+str(baseline).lower(),'-jar',str(jar),'--nogui']
        proc=subprocess.Popen(args,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (OUT/(name+'-server.log')).open('w',encoding='utf-8') as log:
                for line in proc.stdout:lines.append(line);log.write(line);log.flush();events.put(line)
            events.put(None)
        reader=threading.Thread(target=pump,daemon=True);reader.start();deadline=time.monotonic()+360;done=False;passed=False;ready=False
        while time.monotonic()<deadline:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if 'Done (' in line:done=True
            if 'R3915 LOOPBACK READY nonce='+nonce in line:ready=True
            if done and ready and client is None:client=Client(25615,**cfg)
            if 'R3915 SWIFT FAIL' in line:raise ValueError('Fresh server fixture failed')
            if 'R3915 SWIFT PASS nonce='+nonce in line:passed=True
            if done and passed:break
        need(done and passed and client is not None,'Missing current connected-client PASS/Done')
        observed=json.loads(result.read_text());report['observed']=observed
        need(observed.get('pass') is True and observed.get('nonce')==nonce and observed.get('seed')==SEED and observed.get('baseline') is baseline,'Wrong fresh report')
        need(observed.get('network_player_tested') is True,'No real connected player')
        need(len(observed.get('checks',[]))>=20 and all(row['pass'] is True for row in observed['checks']),'Insufficient fixture results')
        if not baseline:need([row['tier'] for row in observed['levels']]==[1,2,3],'Missing tier coverage')
        need(client.stage=='play' and not any('error' in e for e in client.events),'Loopback failed')
        client.close();save(name+'-client.json',client.events);client=None
        proc.stdin.write('stop\n');proc.stdin.flush();report['exit_code']=proc.wait(timeout=120);reader.join(timeout=15)
        need(report['exit_code']==0 and not reader.is_alive(),'Unclean process stop')
        report['targeted_errors']=[line.strip() for line in lines if any(t in line for t in BAD)];need(not report['targeted_errors'],'Targeted server errors');report['pass']=True
    except Exception as e:
        report['error']=repr(e)
        if result.is_file():
            try:report['observed']=json.loads(result.read_text())
            except Exception:pass
    finally:
        if client:client.close();save(name+'-client.json',client.events)
        if proc is not None and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=45)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=15)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if reader:reader.join(timeout=15)
        save(name+'-phase.json',report);print('SWIFT_PHASE',name,json.dumps(report,ensure_ascii=False),flush=True)
    return report

def main():
    build=json.loads((OUT/'swift-build.json').read_text());need(build['pass'] is True,'No built pack')
    new=OUT/'NeverOverworld-R3915.zip';need(sha(new)==build['output_sha256'],'Candidate pack modified')
    core=exact('server.jar',CORE);base=exact('NeverOverworld.zip',BASE);nether=exact('NeverNether.zip',NETHER)
    classes=WORK/'qa-classes';classes.mkdir(exist_ok=False);cp=(WORK/'classpath.txt').read_text()
    p=subprocess.run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes),str(ROOT/'qa/field-r3915/R3915SwiftQa.java')],text=True,capture_output=True)
    (OUT/'swift-qa-javac.log').write_text(p.stdout+p.stderr);print(p.stdout+p.stderr,flush=True);need(p.returncode==0,'QA compile failed')
    plugin=WORK/'R3915SwiftQa.jar'
    with zipfile.ZipFile(plugin,'w',zipfile.ZIP_DEFLATED) as z:
        for path in classes.rglob('*.class'):z.write(path,path.relative_to(classes).as_posix())
        z.writestr('plugin.yml',"name: R3915SwiftQa\nversion: '1'\nmain: R3915SwiftQa\napi-version: '26.2'\nfolia-supported: true\n")
    Client,cfg=wire_config();report={'pass':False,'production_accepted':False,'scope':'Connected loopback player and real mount/dismount with server-side key inputs. No graphical client rendering.'}
    try:
        report['baseline']=phase('swift-baseline',core,setup('baseline',base,nether,plugin),True,Client,cfg);need(report['baseline']['pass'],'Baseline failed')
        candidate=setup('candidate',new,nether,plugin)
        report['candidate']=phase('swift-candidate',core,candidate,False,Client,cfg);need(report['candidate']['pass'],'Candidate failed')
        report['restart']=phase('swift-restart',core,candidate,False,Client,cfg);need(report['restart']['pass'],'Restart failed')
        need(sha(core)==CORE and sha(base)==BASE and sha(nether)==NETHER and sha(new)==build['output_sha256'],'Input changed')
        report['functional_tick_pass']=True
        report['author_detach_cleanup_complete']=not any(row['residual_rider_modifier_after_detach'] for phase_name in ('candidate','restart') for row in report[phase_name]['observed']['levels'])
        report['pass']=True
    except Exception as e:report['error']=repr(e)
    finally:save('swift-runtime.json',report)
    print('SWIFT_RUNTIME',json.dumps({k:v for k,v in report.items() if k not in ('baseline','candidate','restart')}),flush=True);need(report['pass'],'Runtime not accepted')
if __name__=='__main__':main()
