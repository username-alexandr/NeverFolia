#!/usr/bin/env python3
from pathlib import Path
import io,json,os,queue,struct,subprocess,threading,time,uuid,zipfile,zlib,gzip,shutil

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3934-trace';CAND=ROOT/'candidate'
SEED=-4651369264513492755
CENTER=(-205,-224)
RADIUS=8

def need(v,m):
    if not v: raise ValueError(m)

def run(args,name,timeout=300):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    (OUT/name).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'failed '+name)

def nbt_parse(data:bytes):
    f=io.BytesIO(data)
    def needb(n):
        b=f.read(n)
        if len(b)!=n:raise ValueError('truncated NBT')
        return b
    def u1():return struct.unpack('>B',needb(1))[0]
    def i1():return struct.unpack('>b',needb(1))[0]
    def i2():return struct.unpack('>h',needb(2))[0]
    def i4():return struct.unpack('>i',needb(4))[0]
    def i8():return struct.unpack('>q',needb(8))[0]
    def flt():return struct.unpack('>f',needb(4))[0]
    def dbl():return struct.unpack('>d',needb(8))[0]
    def string():
        n=struct.unpack('>H',needb(2))[0];return needb(n).decode('utf-8')
    def payload(t):
        if t==1:return i1()
        if t==2:return i2()
        if t==3:return i4()
        if t==4:return i8()
        if t==5:return flt()
        if t==6:return dbl()
        if t==7:return needb(i4())
        if t==8:return string()
        if t==9:
            et=u1();n=i4()
            if n<0:raise ValueError('negative list')
            if et==0:
                need(n==0,'non-empty TAG_End list');return []
            return [payload(et) for _ in range(n)]
        if t==10:
            o={}
            while True:
                ct=u1()
                if ct==0:return o
                name=string();o[name]=payload(ct)
        if t==11:
            n=i4();need(n>=0,'negative int array');return [i4() for _ in range(n)]
        if t==12:
            n=i4();need(n>=0,'negative long array');return [i8() for _ in range(n)]
        raise ValueError('unsupported tag '+str(t))
    rt=u1();need(rt==10,'root not compound');string();return payload(rt)

def prepare_plugin():
    cp=(ROOT/'.work/r3933-build/classpath.txt').read_text()
    classes=WORK/'classes';classes.mkdir(parents=True)
    src=ROOT/'qa/field-r3934/R3934StructureTrace.java'
    run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),str(src)],'trace-javac.log')
    jar=WORK/'R3934StructureTrace.jar'
    with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as z:
        for p in classes.rglob('*.class'):z.write(p,p.relative_to(classes).as_posix())
        z.writestr('plugin.yml',"name: R3934StructureTrace\nversion: '1'\nmain: R3934StructureTrace\napi-version: '26.2'\nfolia-supported: true\n")
    return jar

def prepare_server(plugin):
    folder=WORK/'server';dp=folder/'world/datapacks';dp.mkdir(parents=True);(folder/'plugins').mkdir()
    shutil.copyfile(plugin,folder/'plugins/R3934StructureTrace.jar')
    shutil.copyfile(CAND/'NeverOverworld.zip',dp/'NeverOverworld.zip')
    shutil.copyfile(CAND/'NeverNether.zip',dp/'NeverNether.zip')
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text(
      f'level-name=world\nlevel-seed={SEED}\n'
      'initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n'
      'server-ip=127.0.0.1\nserver-port=25614\nonline-mode=false\nenable-status=false\n'
      'view-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n'
    )
    return folder

