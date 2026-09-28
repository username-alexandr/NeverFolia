#!/usr/bin/env python3
"""Incremental exact-R3913 Java 25 lifecycle fix. No worldgen class changes.
A standard JDK class-file transform adds one call; every other helper method
is required byte-identical, as is every unrelated bundled entry.
"""
from pathlib import Path
import hashlib,importlib.util,io,json,os,struct,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';WORK=ROOT/'.work/r3915';SRC=Path(__file__).parent
CORE='9571073a77086b04ce54594fe2b91737fdf9daf4019d4ce585016f77c03912f6'
TARGET='net/minecraft/world/item/enchantment/EnchantmentHelper.class'
HELPER='net/minecraft/world/item/enchantment/NeverFoliaSwiftLifecycleR3915.class'
DESC='(Lnet/minecraft/server/level/ServerLevel;Lnet/minecraft/world/entity/LivingEntity;)V'
def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def run(args,name):
    p=subprocess.run(args,text=True,capture_output=True,timeout=90);(OUT/name).write_text(p.stdout+p.stderr);print(p.stdout+p.stderr,flush=True);need(p.returncode==0,'Failed: '+name);return p.stdout

def parts(raw):
    """Raw method_info comparison; constant-pool old indices must stay stable."""
    need(raw[:4]==b'\xca\xfe\xba\xbe','Wrong class');pos=8
    def u2():
        nonlocal pos
        n=struct.unpack_from('>H',raw,pos)[0];pos+=2;return n
    def u4():
        nonlocal pos
        n=struct.unpack_from('>I',raw,pos)[0];pos+=4;return n
    cp={};utf={};total=u2();i=1
    while i<total:
        start=pos;t=raw[pos];pos+=1
        if t==1:
            n=u2();utf[i]=raw[pos:pos+n];pos+=n
        elif t in (3,4,9,10,11,12,17,18):pos+=4
        elif t in (5,6):pos+=8
        elif t in (7,8,16,19,20):pos+=2
        elif t==15:pos+=3
        else:raise ValueError('Unsupported class constant '+str(t))
        cp[i]=raw[start:pos];i+=2 if t in (5,6) else 1
    head=pos;pos+=6;n=u2();pos+=2*n;header=raw[head:pos]
    def attributes():
        nonlocal pos
        for _ in range(u2()):u2();n=u4();pos+=n
    fields_start=pos
    for _ in range(u2()):pos+=6;attributes()
    fields=raw[fields_start:pos];methods={}
    for _ in range(u2()):
        start=pos;u2();name=u2();desc=u2();attributes();key=(utf[name].decode(),utf[desc].decode());need(key not in methods,'Duplicate method');methods[key]=raw[start:pos]
    tail=raw[pos:];attributes();need(pos==len(raw),'Class trailing data')
    return cp,header,fields,methods,tail

def main():
    OUT.mkdir(exist_ok=True);report={'pass':False,'production_accepted':False}
    try:
        matches=list((ROOT/'inputs').rglob('server.jar'));need(len(matches)==1,'Ambiguous core');base=matches[0].read_bytes();need(sha(base)==CORE,'Unexpected base core')
        with zipfile.ZipFile(io.BytesIO(base)) as z:
            paths=[n for n in z.namelist() if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')];need(len(paths)==1,'Ambiguous inner core');path=paths[0];inner=z.read(path);versions=z.read('META-INF/versions.list').decode()
        cp=(WORK/'classpath.txt').read_text();classes=WORK/'lifecycle-classes';classes.mkdir(exist_ok=False)
        run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes),str(SRC/'NeverFoliaSwiftLifecycleR3915.java'),str(SRC/'SwiftTickHook.java')],'swift-kernel-javac.log')
        with zipfile.ZipFile(io.BytesIO(inner)) as z:before=z.read(TARGET);need(HELPER not in z.namelist(),'Already contains lifecycle helper')
        inp=WORK/'EnchantmentHelper-before.class';inp.write_bytes(before);target=WORK/'EnchantmentHelper-after.class';repeat=WORK/'EnchantmentHelper-repeat.class'
        for output,label in ((target,'swift-transform.log'),(repeat,'swift-transform-repeat.log')):
            run(['java','-cp',str(classes)+os.pathsep+cp,'SwiftTickHook',str(inp),str(output)],label)
        after=target.read_bytes();need(after==repeat.read_bytes(),'Hook transformation not reproducible')
        a,b=parts(before),parts(after)
        need(all(b[0].get(i)==v for i,v in a[0].items()),'Existing constant changed')
        need(a[1]==b[1] and a[2]==b[2] and a[4]==b[4],'Class header, fields or attributes changed')
        need(set(a[3])==set(b[3]),'Method set changed')
        changed=[key for key in a[3] if a[3][key]!=b[3][key]];need(changed==[('tickEffects',DESC)],'Unrelated methods changed: '+str(changed))
        spec=importlib.util.spec_from_file_location('r3915_jar',ROOT/'qa/field-r395/jar_packaging.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        replacement={TARGET:after,HELPER:(classes/HELPER).read_bytes()};new_inner=m.rewrite_zip(inner,replacement)
        with zipfile.ZipFile(io.BytesIO(inner)) as old,zipfile.ZipFile(io.BytesIO(new_inner)) as new:
            need(set(new.namelist())==set(old.namelist())|{HELPER},'Unexpected core entry set')
            untouched=[n for n in old.namelist() if n!=TARGET];need(all(old.read(n)==new.read(n) for n in untouched),'Unrelated core entry modified')
        rows=[];updated=0
        for line in versions.splitlines():
            row=line.split('\t');need(len(row)==3,'Invalid versions list')
            if 'META-INF/versions/'+row[2]==path:need(row[0]==sha(inner),'Base digest mismatch');row[0]=sha(new_inner);updated+=1
            rows.append('\t'.join(row))
        need(updated==1,'Wrong inner manifest mapping')
        result=m.rewrite_zip(base,{path:new_inner,'META-INF/versions.list':('\n'.join(rows)+'\n').encode()});(OUT/'server-r3915.jar').write_bytes(result)
        need(matches[0].read_bytes()==base,'Input overwritten')
        report.update({'pass':True,'base_core_sha256':CORE,'output_sha256':sha(result),'helper_sha256':sha(replacement[HELPER]),'changed_existing_entries':[TARGET],'added_entries':[HELPER],'preserved_existing_entries':len(untouched),'changed_existing_methods':changed,'preserved_helper_methods':len(a[3])-1,'repeat_transform_equal':True,'build_kind':'Java 25 helper compilation plus exact standard ClassFile API call insertion; not full Gradle','runtime_tested':False})
    except Exception as e:report['error']=repr(e);raise
    finally:(OUT/'swift-kernel.json').write_text(json.dumps(report,indent=2)+'\n');print('SWIFT_KERNEL',json.dumps(report),flush=True)
if __name__=='__main__':main()
