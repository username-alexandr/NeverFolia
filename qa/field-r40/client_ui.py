#!/usr/bin/env python3
"""Real graphical client test under Xvfb. Downloads only official game/loader inputs.
Minecraft files, natives and assets are private CI inputs and are never published.
Only the authored UI mod, logs and validation reports may be released.
"""
from pathlib import Path
import concurrent.futures,hashlib,io,json,os,shutil,subprocess,threading,time,urllib.request,uuid,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'client-ui-evidence';WORK=ROOT/'.work/r40-client';SEED=-4651369264513492755
HEADERS={'User-Agent':'NeverFolia-UI-QA/1.0'}
TRANSLATIONS={'aerials_bane':'Гроза летающих','antidote':'Противоядие','conductivity_curse':'Проклятие проводимости','ghasted':'Сила гаста','gravity':'Гравитация','hydro_veil':'Водяная завеса','illagers_bane':'Гроза разбойников','multishot':'Тройной выстрел','outreach':'Досягаемость','photosynthesis':'Фотосинтез','piercing':'Сквозной выстрел','power':'Мощь','spiteful':'Мстительность','swift_soar':'Стремительный полёт','traveler':'Путешественник','wax_wings':'Восковые крылья','wither_coated':'Иссушающее покрытие','non_survival_enchant':'Служебное зачарование'}
def need(ok,msg):
    if not ok:raise ValueError(msg)
def rawget(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers=HEADERS),timeout=90) as response:return response.read()
def getjson(url):return json.loads(rawget(url))
def download(url,path,sha1=None):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and (sha1 is None or hashlib.sha1(path.read_bytes()).hexdigest()==sha1):return path
    raw=rawget(url)
    if sha1:need(hashlib.sha1(raw).hexdigest()==sha1,'Official download checksum mismatch')
    path.write_bytes(raw);return path
def allowed(rules):
    if not rules:return True
    answer=False
    for rule in rules:
        osrule=rule.get('os',{})
        if osrule.get('name','linux')!='linux':continue
        if osrule.get('arch') not in (None,'x86_64','amd64'):continue
        if rule.get('features'):continue
        answer=rule.get('action')=='allow'
    return answer
def javac(args,name):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    (OUT/name).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'Failed '+name)
def package(path,classes,metadata,config,translation=False):
    with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as z:
        for p in classes.rglob('*.class'):z.write(p,p.relative_to(classes).as_posix())
        z.writestr('fabric.mod.json',json.dumps(metadata,indent=2));z.writestr(metadata['mixins'][0],json.dumps(config,indent=2))
        if translation:z.writestr('assets/neverland_enchantment_ui/lang/ru_ru.json',json.dumps({'enchantment.dnt.'+k:v for k,v in TRANSLATIONS.items()},ensure_ascii=False,indent=2))
