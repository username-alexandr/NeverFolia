#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,queue,shutil,subprocess,threading,time,uuid,zipfile,os
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3931-runtime';SEED=-4651369264513492755
CENTERS=((7,1),(1,-4),(-197,-217),(-169,-250),(-189,-223),(-1699,-769))
def need(v,m):
    if not v:raise ValueError(m)
def run(args,name):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240);(OUT/name).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'Failed '+name)
def prepare_plugin():
    cp=(ROOT/'.work/r3931-build/classpath.txt').read_text();classes=WORK/'classes';classes.mkdir(parents=True)
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),str(ROOT/'qa/field-r3931/R3931OceanQa.java')],'qa-javac.log')
    jar=WORK/'R3931OceanQa.jar'
    with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as z:
        for p in classes.rglob('*.class'):z.write(p,p.relative_to(classes).as_posix())
        z.writestr('plugin.yml',"name: R3931OceanQa\nversion: '1'\nmain: R3931OceanQa\napi-version: '26.2'\nfolia-supported: true\n")
    return jar
def prepare(name,jar,server,pack,nether):
    f=WORK/name;p=f/'world/datapacks';p.mkdir(parents=True);(f/'plugins').mkdir();shutil.copyfile(jar,f/'plugins/R3931OceanQa.jar');shutil.copyfile(pack,p/'NeverOverworld.zip');shutil.copyfile(nether,p/'NeverNether.zip')
    (f/'eula.txt').write_text('eula=true\n');(f/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25614\nonline-mode=true\nenable-status=false\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n')
    return f
def phase(name,folder,server):
    nonce=uuid.uuid4().hex;lines=[];q=queue.Queue();proc=subprocess.Popen(['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G',f'-Dneverfolia.qaNonce={nonce}','-jar',str(server),'--nogui'],cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
    def pump():
        with (OUT/(name+'.log')).open('w') as f:
            for line in proc.stdout:lines.append(line);f.write(line);f.flush();q.put(line)
        q.put(None)
    t=threading.Thread(target=pump,daemon=True);t.start();ok=False;deadline=time.monotonic()+700
    fatal=('NoSuchMethodError','NoClassDefFoundError','VerifyError','ClassFormatError','Chunk system error')
    try:
        while time.monotonic()<deadline:
            try:line=q.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if any(marker in line for marker in fatal):raise RuntimeError(name+' fatal runtime marker: '+line.rstrip())
            if 'R3931 OCEAN QA ' in line:need('R3931 OCEAN QA PASS '+nonce in line,line.rstrip());ok=True;break
        need(ok,'No QA PASS');rp=folder/'plugins/R3931OceanQa/result.json';need(rp.is_file(),'Missing result');r=json.loads(rp.read_text());need(r.get('pass') and r.get('nonce')==nonce and r.get('completed_chunks')==4,'Bad result')
        proc.stdin.write('stop\n');proc.stdin.flush();code=proc.wait(timeout=120);t.join(timeout=10);need(code==0,'Abnormal stop')
        return r
    finally:
        if proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=30)
            except Exception:proc.kill();proc.wait(timeout=10)
        t.join(timeout=10)
def sums(r):
    keys=('water_0_128','air_0_128','isolated_air_in_water','ice_below_128','ice_at_128',
          'plain_ice_below_128','packed_ice_below_128','blue_ice_below_128','frosted_ice_below_128',
          'plain_ice_0_62','plain_ice_at_63','plain_ice_64_126','plain_ice_at_127','plain_ice_at_128',
          'long_air_columns_ge16','long_air_columns_under_roof')
    return {k:sum(x[k] for x in r['chunks']) for k in keys}
def main():
    WORK.mkdir(parents=True,exist_ok=False);b=json.loads((OUT/'build.json').read_text());jar=prepare_plugin()
    base=prepare('baseline',jar,ROOT/'baseline/server.jar',ROOT/'baseline/world/datapacks/NeverOverworld.zip',ROOT/'baseline/world/datapacks/NeverNether.zip')
    cand=prepare('candidate',jar,ROOT/'candidate/server.jar',ROOT/'candidate/NeverOverworld.zip',ROOT/'candidate/NeverNether.zip')
    rb=phase('baseline',base,ROOT/'baseline/server.jar');rc=phase('candidate',cand,ROOT/'candidate/server.jar')
    sb,sc=sums(rb),sums(rc);report={'pass':True,'baseline':sb,'candidate':sc,'delta':{k:sc[k]-sb[k] for k in sb},'production_accepted':False,'scope':'4 critical natural chunks: islands, cold ocean, frozen ocean, coast'}
    (OUT/'runtime.json').write_text(json.dumps(report,indent=2)+'\n');print('R3931_RUNTIME '+json.dumps(report),flush=True)
if __name__=='__main__':main()
