#!/usr/bin/env python3
"""Assemble the exact R39.23 user test kit only from accepted pinned inputs."""
from __future__ import annotations
from pathlib import Path
import hashlib, json, os, shutil, stat, zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts-r3923'
WORK=ROOT/'.work/r3923'
CORE_SHA='845d0e90fcbe0fbebad7a613aa9934f608cce64a9d41abdfdf012e39e21c1d40'
OW_SHA='9daf27e23300d6687e8cc93cf82c7e6db91f69e4fe605382c6947521f0855590'
NN_SHA='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
CLIENT_MOD_SHA='da556d6f79c53f741f319ca215b09bceb5b74a6b46ac657878ffaca766b9b53d'
CLIENT_RP_SHA='831b4cba0af3bbdad507f1c1c355b5e05a2787560fd990bee30f8c3423d98196'
SEED='-4651369264513492755'

def need(ok,msg):
    if not ok: raise ValueError(msg)

def sha(path:Path)->str:
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def exact(root:Path,name:str,digest:str)->Path:
    hits=[p for p in root.rglob(name) if p.is_file() and sha(p)==digest]
    need(len(hits)==1,f'exact input {name} {digest}: {hits}')
    return hits[0]

def one_json(root:Path,name:str)->dict:
    hits=[p for p in root.rglob(name) if p.is_file()]
    need(len(hits)==1,f'exact report {name}: {hits}')
    return json.loads(hits[0].read_text(encoding='utf-8'))

