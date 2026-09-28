#!/usr/bin/env python3
"""Consolidated resource repair. Missing variants use explicitly reviewed complete
family templates; no empty-room placeholders or deletion of weighted choices.
Every substitution and unchanged input is retained in the report.
"""
from pathlib import Path
import copy,hashlib,importlib.util,io,json,sys,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'r41-final-evidence';OUT.mkdir(exist_ok=True)
SOURCE='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
FINGERPRINTS=('neveroverworld-worldgen-fingerprint.json','data/neverfolia/neveroverworld/worldgen_fingerprint.json')
def need(ok,msg):
    if not ok:raise ValueError(msg)
def load(p,n):
    s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
def sha(b):return hashlib.sha256(b).hexdigest()
def readzip(p):
    with zipfile.ZipFile(p) as z:
        need(len(z.namelist())==len(set(z.namelist())) and z.testzip() is None,'Bad ZIP')
        return {n:z.read(n) for n in z.namelist() if not n.endswith('/')}
def writezip(p,files):
    need(not p.exists(),'Output exists')
    with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,b in sorted(files.items()):
            info=zipfile.ZipInfo(n,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,b,compresslevel=9)
    need(readzip(p)==files,'ZIP round trip mismatch')
def plain(tag):
    t,v=tag
    if t==10:return {k:plain(x) for k,x in v.items()}
    if t==9:return [plain((v[0],x)) for x in v[1]]
    return v

