#!/usr/bin/env python3
from pathlib import Path
import json,os,queue,shutil,subprocess,threading,time,uuid,zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3937-runtime';CAND=ROOT/'candidate'

def need(v,m):
    if not v:raise ValueError(m)

def members(raw):
    import io
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        return {n:z.read(n) for n in z.namelist()}

def prepare_classpath():
    outer=members((CAND/'server.jar').read_bytes())
    libs=WORK/'libs';libs.mkdir(parents=True)
    jars=[]
    for i,(name,raw) in enumerate(outer.items()):
        if name.endswith('.jar') and name.startswith(('META-INF/versions/','META-INF/libraries/')):
            p=libs/(str(i)+'-'+Path(name).name)
            p.write_bytes(raw);jars.append(p)
    need(jars,'no bundled jars for QA classpath')
    return os.pathsep.join(map(str,sorted(jars)))

def run(args,name,timeout=300):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    (OUT/name).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'failed '+name)

def plugin():
    cp=prepare_classpath()
    classes=WORK/'classes';classes.mkdir()
    run([
      'javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),
      str(ROOT/'qa/field-r3937/R3937NetherRegistryQa.java')
    ],'registry-qa-javac.log')
    jar=WORK/'R3937NetherRegistryQa.jar'
    with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as z:
        for p in classes.rglob('*.class'):
            z.write(p,p.relative_to(classes).as_posix())
        z.writestr(
          'plugin.yml',
          "name: R3937NetherRegistryQa\nversion: '1'\nmain: R3937NetherRegistryQa\napi-version: '26.2'\nfolia-supported: true\n"
        )
    return jar

def prepare_server(jar):
    folder=WORK/'server'
    dp=folder/'world/datapacks'
    dp.mkdir(parents=True)
    (folder/'plugins').mkdir()
    shutil.copyfile(jar,folder/'plugins/R3937NetherRegistryQa.jar')
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
    nonce=uuid.uuid4().hex
    q=queue.Queue()
    p=subprocess.Popen([
      'java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G',
      f'-Dneverfolia.qaNonce={nonce}','-jar',str(CAND/'server.jar'),'--nogui'
    ],cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
      text=True,encoding='utf-8',errors='replace',bufsize=1)

    bad_patterns=(
      'Errors in currently selected datapacks',
      'Failed to load registries',
      'Failed to parse',
      'Unknown registry key',
      'NoSuchMethodError',
      'NoClassDefFoundError',
      'VerifyError',
      'ClassFormatError',
      'Chunk system error',
    )

    def pump():
        with (OUT/'registry-server.log').open('w') as f:
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
            if any(x in line for x in bad_patterns):
                raise RuntimeError(line.rstrip())
            if 'R3937 NETHER REGISTRY PASS '+nonce in line:
                ok=True;break
            if 'R3937 NETHER REGISTRY FAIL '+nonce in line:
                raise RuntimeError(line.rstrip())

        need(ok,'no R3937 registry PASS')
        rp=folder/'plugins/R3937NetherRegistryQa/result.json'
        need(rp.is_file(),'missing registry result')
        result=json.loads(rp.read_text())
        need(result.get('pass') is True,'registry result failed: '+repr(result))
        need(result.get('custom_present')==20,'not all 20 custom structures registered')
        need(not result.get('missing'),'custom registry missing IDs')
        need(not result.get('vanilla_missing'),'vanilla Nether structures disappeared')

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
    b=json.loads((OUT/'build-r3937.json').read_text())
    need(b.get('build_pass') is True,'build did not pass')
    result=phase(prepare_server(plugin()))
    report={
      'pass':True,
      'registry':result,
      'custom_present':20,
      'vanilla_nether_preserved':True,
      'startup_datapack_errors':False,
      'manual_natural_placement_check_required':True,
    }
    (OUT/'runtime-r3937.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('R3937_RUNTIME '+json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