def run_server(folder):
    nonce=uuid.uuid4().hex;lines=[];q=queue.Queue()
    p=subprocess.Popen(['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G',f'-Dneverfolia.qaNonce={nonce}','-jar',str(CAND/'server.jar'),'--nogui'],
        cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
    def pump():
        with (OUT/'trace-server.log').open('w') as f:
            for line in p.stdout:
                lines.append(line);f.write(line);f.flush();q.put(line)
        q.put(None)
    t=threading.Thread(target=pump,daemon=True);t.start();ok=False;deadline=time.monotonic()+1500
    try:
        while time.monotonic()<deadline:
            try:line=q.get(timeout=1)
            except queue.Empty:
                if p.poll() is not None:break
                continue
            if line is None:break
            if 'R3934 STRUCTURE TRACE PASS '+nonce in line:
                ok=True;break
            if any(x in line for x in ('NoSuchMethodError','NoClassDefFoundError','VerifyError','Chunk system error')):
                raise RuntimeError(line.strip())
        need(ok,'trace plugin did not finish')
        p.stdin.write('save-all flush\n');p.stdin.flush();time.sleep(3)
        p.stdin.write('stop\n');p.stdin.flush();code=p.wait(timeout=180);t.join(timeout=20);need(code==0,'abnormal stop')
    finally:
        if p.poll() is None:
            try:p.stdin.write('stop\n');p.stdin.flush();p.wait(timeout=30)
            except Exception:p.kill()
        t.join(timeout=10)

def read_region_chunk(path,cx,cz):
    rx=cx//32;rz=cz//32
    need(path.name==f'r.{rx}.{rz}.mca','region mismatch')
    raw=path.read_bytes()
    idx=(cx%32)+(cz%32)*32
    loc=struct.unpack('>I',raw[idx*4:idx*4+4])[0]
    off=(loc>>8)*4096;sectors=loc&255
    if off==0 or sectors==0:return None
    length=struct.unpack('>I',raw[off:off+4])[0]
    ctype=raw[off+4]
    payload=raw[off+5:off+4+length]
    if ctype==1:data=gzip.decompress(payload)
    elif ctype==2:data=zlib.decompress(payload)
    elif ctype==3:data=payload
    else:raise ValueError('unsupported region compression '+str(ctype))
    return nbt_parse(data)

def decode_chunkpos(v):
    u=v & ((1<<64)-1)
    x=(u>>32)&0xffffffff;z=u&0xffffffff
    if x>=2**31:x-=2**32
    if z>=2**31:z-=2**32
    return [x,z]

def collect_structures(folder):
    starts=[];refs=[];chunks=0
    world=folder/'world'
    storage_files=[]
    for p in world.rglob('*'):
        if p.is_file() and (p.suffix in ('.mca','.mcc','.linear') or 'region' in p.parent.name.lower()):
            storage_files.append({'path':str(p.relative_to(folder)),'size':p.stat().st_size})
    # Find the actual chunk-region directory instead of assuming one layout.
    region_dirs=sorted({p.parent for p in world.rglob('r.*.*.mca') if p.parent.name=='region'})
    for cz in range(CENTER[1]-RADIUS,CENTER[1]+RADIUS+1):
        for cx in range(CENTER[0]-RADIUS,CENTER[0]+RADIUS+1):
            rp=None
            for rd in region_dirs:
                candidate=rd/f'r.{cx//32}.{cz//32}.mca'
                if candidate.is_file():
                    rp=candidate;break
            if rp is None:continue
            root=read_region_chunk(rp,cx,cz)
            if not root:continue
            chunks+=1
            s=root.get('structures') or root.get('Structures') or {}
            sm=s.get('starts') or s.get('Starts') or {}
            for key,val in sm.items():
                if not isinstance(val,dict):continue
                sid=val.get('id') or key
                if sid=='INVALID':continue
                children=val.get('Children') or val.get('children') or []
                bbs=[]
                for ch in children:
                    if isinstance(ch,dict):
                        bb=ch.get('BB') or ch.get('bb') or ch.get('bounding_box')
                        if bb is not None:bbs.append(bb)
                starts.append({'chunk':[cx,cz],'key':key,'id':sid,'children':len(children),'piece_bbs':bbs[:64]})
            rm=s.get('References') or s.get('references') or {}
            for key,arr in rm.items():
                if isinstance(arr,list) and arr:
                    refs.append({'chunk':[cx,cz],'key':key,'start_chunks':[decode_chunkpos(v) for v in arr]})
    return {
      'chunks_parsed':chunks,
      'starts':starts,
      'references':refs,
      'region_dirs':[str(x.relative_to(folder)) for x in region_dirs],
      'storage_files':storage_files[:200]
    }

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False)
    plugin=prepare_plugin();folder=prepare_server(plugin);run_server(folder)
    report=collect_structures(folder)
    (OUT/'structure-trace.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('R3934_TRACE '+json.dumps({
      'chunks_parsed':report['chunks_parsed'],
      'start_count':len(report['starts']),
      'reference_count':len(report['references']),
      'region_dirs':report.get('region_dirs',[]),\n      'storage_file_count':len(report.get('storage_files',[])),\n      'storage_files':report.get('storage_files',[])[:30],\n      'starts':[{'chunk':x['chunk'],'id':x['id'],'children':x['children']} for x in report['starts']]\n    },ensure_ascii=False))

if __name__=='__main__':main()