def main():
    pack=ROOT/'core/NeverOverworld.zip';jar=ROOT/'core/server.jar';need(sha(pack.read_bytes())==SOURCE,'Wrong input pack')
    c=load(ROOT/'qa/field-r394/build_candidate.py','r41carts');fp=load(ROOT/'scripts/fingerprint-never-overworld-pack.py','r41fp');a=load(ROOT/'scripts/audit-neveroverworld-r39-resources.py','r41audit');nbt=load(ROOT/'scripts/build-never-overworld-external-structures-r19.py','r41nbt')
    original=readzip(pack);cart=ROOT/'r41-cart.zip';cr=c.build(pack,cart);(OUT/'cart-reconstruction.json').write_text(json.dumps(cr,indent=2))
    files=readzip(cart);effect=files.copy()
    with zipfile.ZipFile(jar) as z:engine=z.read(next(n for n in z.namelist() if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')))
    vanilla=readzip(io.BytesIO(engine));effect={**vanilla,**files}
    ids={n.split('/')[1]+':'+n.split('/structure/',1)[1][:-4]:n for n in effect if n.startswith('data/') and '/structure/' in n and n.endswith('.nbt')}
    before=a.audit_files(jar,cart);mapping={};substitutions=[];unhandled=[]
    reviewed={
      'intact_horizontal_wall_stairs_5':'intact_horizontal_wall_stairs_4',
      'jungle_village_path5':'jungle_village_path2',
      'swamp_village_big_house1':'swamp_village_house1','swamp_village_big_house2':'swamp_village_house2',
      'swamp_village_path5':'swamp_village_path2',
      'badlands_village_path_t_curve_big':'badlands_village_path_t_curve_large',
      'bunker_hallway_21':'bunker_hallway_2',
      'catacomb_path_2_1':'catacomb_path_snake_2_1','catacomb_path_2_2':'catacomb_path_snake_2_2',
      'desert_temple_main':'desert_temple_main_start',
      'illager_mansion_path_short_sb':'illager_mansion_path_short_srb',
      'deko_furnace_shelf':'deko_smelting','deko_mirror_furnace_shelf':'deko_mirror_smelting',
      'pale_residence_main_4_big':'pale_residence_main_e_big','pale_residence_main_4_medium':'pale_residence_main_e_medium','pale_residence_main_4_small':'pale_residence_main_e_small',
      'pale_residence_house_8':'pale_residence_house_7',
      'remnant_creeper_homestead_connect':'remnant_creeper_homestead',
      'ruin_house_small_5':'ruin_house_small_4','ruin_tower_house_5':'ruin_tower_house_4',
      'stray_fort_path_t-cross':'stray_fort_path_t-cross_small',
      'toxic_small_room_6':'toxic_small_room_5',
    }
    for row in before['missing']:
        id=row['id'];need(row['kind']=='template','Non-template unresolved '+id)
        if id=='minecraft:minecraft/empty':continue
        base=id.rsplit('/',1)[-1];namespace=id.split(':',1)[0];target=None;reason='canonical path correction'
        exact=[v for v in ids if v.split(':',1)[0]==namespace and v.rsplit('/',1)[-1]==base]
        if len(exact)==1:target=exact[0]
        if target is None and 'deko_mirror_center_' in base:
            proposal=id.replace('deko_mirror_center_','deko_center_')
            if proposal in ids:target=proposal;reason='complete connector-compatible center variant; mirrored art unavailable, not claimed restored'
        if target is None:
            new=reviewed.get(base)
            if new:
                values=[v for v in ids if v.split(':',1)[0]==namespace and v.rsplit('/',1)[-1]==new]
                if len(values)==1:target=values[0];reason='reviewed complete family variant / corrected author naming; not fabricated original'
        if target is None:
            proposal=id.replace('/funiture/','/furniture/')
            if proposal in ids:target=proposal
        if target is None:unhandled.append(row);continue
        root=nbt._nbt_parse(effect[ids[target]])[2];need(bool(root.get('blocks',(9,(10,[])))[1][1]),'Empty replacement forbidden '+target)
        meta={'from':id,'to':target,'reason':reason,'source_sha256':sha(effect[ids[target]]),'size':root['size'][1][1], 'direct_entities':len(root.get('entities',(9,(10,[])))[1][1]),'jigsaws':[]}
        for block in root['blocks'][1][1]:
            be=block.get('nbt',(10,{}))[1]
            if be.get('id')==(8,'minecraft:jigsaw'):meta['jigsaws'].append({k:plain(be[k]) for k in ('name','target','pool') if k in be})
        mapping[id]=target;substitutions.append(meta)
    if unhandled:
        (OUT/'unhandled.json').write_text(json.dumps(unhandled,indent=2));print('UNHANDLED',json.dumps([x['id'] for x in unhandled]),flush=True);raise ValueError('Unreviewed missing templates: no automatic fuzzy replacement')
    loot={n.split('/')[1]+':'+n.split('/loot_table/',1)[1][:-5]:n for n in effect if n.startswith('data/') and '/loot_table/' in n and n.endswith('.json')}
    loot_map={
      'nova_structures:equipment/desert_mobs/shrine_weapons':'nova_structures:equipment/desert_mobs/shrine/shrine_weapons',
      'nova_structures:equipment/lone_citadel/spiderqueen':'nova_structures:equipment/illager_mobs/lone_citadel/spiderqueen',
      'nova_structures:spawner_projectile/nether_keep/projectiles_nether_port':'nova_structures:spawner_projectile/nether_keep/projectiles_port',
      'nova_structures:chests/shrine':'nova_structures:chests/shrine/shrine',
    }
    for x,y in loot_map.items():need(y in loot,'Unknown reviewed loot '+y)
    changes=[];empty=0;loot_changes=[];renamed_counts=[]
    def fix(v,source,path=()):
        nonlocal empty
        if isinstance(v,dict):
            if v.get('location')=='minecraft:minecraft/empty':
                need(v.get('element_type') in ('minecraft:single_pool_element','minecraft:legacy_single_pool_element'),'Unexpected empty schema')
                old=copy.deepcopy(v);v.clear();v['element_type']='minecraft:empty_pool_element';empty+=1;changes.append({'source':source,'path':list(path),'before':old,'after':v.copy()});return
            for k,value in list(v.items()):
                if k=='location' and isinstance(value,str) and value in mapping:
                    v[k]=mapping[value];changes.append({'source':source,'path':list(path)+( [k]),'before':value,'after':v[k]})
                if isinstance(value,str) and value in loot_map and k in ('loot_table','name','LootTable','DeathLootTable','items_to_drop_when_ominous','data'):
                    v[k]=loot_map[value];loot_changes.append({'source':source,'path':list(path)+[k],'before':value,'after':v[k]})
                if value=='nova_structures:toxic_lair/boss_slime' and k=='data':
                    v[k]='nova_structures:chests/'+('ominous_trial_chambers' if '/ominous.json' in source else 'trial_chambers')+'/toxic_lair/boss/slime'
                    need(v[k] in loot,'Missing actual slime reward');loot_changes.append({'source':source,'before':value,'after':v[k]})
                if value=='nova_structures:chests/nether_port_blaze_loot' and k=='data':
                    candidates=[x for x in loot if 'blaze' in x and ('nether_port' in x or 'nether_keep' in x)]
                    filtered=[x for x in candidates if ('ominous' in x)==('/ominous.json' in source)]
                    need(len(filtered)==1,'Ambiguous blaze loot '+repr(candidates));v[k]=filtered[0];loot_changes.append({'source':source,'before':value,'after':v[k]})
                fix(v[k],source,path+(k,))
            # Explicit modern item count schema only; leave unrelated entity Count fields alone.
            if isinstance(v.get('id'),str) and 'Count' in v and isinstance(v['Count'],int) and ('components' in v or set(v).issubset({'id','Count','tag'})):
                need('count' not in v,'Conflicting item counts');v['count']=v.pop('Count');renamed_counts.append({'source':source,'path':list(path)})
        elif isinstance(v,list):
            for i,x in enumerate(v):fix(x,source,path+(i,))
    for name,raw in list(files.items()):
        if name.startswith('data/') and name.endswith('.json'):
            doc=json.loads(raw);before_doc=copy.deepcopy(doc);fix(doc,name)
            if doc!=before_doc:files[name]=(json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode()
    need(empty==2,'Terminal empty fix did not match two intended entries')
    fpdoc=fp.fingerprint_document(files)
    for name in FINGERPRINTS:files[name]=(json.dumps(fpdoc,ensure_ascii=False,indent=2)+'\n').encode()
    out=ROOT/'NeverOverworld-R41.zip';writezip(out,files)
    after=a.audit_files(jar,out);(OUT/'resource-after.json').write_text(json.dumps(after,indent=2));(OUT/'resource-before.json').write_text(json.dumps(before,indent=2))
    report={'pass':not after['missing'],'source_sha256':SOURCE,'pack_sha256':sha(out.read_bytes()),'reconstructed_cart_templates':22,'substitutions':substitutions,'reference_changes':changes,'loot_changes':loot_changes,'item_count_schema_changes':renamed_counts,'counts_before':before['counts'],'counts_after':after['counts'],'original_files_preserved':sum(files.get(n)==b for n,b in original.items()),'original_files_changed':[n for n,b in original.items() if files.get(n)!=b],'added_files':[n for n in files if n not in original],'all_bugs_fixed':False,'limits':['Some absent author variants deliberately reuse complete same-family models, not original mirrored/unique art.','Graph closure does not prove every geometric placement, player combat or global ocean closure.']}
    (OUT/'pack-repair.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('R41_PACK',json.dumps({k:v for k,v in report.items() if k in ('pass','pack_sha256','counts_after','item_count_schema_changes')}),flush=True)
    need(report['pass'],'Newly reached unresolved references remain: '+repr(after['missing']))
    need(sha(pack.read_bytes())==SOURCE,'Input mutated')
if __name__=='__main__':main()
