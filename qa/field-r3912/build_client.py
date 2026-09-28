#!/usr/bin/env python3
"""Build only client-owned classes/locales against pinned game and pack inputs.
No server/datapack/world files are rewritten. Client launch is a separate test.
"""
from __future__ import annotations
import argparse, hashlib, io, json, os, re, shutil, subprocess, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = 'c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67'
PACK = 'a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
RU = {
 'aerials_bane':'Гроза летающих', 'antidote':'Противоядие',
 'conductivity_curse':'Проклятие проводимости', 'ghasted':'Сила гаста',
 'gravity':'Гравитация', 'hydro_veil':'Водяная завеса',
 'illagers_bane':'Гроза разбойников', 'multishot':'Тройной выстрел',
 'outreach':'Досягаемость', 'photosynthesis':'Фотосинтез',
 'piercing':'Сквозной выстрел', 'power':'Мощь', 'spiteful':'Мстительность',
 'swift_soar':'Стремительный полёт', 'traveler':'Путешественник',
 'wax_wings':'Восковые крылья', 'wither_coated':'Иссушающее покрытие',
 'non_survival_enchant':'Служебное зачарование'
}
TECH_KEY = 'enchantment.dnt.non_survival_enchant'
TAG = 'nova_structures:non_survival_enchants'
RAVAGER = 'nova_structures:jockey/spawn_ravager_jockey'
HOSTS = {'piston-meta.mojang.com','piston-data.mojang.com', 'launchermeta.mojang.com',
         'launcher.mojang.com','maven.fabricmc.net','libraries.minecraft.net'}

def need(ok: bool, message: str) -> None:
    if not ok: raise ValueError(message)

