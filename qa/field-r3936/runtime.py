#!/usr/bin/env python3
from pathlib import Path
import json,os,queue,shutil,subprocess,threading,time,uuid,zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3936-runtime';CAND=ROOT/'candidate'
SEED=-4651369264513492755

def need(v,m):
    if not v:raise ValueError(m)

def run(args,name,timeout=300):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    (OUT/name).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'failed '+name)

def plugin():
    cp=(ROOT/'.work/r3936-build/classpath.txt').read_text()
    classes=WORK/'classes';classes.mkdir(parents=True)
    run([
      'javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),
      str(ROOT/'qa/field-r3936/R3936UndergroundQa.java')
    ],'qa-javac.log')
    jar=WORK/'R3936UndergroundQa.jar'
    with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as z:
        for p in classes.rglob('*.class'):z.write(p,p.relative_to(classes).as_posix())
        z.writestr('plugin.yml',"name: R3936UndergroundQa\nversion: '1'\nmain: R3936UndergroundQa\napi-version: '26.2'\nfolia-supported: true\n")
    return jar

def prepare(jar):
    f=WORK/'server';dp=f/'world/datapacks';dp.mkdir(parents=True);(f/'plugins').mkdir()
    shutil.copyfile(jar,f/'plugins/R3936UndergroundQa.jar')
    shutil.copyfile(CAND/'NeverOverworld.zip',dp/'NeverOverworld.zip')
    shutil.copyfile(CAND/'NeverNether.zip',dp/'NeverNether.zip')
    (f/'eula.txt').write_text('eula=true\n')
    (f/'server.properties').write_text(
      f'level-name=world\nlevel-seed={SEED}\n'
      'initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n'
      'server-ip=127.0.0.1\nserver-port=25614\nonline-mode=false\nenable-status=false\n'
      'view-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n'
    )
    return f

def phase(folder):
    nonce=uuid.uuid4().hex;q=queue.Queue()
    p=subprocess.Popen([
      'java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G',
      f'-Dneverfolia.qaNonce={nonce}','-jar',str(CAND/'server.jar'),'--nogui'
    ],cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
      text=True,encoding='utf-8',errors='replace',bufsize=1)

    def pump():
        with (OUT/'underground-server.log').open('w') as f:
            for line in p.stdout:
                f.write(line);f.flush();q.put(line)
        q.put(None)

    t=threading.Thread(target=pump,daemon=True);t.start()
    ok=False;deadline=time.monotonic()+1200
    fatal=('NoSuchMethodError','NoClassDefFoundError','VerifyError','ClassFormatError','Chunk system error')
    try:
        while time.monotonic()<deadline:
            try:line=q.get(timeout=1)
            except queue.Empty:
                if p.poll() is not None:break
                continue
            if line is None:break
            if any(x in line for x in fatal):raise RuntimeError(line.rstrip())
            if 'R3936 UNDERGROUND QA PASS '+nonce in line:
                ok=True;break
            if 'R3936 UNDERGROUND QA FAIL '+nonce in line:
                raise RuntimeError(line.rstrip())

        need(ok,'no R3936 underground QA PASS')
        rp=folder/'plugins/R3936UndergroundQa/result.json'
        need(rp.is_file(),'missing result')
        result=json.loads(rp.read_text())
        need(result.get('pass') is True,'bad result: '+repr(result))
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
    b=json.loads((OUT/'build-r3936.json').read_text())
    need(b.get('build_pass') is True,'build did not pass')
    result=phase(prepare(plugin()))
    structures=result.get('structures',[])
    need(len(structures)>=2,'too few runtime custom structures')
    for row in structures:
        need(-512<=int(row['min_y'])<=511,'runtime minY outside dimension')
        need(-512<=int(row['max_y'])<=511,'runtime maxY outside dimension')

    ys=[int(row['min_y']) for row in structures]
    report={
      'pass':True,
      'runtime':result,
      'observed_structure_min_y':ys,
      'static_policy':{
        'per_profile_y_bands_removed':True,
        'global_start_y':[-480,480],
        'dynamic_upper_bound':'OCEAN_FLOOR_WG minus surface cover'
      },
      'manual_distribution_check_required':True
    }
    (OUT/'runtime-r3936.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('R3936_RUNTIME '+json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