def main():
    OUT.mkdir(exist_ok=False);WORK.mkdir(parents=True,exist_ok=False)
    manifest=getjson('https://piston-meta.mojang.com/mc/game/version_manifest_v2.json');matches=[v for v in manifest['versions'] if v['id']=='26.2'];need(len(matches)==1,'Missing exact Minecraft 26.2')
    versionraw=rawget(matches[0]['url']);need(hashlib.sha1(versionraw).hexdigest()==matches[0]['sha1'],'Version metadata digest mismatch');version=json.loads(versionraw)
    profile=getjson('https://meta.fabricmc.net/v2/versions/loader/26.2/0.19.3/profile/json')
    (OUT/'game-version.json').write_text(json.dumps(version,indent=2));(OUT/'fabric-profile.json').write_text(json.dumps(profile,indent=2))
    jars=[];libraries=WORK/'libraries';natives=WORK/'natives';natives.mkdir();tasks=[]
    client=version['downloads']['client'];clientjar=download(client['url'],WORK/'minecraft-client.jar',client['sha1']);jars.append(clientjar)
    for lib in version['libraries']:
        if not allowed(lib.get('rules')):continue
        info=lib.get('downloads',{}).get('artifact')
        if info:tasks.append((info['url'],libraries/info['path'],info.get('sha1')))
        classifier=lib.get('natives',{}).get('linux')
        if classifier:
            classifier=classifier.replace('${arch}','64');native=lib.get('downloads',{}).get('classifiers',{}).get(classifier)
            if native:tasks.append((native['url'],libraries/native['path'],native.get('sha1')))
    for lib in profile.get('libraries',[]):
        group,artifact,v=lib['name'].split(':',2);relative=group.replace('.','/')+'/'+artifact+'/'+v+'/'+artifact+'-'+v+'.jar'
        tasks.append((lib.get('url','https://maven.fabricmc.net/').rstrip('/')+'/'+relative,libraries/relative,None))
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:jars.extend(pool.map(lambda t:download(*t),tasks))
    jars=list(dict.fromkeys(jars))
    for p in jars:
        with zipfile.ZipFile(p) as z:
            for n in z.namelist():
                if n.endswith('.so') and not n.startswith('META-INF/'):
                    target=natives/Path(n).name;payload=z.read(n)
                    if target.exists():need(target.read_bytes()==payload,'Conflicting native library '+target.name)
                    else:target.write_bytes(payload)
    cp=os.pathsep.join(str(p) for p in jars)
    # Compile against the real client, not server API stubs.
    mainclasses=WORK/'mod-classes';qaclasses=WORK/'qa-classes';mainclasses.mkdir();qaclasses.mkdir()
    sources=sorted((ROOT/'client/neverland-enchantment-ui/src').rglob('*.java'))
    javac(['javac','--release','25','-proc:none','-cp',cp,'-d',str(mainclasses)]+[str(p) for p in sources],'mod-javac.log')
    javac(['javac','--release','25','-proc:none','-cp',cp,'-d',str(qaclasses),str(ROOT/'qa/field-r40/ClientUiQaMixin.java')],'qa-javac.log')
    gamedir=WORK/'game';mods=gamedir/'mods';mods.mkdir(parents=True)
    mod=OUT/'NeverLand-Enchantment-UI-Fabric-26.2-R40.jar'
    metadata={'schemaVersion':1,'id':'neverland_enchantment_ui','version':'0.2.0-r40','name':'NeverLand Enchantment UI','environment':'client','mixins':['neverland-enchantment-ui.mixins.json'],'depends':{'fabricloader':'>=0.19.3','minecraft':'26.2','java':'>=25'}}
    config={'required':True,'minVersion':'0.8','package':'cc.neverland.client','compatibilityLevel':'JAVA_25','client':['CreativeBookMixin'],'injectors':{'defaultRequire':1}}
    package(mod,mainclasses,metadata,config,True);shutil.copyfile(mod,mods/mod.name)
    qm={'schemaVersion':1,'id':'neverland_ui_qa','version':'1','environment':'client','mixins':['neverland-ui-qa.mixins.json'],'depends':{'fabricloader':'>=0.19.3','minecraft':'26.2','java':'>=25'}}
    qc={'required':True,'minVersion':'0.8','package':'cc.neverland.qa','compatibilityLevel':'JAVA_25','client':['ClientUiQaMixin'],'injectors':{'defaultRequire':1}}
    package(mods/'NeverLand-UI-QA.jar',qaclasses,qm,qc)
    assets=WORK/'assets';index=version['assetIndex'];indexpath=download(index['url'],assets/'indexes'/(index['id']+'.json'),index['sha1']);objects=json.loads(indexpath.read_text())['objects']
    asset_tasks=[];skipped=0
    for name,v in objects.items():
        if name.endswith(('.ogg','.mp3')):skipped+=1;continue
        h=v['hash'];asset_tasks.append(('https://resources.download.minecraft.net/'+h[:2]+'/'+h,assets/'objects'/h[:2]/h,h))
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:list(pool.map(lambda t:download(*t),asset_tasks))
    (gamedir/'options.txt').write_text('lang:ru_ru\nrenderDistance:2\nsimulationDistance:2\nmaxFps:30\nsoundCategory_master:0.0\n')
    expected={}
    with zipfile.ZipFile(ROOT/'baseline/world/datapacks/NeverOverworld.zip') as z:
        for name in z.namelist():
            if name.startswith('data/nova_structures/enchantment/') and name.endswith('.json'):
                obj=json.loads(z.read(name))
                if obj.get('description',{}).get('translate')=='enchantment.dnt.non_survival_enchant':expected['nova_structures:'+name.split('/enchantment/')[1][:-5]]=False
        gameplay=json.loads(z.read('data/nova_structures/tags/enchantment/all_dnt_enchants.json'))['values'];expected.update({v:True for v in gameplay})
    expected.update({'minecraft:sharpness':True,'minecraft:protection':True});need(len(expected)==35,'Unexpected enchantment scope')
    (gamedir/'expected-ui-enchants.json').write_text(json.dumps(expected,indent=2))
    server=WORK/'server';(server/'world/datapacks').mkdir(parents=True)
    for name in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(ROOT/'baseline/world/datapacks'/name,server/'world/datapacks'/name)
    # Offline login exists only on the loopback ephemeral CI test, never in a user kit.
    (server/'eula.txt').write_text('eula=true\n');(server/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25641\nonline-mode=false\nenforce-secure-profile=false\nwhite-list=false\nmax-players=1\ngamemode=creative\nview-distance=2\nsimulation-distance=2\nenable-rcon=false\npause-when-empty-seconds=-1\n')
    nonce=uuid.uuid4().hex;sp=None;cl=None;serverlines=[];thread=None;report={'pass':False,'nonce':nonce,'game_version':'26.2','fabric_loader':'0.19.3','audio_assets_skipped':skipped,'production_accepted':False}
    try:
        need(hashlib.sha256((ROOT/'baseline/server.jar').read_bytes()).hexdigest()=='c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67','Wrong test server')
        sp=subprocess.Popen(['java','-XX:ActiveProcessorCount=2','-Xms512M','-Xmx2G','-jar',str(ROOT/'baseline/server.jar'),'--nogui'],cwd=server,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
        def pump():
            with (OUT/'server.log').open('w') as out:
                for line in sp.stdout:out.write(line);out.flush();serverlines.append(line)
        thread=threading.Thread(target=pump,daemon=True);thread.start();deadline=time.monotonic()+300
        while time.monotonic()<deadline and not any('Done (' in x for x in serverlines):
            need(sp.poll() is None,'Server failed before startup');time.sleep(.25)
        need(any('Done (' in x for x in serverlines),'Server did not become ready')
        command=['xvfb-run','-a','java','-Xms512M','-Xmx2G','-Djava.library.path='+str(natives),'-Dorg.lwjgl.librarypath='+str(natives),'-Dneverfolia.qaNonce='+nonce,'-cp',cp,profile['mainClass'],'--username','NeverLandUiQa','--uuid',uuid.uuid3(uuid.NAMESPACE_DNS,'NeverLandUiQa').hex,'--accessToken','0','--version','26.2','--versionType','release','--gameDir',str(gamedir),'--assetsDir',str(assets),'--assetIndex',index['id'],'--userType','legacy','--width','854','--height','480','--quickPlayMultiplayer','127.0.0.1:25641']
        env=dict(os.environ,ALSOFT_DRIVERS='null',LIBGL_ALWAYS_SOFTWARE='1')
        with (OUT/'client.log').open('w') as log:
            cl=subprocess.Popen(command,cwd=gamedir,stdout=log,stderr=subprocess.STDOUT,env=env);report['client_exit']=cl.wait(timeout=300)
        observed=json.loads((gamedir/'client-ui-result.json').read_text());need(observed.get('pass') is True and observed.get('nonce')==nonce and report['client_exit']==0,'Client UI regression failed')
        report['observed']=observed;sp.stdin.write('stop\n');sp.stdin.flush();report['server_exit']=sp.wait(timeout=120);thread.join(timeout=10);need(report['server_exit']==0,'Server did not stop normally')
        report['mod_sha256']=hashlib.sha256(mod.read_bytes()).hexdigest();report['pass']=True
    except Exception as error:report['error']=repr(error)
    finally:
        if cl is not None and cl.poll() is None:cl.terminate();cl.wait(timeout=30)
        if sp is not None and sp.poll() is None:
            try:sp.stdin.write('stop\n');sp.stdin.flush();sp.wait(timeout=90)
            except Exception:sp.terminate();sp.wait(timeout=30)
        if thread is not None:thread.join(timeout=10)
        if (gamedir/'client-ui-result.json').exists():shutil.copyfile(gamedir/'client-ui-result.json',OUT/'actual-client-ui-result.json')
        (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print('R40_CLIENT_UI_RESULT',json.dumps(report),flush=True)
        if not report['pass'] and mod.exists():mod.rename(mod.with_name('UNACCEPTED-'+mod.name))
    need(report['pass'],'Actual Fabric client acceptance did not pass')
if __name__=='__main__':main()