def digest(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def sha(path: Path) -> str:
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()
def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def jbytes(data) -> bytes: return (json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf-8')

def download(url: str, maximum: int = 80_000_000) -> bytes:
    from urllib.parse import urlparse
    parsed=urlparse(url)
    need(parsed.scheme=='https' and parsed.hostname in HOSTS,'Unapproved build dependency URL')
    req=urllib.request.Request(url,headers={'User-Agent':'NeverFolia-client-build/3912'})
    with urllib.request.urlopen(req,timeout=90) as response:
        need(urlparse(response.geturl()).hostname in HOSTS,'Unapproved dependency redirect')
        raw=response.read(maximum+1)
    need(len(raw)<=maximum,'Dependency exceeded size limit')
    return raw

def archive_bytes(entries: dict[str,bytes]) -> bytes:
    need(all(n and not n.startswith('/') and '\\' not in n and '..' not in n.split('/') for n in entries),'Unsafe output member')
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,raw in sorted(entries.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,9,28,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=0o100644<<16
            z.writestr(info,raw)
    raw=stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(z.testzip() is None and len(z.namelist())==len(entries),'Invalid output archive')
        need(all(z.read(k)==v for k,v in entries.items()),'Archive payload changed')
    return raw

def unique(folder: Path, pattern: str, expected: str) -> Path:
    hits=[p for p in folder.rglob(pattern) if p.is_file() and sha(p)==expected]
    need(len(hits)==1,'Missing/ambiguous pinned '+pattern)
    return hits[0]

def classify_pack(path: Path) -> tuple[dict,dict]:
    need(sha(path)==PACK,'Different NeverOverworld pack: no guessed controller filter')
    with zipfile.ZipFile(path) as z:
        names=z.namelist(); need(len(names)==len(set(names)) and z.testzip() is None,'Invalid input ZIP')
        ench={}
        for name in names:
            prefix='data/nova_structures/enchantment/'
            if name.startswith(prefix) and name.endswith('.json'):
                ench['nova_structures:'+name[len(prefix):-5]]=json.loads(z.read(name))
        technical={k for k,v in ench.items() if v.get('description',{}).get('translate')==TECH_KEY}
        gameplay=set(json.loads(z.read('data/nova_structures/tags/enchantment/all_dnt_enchants.json'))['values'])
        def tag_values(key,stack=()):
            need(key not in stack,'Cyclic enchantment tag')
            ns,p=key.split(':',1); data=json.loads(z.read(f'data/{ns}/tags/enchantment/{p}.json'))
            values=set()
            for value in data['values']:
                need(isinstance(value,str),'Unexpected non-string tag entry')
                values.update(tag_values(value[1:],stack+(key,)) if value.startswith('#') else [value])
            return values
        tagged=tag_values(TAG)
        hidden=tagged|{RAVAGER}
        need(len(technical)==16 and len(gameplay)==17,'Unexpected exact pack registry scope')
        need(hidden==technical and not hidden&gameplay,'Filter does not match technical entries exactly')
        needed={ench[k]['description']['translate'] for k in technical|gameplay}
        translations={'enchantment.dnt.'+k:v for k,v in RU.items()}
        need(needed==set(translations),'Missing/extra locale keys: '+repr(needed^set(translations)))
        expected={k:False for k in sorted(technical)}
        expected.update({k:True for k in sorted(gameplay)})
        expected.update({'minecraft:sharpness':True,'minecraft:protection':True})
        report={'pack_sha256':PACK,'technical':sorted(technical),'gameplay':sorted(gameplay),
                'explicit_missing_tag_member':RAVAGER,'translations':translations,
                'descriptions':{k:ench[k]['description'] for k in sorted(technical|gameplay)},
                'registry_unchanged':True,'loot_unchanged':True}
        return expected,report

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,default=ROOT/'inputs')
    parser.add_argument('--debug',type=Path,default=ROOT/'debug')
    parser.add_argument('--output',type=Path,default=ROOT/'client-output')
    args=parser.parse_args(); out=args.output.resolve(); out.mkdir(exist_ok=False)
    work=ROOT/'.work/r3912'; work.mkdir(parents=True,exist_ok=False)
    libs=work/'libs'; libs.mkdir()
    base=unique(args.inputs,'server.jar',BASE); pack=unique(args.inputs,'NeverOverworld.zip',PACK)
    expected,pack_report=classify_pack(pack); save(out/'pack-contract.json',pack_report)
    save(work/'expected.json',expected)
    original_base=sha(base); original_pack=sha(pack)
    with zipfile.ZipFile(base) as z:
        for i,n in enumerate(z.namelist()):
            if n.endswith('.jar') and n.startswith(('META-INF/libraries/','META-INF/versions/')):
                (libs/(str(i)+'-'+Path(n).name)).write_bytes(z.read(n))
    providers=[]
    for p in libs.glob('*.jar'):
        with zipfile.ZipFile(p) as z:
            if 'org/bukkit/Bukkit.class' in z.namelist(): providers.append(p)
    if not providers:
        diagnostics=list(args.debug.rglob('diagnostics.zip')); need(len(diagnostics)==1,'Missing exact debug API')
        found=[]
        with zipfile.ZipFile(diagnostics[0]) as z:
            for n in z.namelist():
                if 'folia-api' in n and n.endswith('.jar'):
                    raw=z.read(n)
                    with zipfile.ZipFile(io.BytesIO(raw)) as api:
                        if 'org/bukkit/Bukkit.class' in api.namelist(): found.append(raw)
        need(len(found)==1,'Ambiguous debug API'); (libs/'folia-api.jar').write_bytes(found[0])
    def run(command,label):
        p=subprocess.run(command,capture_output=True,text=True,timeout=180)
        (out/(label+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
        need(p.returncode==0,label+' failed: '+(p.stdout+p.stderr)[-3000:]); return p.stdout+p.stderr
    version=run(['javac','-version'],'javac-version'); need(re.search(r'javac 25[.\s]',version) is not None,'JDK25 required')
    manifest=json.loads(download('https://piston-meta.mojang.com/mc/game/version_manifest_v2.json',10_000_000))
    selected=[v for v in manifest['versions'] if v['id']=='26.2']; need(len(selected)==1,'Missing official 26.2')
    vraw=download(selected[0]['url'],10_000_000)
    need(hashlib.sha1(vraw).hexdigest()==selected[0]['sha1'],'Version metadata checksum mismatch')
    vdata=json.loads(vraw); need(vdata['id']=='26.2','Wrong official client')
    client_meta=vdata['downloads']['client']; client_raw=download(client_meta['url'],120_000_000)
    need(len(client_raw)==client_meta['size'] and hashlib.sha1(client_raw).hexdigest()==client_meta['sha1'],'Official client checksum mismatch')
    client=work/'minecraft-client.jar'; client.write_bytes(client_raw)
    with zipfile.ZipFile(client) as z: game_version=json.loads(z.read('version.json'))
    save(out/'game-version.json',game_version)
    # Mojang's published 26.2 resource format. Reject a changed input, do not guess.
    resource=game_version['pack_version']['resource']
    resource_major=resource.get('major') if isinstance(resource,dict) else (resource[0] if isinstance(resource,list) else resource)
    need(resource_major==88,'Unexpected official resource format: '+repr(resource))
    disasm=run(['javap','-classpath',str(client),'-p','-c', 'net.minecraft.world.item.CreativeModeTabs'],'official-creative-targets')
    methods={}
    lines=disasm.splitlines()
    for name in ('generateEnchantmentBookTypesOnlyMaxLevel','generateEnchantmentBookTypesAllLevels'):
        starts=[i for i,l in enumerate(lines) if re.search(r'\b'+name+r'\(',l)]
        need(len(starts)==1,'Missing/ambiguous client target '+name)
        a=starts[0]; b=next((i for i in range(a+1,len(lines)) if re.match(r'^  (?:public|private|protected|static) ',lines[i])),len(lines))
        body='\n'.join(lines[a:b])
        needle='InterfaceMethod net/minecraft/core/HolderLookup.listElements:()Ljava/util/stream/Stream;'
        need(body.count(needle)==1,'Redirect target count changed: '+name)
        methods[name]={'matching_invocations':1,'method':lines[a].strip()}
    loader=json.loads(download('https://maven.fabricmc.net/net/fabricmc/fabric-loader/0.19.3/fabric-loader-0.19.3.json',1_000_000))
    mixins=[e for group in loader['libraries'].values() if isinstance(group,list) for e in group if 'sponge-mixin' in e.get('name','')]
    need(len(mixins)==1,'Ambiguous Fabric Mixin')
    entry=mixins[0]; group,artifact,ver=entry['name'].split(':')
    url='https://maven.fabricmc.net/'+group.replace('.','/')+'/'+artifact+'/'+ver+'/'+artifact+'-'+ver+'.jar'
    mixin=work/'sponge-mixin.jar'; mixin.write_bytes(download(url,20_000_000))
    cp=os.pathsep.join([str(client),str(mixin)]+[str(p) for p in sorted(libs.glob('*.jar'))])
    server_cp=os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')))
    source=ROOT/'client/neverland-enchantment-ui/src'
    exact={'CreativeBookMixin.java':'9c9e44cba8fd446e6e353e417289ca9038bd2ebd','EnchantmentVisibility.java':'74bd893d444c736adad06e7dbdd198a85421f4a2'}
    sources=[]
    for name,required in exact.items():
        paths=list(source.rglob(name)); need(len(paths)==1,'Missing own source '+name)
        raw=paths[0].read_bytes(); blob=hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()
        need(blob==required,'Unreviewed client source '+name); sources.append(str(paths[0]))
    classes=work/'classes'; classes.mkdir()
    run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes)]+sources,'client-compile')
    ru=pack_report['translations']; en={TECH_KEY:'Internal controller (not a survival enchantment)'}
    locales={'assets/minecraft/lang/ru_ru.json':jbytes(ru),'assets/minecraft/lang/en_us.json':jbytes(en)}
    metadata={'pack':{'description':'NeverLand: названия зачарований, Minecraft 26.2','min_format':[88,0],'max_format':[88,0]}}
    rp=archive_bytes({'pack.mcmeta':jbytes(metadata)}|locales)
    need(rp==archive_bytes({'pack.mcmeta':jbytes(metadata)}|locales),'Resource pack not reproducible')
    (out/'NeverLand-Enchantments-RU-26.2-R39.12.zip').write_bytes(rp)
    mod={'schemaVersion':1,'id':'neverland_enchantment_ui','version':'0.2.0-r3912','name':'NeverLand Enchantment UI',
         'environment':'client','description':'Hide technical Nova controller books only in creative listings; retain gameplay enchantments and all registry entries.',
         'mixins':['neverland-enchantment-ui.mixins.json'],'depends':{'fabricloader':'>=0.19.3','minecraft':'26.2','java':'>=25'}}
    mixin_json={'required':True,'minVersion':'0.8','package':'cc.neverland.client','compatibilityLevel':'JAVA_25','client':['CreativeBookMixin'],'injectors':{'defaultRequire':1}}
    own={p.relative_to(classes).as_posix():p.read_bytes() for p in classes.rglob('*.class')}
    need(set(own)=={'cc/neverland/client/EnchantmentVisibility.class','cc/neverland/client/CreativeBookMixin.class'},'Unexpected output classes')
    need(all(int.from_bytes(v[6:8],'big')==69 for v in own.values()),'Wrong classfile version')
    contents=own|locales|{'fabric.mod.json':jbytes(mod),'neverland-enchantment-ui.mixins.json':jbytes(mixin_json)}
    jar=archive_bytes(contents); need(jar==archive_bytes(contents),'Mod packaging not reproducible')
    (out/'NeverLand-Enchantment-UI-Fabric-26.2-R39.12.jar').write_bytes(jar)
    plugin=work/'plugin'; plugin.mkdir()
    run(['javac','--release','25','-proc:none','-classpath',str(classes)+os.pathsep+server_cp,'-d',str(plugin),str(ROOT/'qa/field-r3912/R3912EnchantmentQa.java')],'registry-plugin-compile')
    plugin_entries={p.relative_to(plugin).as_posix():p.read_bytes() for p in plugin.rglob('*.class')}
    plugin_entries['cc/neverland/client/EnchantmentVisibility.class']=own['cc/neverland/client/EnchantmentVisibility.class']
    plugin_entries['expected.json']=jbytes(expected)
    plugin_entries['plugin.yml']=b'name: R3912EnchantmentQa\nversion: 1\nmain: R3912EnchantmentQa\napi-version: \'26.2\'\nfolia-supported: true\n'
    (work/'R3912EnchantmentQa.jar').write_bytes(archive_bytes(plugin_entries))
    shutil.copyfile(base,work/'server.jar'); shutil.copyfile(pack,work/'NeverOverworld.zip')
    nether=unique(args.inputs,'NeverNether.zip','5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10')
    shutil.copyfile(nether,work/'NeverNether.zip')
    report={'compile_pass':True,'client_launch_tested':False,'mixin_transform_executed':False,
            'official_client_sha1':client_meta['sha1'],'official_client_sha256':digest(client_raw),
            'resource_format':resource,'mixin_coordinate':entry['name'],'mixin_sha256':sha(mixin),
            'redirect_targets':methods,'technical_entries':16,'gameplay_entries':17,'locale_keys':len(ru),
            'server_input_sha256':BASE,'pack_sha256':PACK,'server_unchanged':sha(base)==original_base,
            'datapack_unchanged':sha(pack)==original_pack,'output_sha256':{p.name:sha(p) for p in out.iterdir() if p.suffix in ('.jar','.zip')},
            'scope':'Client files only; NOT a worldgen patch. Predicate runtime is tested separately, Mixin launch remains manual.'}
    need(report['server_unchanged'] and report['datapack_unchanged'],'Input was changed')
    save(out/'build.json',report); print('R3912_BUILD '+json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__': main()