def write(path:Path,text:str,mode:int|None=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf-8',newline='\n')
    if mode is not None:path.chmod(mode)

def deterministic_zip(folder:Path,out:Path):
    if out.exists():out.unlink()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(folder.rglob('*')):
            if not p.is_file():continue
            rel=p.relative_to(folder.parent).as_posix()
            info=zipfile.ZipInfo(rel,date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=(0o100755 if os.access(p,os.X_OK) else 0o100644)<<16
            z.writestr(info,p.read_bytes())
    with zipfile.ZipFile(out) as z:
        need(z.testzip() is None,'final ZIP CRC failure')
        need(len(z.namelist())==len(set(z.namelist())),'duplicate final ZIP member')

def main():
    need(not WORK.exists(),'R3923 work directory already exists')
    WORK.mkdir(parents=True);OUT.mkdir(exist_ok=True)

    core=exact(ROOT/'core-input','server-r3915.jar',CORE_SHA)
    ow=exact(ROOT/'resource-input','NeverOverworld-R3918-Walls.zip',OW_SHA)
    nn=exact(ROOT/'ice-input','NeverNether.zip',NN_SHA)
    client_mod=exact(ROOT/'client-input','NeverLand-Enchantment-UI-Fabric-26.2-R39.12.jar',CLIENT_MOD_SHA)
    client_rp=exact(ROOT/'client-input','NeverLand-Enchantments-RU-26.2-R39.12.zip',CLIENT_RP_SHA)

    with zipfile.ZipFile(ow) as z:
        need(z.testzip() is None,'NeverOverworld ZIP CRC failure')
        foreign=[n for n in z.namelist() if n.endswith('.nbt') and b'porting_lib:' in z.read(n)]
        need(not foreign,'foreign PortingLib attributes survived in structures: '+repr(foreign[:8]))
        pale='data/nova_structures/worldgen/template_pool/pale_residence/decor_inside.json'
        pale_obj=json.loads(z.read(pale))
        pale_features={e.get('element',{}).get('feature') for e in pale_obj.get('elements',[])
                       if isinstance(e,dict) and isinstance(e.get('element'),dict)
                       and e['element'].get('element_type')=='minecraft:feature_pool_element'}
        need(pale_obj.get('fallback')=='minecraft:empty' and
             pale_features=={'nova_structures:pale_moss_small','nova_structures:pale_moss_floor'},
             'Pale Residence authored decor contract missing')

    resource=one_json(ROOT/'resource-input','walls-result.json')
    mobs=one_json(ROOT/'mob-input','r3921-mobs-summary.json')
    field=one_json(ROOT/'field-input','summary.json')
    need(resource.get('pass') is True,'R3918 resource acceptance failed')
    need(resource.get('all_reported_bugs_fixed') is True,'Resource candidate explicitly reports unresolved bugs')
    need(resource.get('production_accepted') is False,'Resource evidence must remain a test candidate until user acceptance')
    need(resource.get('resource_delta',{}).get('full_resource_acceptance') is True,'R3918 graph not closed')
    after=resource['resource_delta']['after']
    need(after.get('missing_pools')==after.get('missing_templates')==after.get('other_missing')==0,
         'R3918 still has missing jigsaw resources')
    stacks=resource.get('effective_resource_stacks',{})
    need(set(stacks)=={'overworld_then_nether','nether_then_overworld'},
         'R3918 effective two-pack stack evidence missing')
    for label,row in stacks.items():
        counts=row.get('counts',{})
        need(counts.get('missing_pools')==counts.get('missing_templates')==counts.get('other_missing')==0,
             'R3918 effective stack not closed: '+label)
    need(mobs.get('pass') is True and mobs.get('phases')==2 and min(mobs.get('case_counts',[0]))>=14,
         'R3921 mob acceptance failed')
    need(mobs.get('core_sha256')==CORE_SHA and mobs.get('overworld_sha256')==OW_SHA and
         mobs.get('nether_sha256')==NN_SHA,'R3921 tested different binaries')
    need(field.get('pass') is True and field.get('targets')==72,'R3922 72-chunk field acceptance failed')
    need(field.get('candidate_restart_water_hash_equal') is True and
         field.get('candidate_reverse_water_hash_equal') is True,'R3922 persistence/order acceptance failed')
    need(field.get('isolated_air',{}).get('candidate')==0,'R3922 isolated ocean air remains')
    need(field.get('isolated_ice',{}).get('candidate')==0,'R3922 isolated submerged ice remains')
    need(field.get('core_sha256')==CORE_SHA and field.get('overworld_sha256')==OW_SHA and
         field.get('nether_sha256')==NN_SHA,'R3922 tested different binaries')

    kit=WORK/'NeverFolia-R39.23-FullFix-TEST'
    (kit/'world/datapacks').mkdir(parents=True)
    (kit/'client-addon').mkdir()
    shutil.copyfile(core,kit/'server.jar')
    shutil.copyfile(ow,kit/'world/datapacks/NeverOverworld.zip')
    shutil.copyfile(nn,kit/'world/datapacks/NeverNether.zip')
    shutil.copyfile(client_mod,kit/'client-addon'/client_mod.name)
    shutil.copyfile(client_rp,kit/'client-addon'/client_rp.name)

    write(kit/'server.properties',
f"""level-name=world
level-seed={SEED}
initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip
online-mode=false
enforce-secure-profile=false
server-ip=127.0.0.1
server-port=25565
view-distance=6
simulation-distance=4
spawn-protection=0
pause-when-empty-seconds=-1
enable-rcon=false
enable-query=false
""")
    write(kit/'START-LOCAL.bat',
"""@echo off
java -Xms2G -Xmx4G -Dneverfolia.r399OceanClosure=true -Dneverfolia.r3913IceFragments=true -jar server.jar --nogui
pause
""")
    write(kit/'START-LOCAL.sh',
"""#!/usr/bin/env sh
set -eu
exec java -Xms2G -Xmx4G -Dneverfolia.r399OceanClosure=true -Dneverfolia.r3913IceFragments=true -jar server.jar --nogui
""",0o755)
    write(kit/'README-RU.txt',
"""NeverFolia R39.23 FullFix TEST
===============================

Это единый кандидат для твоей локальной ручной проверки Minecraft 26.2 / Java 25.

ВАЖНО:
1. Проверять на НОВОМ тестовом мире. Генерационные исправления воды/льда не переписывают уже сохранённые старые чанки.
2. Перед первым запуском создай eula.txt с eula=true, если принимаешь Minecraft EULA.
3. Запускай START-LOCAL.bat (Windows) или START-LOCAL.sh (Linux).
   Два JVM-флага в этих скриптах обязательны для этого тестового кандидата:
   -Dneverfolia.r399OceanClosure=true
   -Dneverfolia.r3913IceFragments=true
4. NeverOverworld.zip и NeverNether.zip уже лежат в world/datapacks.
5. Для клиентской части:
   - Minecraft 26.2
   - Fabric Loader >= 0.19.3
   - Java 25
   - Fabric API не требуется
   Установи JAR из client-addon/ в клиентские mods.
   ZIP локализации из client-addon/ подключи как resource pack.

Что закрывается этой сборкой:
- воздушные полости/стены воды вокруг островов и в океане;
- сохранение защищённых сухих шахт и построек;
- подводные остатки льда в проверенных проблемных областях;
- 0 отсутствующих достижимых jigsaw pool/template ресурсов после восстановления;
- Stray Fort восстановлен из авторских шаблонов;\n- pale_residence/decor_inside восстановлен из закреплённого авторского D&T v4.5 вместе с исходной pale_* feature-семьёй;
- технические D&T enchant-книги скрываются клиентским дополнением, игровые остаются;
- Swift Soar работает серверно;
- native/Folia-safe активация dungeon mob/jockey сценариев;
- отсутствие целевых console warnings: Empty/non-existent pool, porting_lib,
  Block-attached entity at invalid position, unknown registry key в проверенных прогонах.

Основной seed регрессии:
-4651369264513492755

Если найдёшь дефект, пришли координаты + F3/биом + скриншот и latest.log.
Не переносить этот TEST-комплект в production до твоей ручной проверки.
""")

    members={
      'server.jar':CORE_SHA,
      'world/datapacks/NeverOverworld.zip':OW_SHA,
      'world/datapacks/NeverNether.zip':NN_SHA,
      'client-addon/'+client_mod.name:CLIENT_MOD_SHA,
      'client-addon/'+client_rp.name:CLIENT_RP_SHA,
    }
    sums=''.join(f"{digest}  {name}\n" for name,digest in sorted(members.items()))
    write(kit/'SHA256SUMS.txt',sums)

    acceptance={
      'schema':1,'version':'R39.23','pass':True,'seed':int(SEED),
      'inputs':members,
      'acceptance':{
        'R3918_resource_graph':{
          'pass':True,'missing_pools':after['missing_pools'],
          'missing_templates':after['missing_templates'],'other_missing':after['other_missing']},
        'R3921_dungeon_mobs':mobs,
        'R3922_water_ice_field':{
          'pass':field['pass'],'targets':field['targets'],
          'air_to_water':field.get('air_to_water'),
          'ice_report_files':field.get('ice_report_files'),
          'isolated_air':field.get('isolated_air'),
          'isolated_ice':field.get('isolated_ice'),
          'candidate_restart_water_hash_equal':field['candidate_restart_water_hash_equal'],
          'candidate_reverse_water_hash_equal':field['candidate_reverse_water_hash_equal'],
          'comparisons':field.get('comparisons')}},
      'manual_test_required':True,
      'production_accepted':False,
      'generation_only_note':'Use a new world; already-generated old chunks are not rewritten by the generation-stage repair.'
    }
    write(kit/'ACCEPTANCE.json',json.dumps(acceptance,indent=2,ensure_ascii=False)+'\n')

    out=OUT/'NeverFolia-R39.23-FullFix-TEST.zip'
    deterministic_zip(kit,out)
    report={'pass':True,'version':'R39.23','archive':out.name,'archive_sha256':sha(out),
            'archive_size':out.stat().st_size,'members':members,'acceptance':acceptance['acceptance']}
    write(OUT/'R39.23-package-report.json',json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(report,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
