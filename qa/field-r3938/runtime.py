#!/usr/bin/env python3
from pathlib import Path
import json,os,queue,shutil,subprocess,threading,time,uuid,zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3938-runtime';CAND=ROOT/'candidate'

def need(v,m):
    if not v:raise ValueError(m)

def run(args,name,timeout=300):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    (OUT/name).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'failed '+name)

def plugin():
    cp=(ROOT/'.work/r3938-build/classpath.txt').read_text()
    classes=WORK/'classes';classes.mkdir(parents=True)
    run([
      'javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),
      str(ROOT/'qa/field-r3938/R3938FastLocateQa.java')
    ],'qa-javac.log')
    jar=WORK/'R3938FastLocateQa.jar'
    with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as z:
        for p in classes.rglob('*.class'):z.write(p,p.relative_to(classes).as_posix())
        z.writestr('plugin.yml',"name: R3938FastLocateQa\nversion: '1'\nmain: R3938FastLocateQa\napi-version: '26.2'\nfolia-supported: true\n")
    return jar

def prepare(jar):
    folder=WORK/'server';dp=folder/'world/datapacks';dp.mkdir(parents=True);(folder/'plugins').mkdir()
    shutil.copyfile(jar,folder/'plugins/R3938FastLocateQa.jar')
    shutil.copyfile(CAND/'NeverOverworld.zip',dp/'NeverOverworld.zip')
    shutil.copyfile(CAND/'NeverNether.zip',dp/'NeverNether.zip')
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text(
      'level-name=world\n'
      'level-seed=-4651369264513492755\n'
      'initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n'
      'server-ip=127.0.0.1\nserver-port=25614\nonline-mode=false\nenable-status=false\n'
      'view-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n'
    )
    return folder

def phase(folder):
    nonce=uuid.uuid4().hex;q=queue.Queue()
    p=subprocess.Popen([
      'java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G',
      f'-Dneverfolia.qaNonce={nonce}','-Dneverfolia.r3938Trace=true',
      '-jar',str(CAND/'server.jar'),'--nogui'
    ],cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
      text=True,encoding='utf-8',errors='replace',bufsize=1)

    fatal=(
      'NoSuchMethodError','NoClassDefFoundError','VerifyError','ClassFormatError',
      'Chunk system error','has not responded in'
    )

    def pump():
        with (OUT/'fast-locate-server.log').open('w') as f:
            for line in p.stdout:
                f.write(line);f.flush();q.put(line)
        q.put(None)

    t=threading.Thread(target=pump,daemon=True);t.start()
    ok=False;deadline=time.monotonic()+900
    try:
        while time.monotonic()<deadline:
            try:line=q.get(timeout=1)
            except queue.Empty:
                if p.poll() is not None:break
                continue
            if line is None:break
            if any(x in line for x in fatal):
                raise RuntimeError(line.rstrip())
            if 'R3938 FAST LOCATE PASS '+nonce in line:
                ok=True;break
            if 'R3938 FAST LOCATE FAIL '+nonce in line:
                raise RuntimeError(line.rstrip())

        need(ok,'no R3938 fast-locate PASS')
        rp=folder/'plugins/R3938FastLocateQa/result.json'
        need(rp.is_file(),'missing QA result')
        result=json.loads(rp.read_text())
        need(result.get('pass') is True,'fast-locate QA failed: '+repr(result))
        need(int(result.get('elapsed_ms',999999))<4000,'locate exceeded 4s')
        need(result.get('generated_nether_keep') is True,'located candidate did not generate')

        p.stdin.write('stop\n');p.stdin.flush()
        code=p.wait(timeout=180);t.join(timeout=20);need(code==0,'abnormal stop')
        return result
    finally:
        if p.poll() is None:
            try:p.stdin.write('stop\n');p.stdin.flush();p.wait(timeout=30)
            except Exception:p.kill()
        t.join(timeout=10)

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False)
    b=json.loads((OUT/'build-r3938.json').read_text())
    need(b.get('build_pass') is True,'build did not pass')
    result=phase(prepare(plugin()))
    report={
      'pass':True,
      'fast_locate':result,
      'watchdog_stall':False,
      'located_candidate_generated':True,
      'manual_player_command_check_required':True
    }
    (OUT/'runtime-r3938.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R3938_RUNTIME '+json.dumps(report),flush=True)

if __name__=='__main__':main()
