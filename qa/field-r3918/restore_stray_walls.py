#!/usr/bin/env python3
"""Recover exact historical authored NBT models, never approximate aliases.
The old data version is retained for Minecraft's own forward data fixer.
Only absent reviewed IDs are added. Current pools/weights/roots stay unchanged,
except the separately verified two mansion identifier corrections.
"""
from pathlib import Path
from urllib.parse import urlparse
import json,urllib.request
import mansion_reference as fix
s=fix.s;ROOT=fix.ROOT
AUTHOR_URL='https://cdn.modrinth.com/data/tpehi7ww/versions/8o3mS993/Dungeons%20and%20Taverns%20v4.5.zip'
AUTHOR_SHA='c48fd3ddf4999cdaa7513e8ea676b5c8f527ae1f28a0e4a72ad0272502c69979'
AUTHOR_SIZE=14032193
V6_URL='https://cdn.modrinth.com/data/tpehi7ww/versions/bipfLkEE/Dungeons%20and%20Taverns%20v6.0.1.zip'
V6_SHA='78baaa07653eb618be42da7a7fb705b14c72f72351061b5190d635c3c0493345'
V6_SIZE=21700737
PREFIX='data/nova_structures/structure/stray_fort/'
FUTURE_MODELS={
    'nova_structures:illager_hideout/illager_hideout_path_short_sb':'3167defa36170b1f09a074caf7d892f62c8be9c4bcd52b81fdd253727330e3a2',
    'nova_structures:ruin_town/ruin_town_house_small_5':'28b06ea03d05916484a9fe980c169662bf368a8f9688e9739de2b5645ecec228',
    'nova_structures:ruin_town/ruin_town_tower_house_5':'b0b4a0a1344a7150862547bdc5e57f92ec0618c5d1732c2bd4d1799c1a44df29',
    'nova_structures:stray_fort/road/stray_fort_path_t-cross':'fdc060d1b28add786a5be07ad95fdb701ba11dfb96cc81b32d7156d762e7e5ba',
    'nova_structures:toxic_lair/funiture/toxic_surface_deco_2_r':'549e24bbb5d8c4df6c61905274e7229a3948edd8f6cede03dfadf30cb9f8a8f7',
}
MODELS=tuple(sorted('stray_fort_wall_'+part+str(i) for part in ('','back_','back_left_','back_right_','front_','front_left_','front_right_','gate_','gate_back_','gate_front_','gate_short_','short_') for i in (1,2,3)))
# These exact v4.5 templates are the one-hop children exposed by the restored
# wall jigsaws. They were not reachable in the broken pack, so the earlier
# resource audit could not report them until the walls were restored.
CLOSURE_MODELS=tuple(
    [f'stray_fort_event_{i}' for i in range(1,16)]
    + [f'stray_fort_event_{i}b' for i in range(1,16) if i != 13]
    + [f'stray_fort_path_{i}' for i in range(1,5)]
)
EVENT_POOL='data/nova_structures/worldgen/template_pool/stray_fort_event.json'
DANGLING_EVENT='nova_structures:stray_fort/stray_fort_event_13b'
ANCIENT_POOL='data/minecraft/worldgen/template_pool/ancient_city/walls/no_corners.json'
PALE_POOL='data/nova_structures/worldgen/template_pool/pale_residence/decor_inside.json'
PALE_FEATURE_PREFIXES=('data/nova_structures/worldgen/configured_feature/pale_',
                       'data/nova_structures/worldgen/placed_feature/pale_')
ANCIENT_MISSING='minecraft:ancient_city/walls/intact_horizontal_wall_stairs_5'
ANCIENT_LOCATIONS=(
    'minecraft:ancient_city/walls/intact_horizontal_wall_1',
    'minecraft:ancient_city/walls/intact_horizontal_wall_2',
    'minecraft:ancient_city/walls/intact_horizontal_wall_stairs_1',
    'minecraft:ancient_city/walls/intact_horizontal_wall_stairs_2',
    'minecraft:ancient_city/walls/intact_horizontal_wall_stairs_3',
    'minecraft:ancient_city/walls/intact_horizontal_wall_stairs_4',
    ANCIENT_MISSING,
    'minecraft:ancient_city/walls/intact_horizontal_wall_bridge',
)
# Exact resource IDs referenced by the current source pools but absent from all
# reviewed official source releases. These entries can never resolve at runtime.
# Do not add IDs here unless the historical inventory proves the absence.
EMPTY_COMPAT_POOLS={
    'data/structory_towers/worldgen/template_pool/random_pillager_book.json':{
        'structory_towers:book/pillager_1',
        'structory_towers:book/pillager_2',
        'structory_towers:book/pillager_3',
    },
}
PROVEN_DANGLING={
    'minecraft:village_jungle/jungle_village_path5',
    'minecraft:village_swamp/swamp_village_big_house1',
    'minecraft:village_swamp/swamp_village_big_house2',
    'minecraft:village_swamp/swamp_village_path5',
    'nova_structures:badlands_miner_outpost/badlands_miner_outpost_path_t_curve_big',
    'nova_structures:bunker/bunker_underground_hallway_21',
    'nova_structures:catacomb/hallway/catacomb_path_2_1',
    'nova_structures:catacomb/hallway/catacomb_path_2_2',
    'nova_structures:desert_ruin/temple/desert_ruins_temple_main',
    'nova_structures:lone_citadel/room_content/deko_furnace_shelf',
    'nova_structures:lone_citadel/room_content/deko_mirror_center_bed',
    'nova_structures:lone_citadel/room_content/deko_mirror_center_books',
    'nova_structures:lone_citadel/room_content/deko_mirror_center_crafter',
    'nova_structures:lone_citadel/room_content/deko_mirror_center_golem',
    'nova_structures:lone_citadel/room_content/deko_mirror_center_group_table',
    'nova_structures:lone_citadel/room_content/deko_mirror_center_office',
    'nova_structures:lone_citadel/room_content/deko_mirror_center_smoker',
    'nova_structures:lone_citadel/room_content/deko_mirror_center_table',
    'nova_structures:lone_citadel/room_content/deko_mirror_center_vault',
    'nova_structures:lone_citadel/room_content/deko_mirror_furnace_shelf',
    'nova_structures:pale_residence/residence/pale_residence_main_4_big',
    'nova_structures:pale_residence/residence/pale_residence_main_4_medium',
    'nova_structures:pale_residence/residence/pale_residence_main_4_small',
    'nova_structures:pale_residence/village/house/pale_house_8',
    'nova_structures:remnant/remnant_creeper_homestead_connect',
    'nova_structures:toxic_lair/room/small_room_6',
    'nova_structures:toxic_lair/spawner/spawner_boss_slime',
    'structory_towers:book/pillager_1',
    'structory_towers:book/pillager_2',
    'structory_towers:book/pillager_3',
}

def pinned_download(url,size,expected):
    req=urllib.request.Request(url,headers={'User-Agent':'NeverFolia-resource-recovery/1.0'})
    with urllib.request.urlopen(req,timeout=60) as r:
        s.need(urlparse(r.url).scheme=='https' and urlparse(r.url).hostname=='cdn.modrinth.com','Unexpected author redirect')
        raw=r.read(size+1)
    s.need(len(raw)==size and s.sha(raw)==expected,'Wrong exact historical author archive')
    return raw

def author_bytes():return pinned_download(AUTHOR_URL,AUTHOR_SIZE,AUTHOR_SHA)
def author_v6_bytes():return pinned_download(V6_URL,V6_SIZE,V6_SHA)

def foreign_ids(value):
    if isinstance(value,dict):
        return sum(foreign_ids(v) for v in value.values())
    if isinstance(value,(tuple,list)):
        return sum(foreign_ids(v) for v in value)
    return int(isinstance(value,str) and value.startswith('porting_lib:'))

def install_ancient_city_pool_override(files, missing):
    s.need(('template',ANCIENT_MISSING) in missing,'Pinned vanilla ancient-city gap no longer present')
    s.need(ANCIENT_POOL not in files,'NeverOverworld unexpectedly already overrides vanilla ancient-city pool')
    def entry(location):
        return {'element':{'element_type':'minecraft:single_pool_element','location':location,
                           'processors':'minecraft:ancient_city_walls_degradation','projection':'rigid'},
                'weight':1}
    source={'elements':[entry(x) for x in ANCIENT_LOCATIONS],'fallback':'minecraft:empty'}
    fixed={'elements':[entry(x) for x in ANCIENT_LOCATIONS if x!=ANCIENT_MISSING],'fallback':'minecraft:empty'}
    s.need(len(source['elements'])==8 and len(fixed['elements'])==7,'Ancient city compatibility contract changed')
    payload=(json.dumps(fixed,indent=2,ensure_ascii=False)+'\n').encode()
    files[ANCIENT_POOL]=payload
    return {'path':ANCIENT_POOL,'removed_location':ANCIENT_MISSING,'removed_weight':1,
            'source_variants':8,'remaining_variants':7,'output_sha256':s.sha(payload),
            'pinned_server_sha256':fix.CORE}

def prune_dangling_pool_elements(files, missing):
    targets=PROVEN_DANGLING & {ident for kind,ident in missing if kind=='template'}
    changed=[];removed=set()
    def prune(node,path):
        nonlocal changed,removed
        if isinstance(node,list):
            out=[]
            for index,item in enumerate(node):
                # Weighted template-pool entry: remove only a reviewed exact
                # single/legacy pool element whose location is unresolved.
                element=item.get('element') if isinstance(item,dict) else None
                location=element.get('location') if isinstance(element,dict) else None
                etype=element.get('element_type') if isinstance(element,dict) else None
                if (etype in ('minecraft:single_pool_element','minecraft:legacy_single_pool_element')
                        and location in targets):
                    weight=item.get('weight')
                    s.need(type(weight) is int and weight>0,'Invalid dangling element weight')
                    removed.add(location)
                    changed.append({'json_path':path+[index],'location':location,'weight':weight})
                    continue
                out.append(prune(item,path+[index]))
            return out
        if isinstance(node,dict):
            return {k:prune(v,path+[k]) for k,v in node.items()}
        return node
    touched={}
    for path,payload in list(files.items()):
        if '/worldgen/template_pool/' not in path or not path.endswith('.json'):continue
        original=json.loads(payload)
        updated=prune(original,[path])
        if updated==original:continue
        elements=updated.get('elements')
        positive=[e for e in elements or [] if isinstance(e,dict) and type(e.get('weight')) is int and e.get('weight')>0]
        compatibility_empty=False
        if not positive:
            allowed=EMPTY_COMPAT_POOLS.get(path)
            original_ids={
                e.get('element',{}).get('location') for e in original.get('elements',[])
                if isinstance(e,dict) and isinstance(e.get('element'),dict)
                and e['element'].get('element_type') in ('minecraft:single_pool_element','minecraft:legacy_single_pool_element')
            }
            s.need(allowed is not None and original_ids==allowed and allowed <= targets,
                   'Dangling repair would empty non-cosmetic template pool '+path)
            updated['elements']=[{'weight':1,'element':{'element_type':'minecraft:empty_pool_element'}}]
            elements=updated['elements'];positive=elements;compatibility_empty=True
        encoded=(json.dumps(updated,indent=2,ensure_ascii=False)+'\n').encode()
        files[path]=encoded
        touched[path]={'source_sha256':s.sha(payload),'output_sha256':s.sha(encoded),
                       'remaining_positive_entries':len(positive),'compatibility_empty':compatibility_empty}
    s.need(removed==targets,'Not every proven dangling template reference was removed: '+repr(sorted(targets-removed)))
    return {'targets':sorted(targets),'removed':changed,'pools':touched}

def install_pale_decor_recovery(files,source):
    """Restore the exact authored Pale Residence decor contract from pinned D&T v4.5.

    D&T 5.3.2/6.0.1 retain NBT jigsaws targeting decor_inside but omit the pool and
    its feature family.  The pinned v4.5 archive contains the original pool plus the
    complete namespaced pale_* configured/placed feature family, so these resources
    are copied byte-for-byte rather than reconstructed.
    """
    s.need(PALE_POOL in source,'Pinned v4.5 Pale decor pool disappeared')
    authored=json.loads(source[PALE_POOL])
    expected_features={'nova_structures:pale_moss_small','nova_structures:pale_moss_floor'}
    actual_features={e.get('element',{}).get('feature') for e in authored.get('elements',[])
                     if isinstance(e,dict) and isinstance(e.get('element'),dict)
                     and e['element'].get('element_type')=='minecraft:feature_pool_element'}
    s.need(actual_features==expected_features,'Pinned Pale decor pool contract changed')
    s.need(authored.get('fallback')=='minecraft:empty','Pinned Pale decor fallback changed')
    prior=files.get(PALE_POOL)
    if prior is not None:
        prior_obj=json.loads(prior)
        compat={'fallback':'minecraft:empty','elements':[{'element':{'element_type':'minecraft:empty_pool_element'},'weight':1}]}
        s.need(prior_obj==compat or prior==source[PALE_POOL],'Unexpected current Pale decor pool')
    files[PALE_POOL]=source[PALE_POOL]

    family=sorted(path for path in source
                  if path.endswith('.json') and path.startswith(PALE_FEATURE_PREFIXES))
    s.need(bool(family),'Pinned v4.5 Pale feature family disappeared')
    added=[];identical=[]
    for path in family:
        if path in files:
            s.need(files[path]==source[path],'Current Pale feature differs from pinned authored resource: '+path)
            identical.append(path)
        else:
            files[path]=source[path];added.append(path)
    return {'pool_path':PALE_POOL,'pool_source_sha256':s.sha(source[PALE_POOL]),
            'pool_replaced_compatibility_fallback':prior is not None and prior!=source[PALE_POOL],
            'feature_family_count':len(family),'added_feature_paths':added,
            'identical_existing_feature_paths':identical,
            'feature_hashes':{path:s.sha(source[path]) for path in family}}

def sanitize_exact(ext,raw,ident):
    root=ext._nbt_parse(raw)[2]
    before_foreign=foreign_ids(root)
    installed=ext.sanitize_dat_structure_nbt(raw,ident)
    afterroot=ext._nbt_parse(installed)[2]
    after_foreign=foreign_ids(afterroot)
    s.need(after_foreign==0 and before_foreign>=after_foreign,'Foreign attribute sanitizer contract changed')
    s.need(afterroot.get('DataVersion')==root.get('DataVersion'),'DataVersion changed during compatibility sanitation')
    s.need(afterroot.get('size')==root.get('size') and afterroot.get('palette')==root.get('palette')
           and afterroot.get('blocks')==root.get('blocks'),'Authored structure geometry changed')
    return root,installed,before_foreign-after_foreign

def build(base,author,before,author_v6=None):
    s.need(s.sha(base)==fix.BASE and s.sha(author)==AUTHOR_SHA,'Wrong pinned inputs')
    if author_v6 is not None:s.need(s.sha(author_v6)==V6_SHA,'Wrong pinned v6 input')
    s.need(before['inputs']['pack_sha256']==fix.BASE,'Wrong reference audit')
    missing={(x['kind'],x['id']) for x in before['missing']}
    corrected,mansion=fix.build(base);files=s.read_zip(corrected);original=s.read_zip(base);source=s.read_zip(author)
    source_v6=s.read_zip(author_v6) if author_v6 is not None else {}
    ext=s.load('r3918_authored_walls',ROOT/'scripts/build-never-overworld-external-structures-r19.py');rows=[]
    event_pool=json.loads(files[EVENT_POOL])
    before_event=json.loads(json.dumps(event_pool))
    target_rows=[entry for entry in event_pool.get('elements',[])
                 if isinstance(entry,dict) and isinstance(entry.get('element'),dict)
                 and entry['element'].get('location')==DANGLING_EVENT]
    s.need(len(target_rows)==1 and target_rows[0].get('weight')==2,
           'Dangling event_13b source reference no longer matches reviewed upstream')
    event_pool['elements']=[entry for entry in event_pool['elements'] if entry is not target_rows[0]]
    s.need(len(event_pool['elements'])==len(before_event['elements'])-1,'Unexpected Stray Fort event-pool edit')
    files[EVENT_POOL]=(json.dumps(event_pool,indent=2,ensure_ascii=False)+'\n').encode()
    ancient_repair=install_ancient_city_pool_override(files,missing)
    dangling_repair=prune_dangling_pool_elements(files,missing)
    pale_repair=install_pale_decor_recovery(files,source)
    for model in MODELS:
        path=PREFIX+model+'.nbt';ident='nova_structures:stray_fort/'+model
        s.need(('template',ident) in missing and path not in files and path in source,'Unexpected restoration target '+ident)
        raw=source[path];root=ext._nbt_parse(raw)[2]
        version=root.get('DataVersion');s.need(version and version[0]==3 and version[1] in (3578,3688),'Unreviewed authored version')
        size=root['size'][1][1];s.need(len(size)==3 and all(type(x) is int and 0<x<=32 for x in size),'Unexpected wall bounds')
        s.need('palettes' not in root,'Multiple palettes need a separate review')
        palette=root['palette'][1][1];blocks=root['blocks'][1][1];s.need(bool(blocks) and bool(palette),'Empty wall')
        joints=[];nonair=0
        for b in blocks:
            pos=b['pos'][1][1];idx=b['state'][1]
            s.need(len(pos)==3 and all(type(x) is int and 0<=x<d for x,d in zip(pos,size)),'Out-of-bounds source block')
            s.need(type(idx) is int and 0<=idx<len(palette),'Invalid source palette')
            name=palette[idx]['Name'][1]
            if name not in ('minecraft:air','minecraft:cave_air','minecraft:void_air','minecraft:structure_void'):nonair+=1
            if name=='minecraft:jigsaw':joints.append({'pos':pos,'nbt':b.get('nbt')})
        s.need(nonair>100 and joints,'Wall lacks geometry/connectors')
        # This existing sanitizer removes only known foreign PortingLib attributes.
        # No blanket entity removal, no manual DataVersion relabel, no loot edit.
        root,installed,removed=sanitize_exact(ext,raw,ident)
        files[path]=installed
        rows.append({'id':ident,'path':path,'source_sha256':s.sha(raw),'installed_sha256':s.sha(installed),'data_version':version[1],'size':size,'blocks':len(blocks),'nonair':nonair,'jigsaw_count':len(joints),'jigsaws':joints,'foreign_attributes_removed':removed,'byte_identical_to_author':raw==installed})
    s.need(len(rows)==36 and len({r['id'] for r in rows})==36,'Incomplete exact model family')
    closure=[]
    for model in CLOSURE_MODELS:
        path=PREFIX+model+'.nbt';ident='nova_structures:stray_fort/'+model
        s.need(path not in files and path in source,'Missing exact authored closure template '+ident)
        raw=source[path]
        root,installed,removed=sanitize_exact(ext,raw,ident)
        version=root.get('DataVersion')
        s.need(version and version[0]==3 and version[1] in (3578,3688),'Unreviewed closure DataVersion '+ident)
        size=root['size'][1][1]
        s.need(len(size)==3 and all(type(x) is int and 0<x<=128 for x in size),'Unexpected closure bounds '+ident)
        files[path]=installed
        closure.append({'id':ident,'path':path,'source_sha256':s.sha(raw),'installed_sha256':s.sha(installed),
                        'data_version':version[1],'size':size,'foreign_attributes_removed':removed,
                        'byte_identical_to_author':raw==installed})
    s.need(len(closure)==33 and len({r['id'] for r in closure})==33,'Incomplete exact closure family')
    future=[]
    if source_v6:
        for ident,expected_sha in FUTURE_MODELS.items():
            ns,name=ident.split(':',1);path=f'data/{ns}/structure/{name}.nbt'
            s.need(('template',ident) in missing and path not in files and path in source_v6,'Unexpected v6 restoration target '+ident)
            raw=source_v6[path];s.need(s.sha(raw)==expected_sha,'Reviewed v6 model hash changed '+ident)
            root,installed,removed=sanitize_exact(ext,raw,ident)
            version=root.get('DataVersion');s.need(version and version[0]==3 and version[1] in (4082,5003),'Unreviewed v6 DataVersion '+ident)
            size=root['size'][1][1];s.need(len(size)==3 and all(type(x) is int and 0<x<=128 for x in size),'Unexpected v6 model bounds '+ident)
            files[path]=installed
            future.append({'id':ident,'path':path,'source_sha256':expected_sha,'installed_sha256':s.sha(installed),
                           'data_version':version[1],'size':size,'foreign_attributes_removed':removed,
                           'byte_identical_to_author':raw==installed})
        s.need(len(future)==len(FUTURE_MODELS),'Incomplete exact v6 recovery')
    fp=s.load('r3918_wall_fingerprint',ROOT/'scripts/fingerprint-never-overworld-pack.py')
    encoded=(json.dumps(fp.fingerprint_document(files),ensure_ascii=False,indent=2)+'\n').encode()
    for p in s.FP:files[p]=encoded
    pale_added=set(pale_repair['added_feature_paths'])
    if PALE_POOL not in original:pale_added.add(PALE_POOL)
    additions={r['path'] for r in rows}|{r['path'] for r in closure}|{r['path'] for r in future}|{ANCIENT_POOL}|pale_added
    s.need(set(files)-set(original)==additions and not set(original)-set(files),'Unexpected entry delta')
    allowed_changes=(*fix.POOLS,EVENT_POOL,PALE_POOL,*dangling_repair['pools'],*s.FP)
    s.need(all(files[p]==v for p,v in original.items() if p not in allowed_changes),'Unrelated original content changed')
    output=s.write_zip(files);s.need(s.read_zip(output)==files and output==s.write_zip(files),'Nonrepeatable output')
    return output,{'pass':True,'base_sha256':fix.BASE,'source_url':AUTHOR_URL,'source_archive_sha256':AUTHOR_SHA,
                   'output_sha256':s.sha(output),'mansion_repair':mansion,'models':rows,'closure_models':closure,
                   'future_models':future,'v6_source_url':V6_URL if source_v6 else None,'v6_source_sha256':V6_SHA if source_v6 else None,
                   'proven_dangling_repair':dangling_repair,'ancient_city_pool_repair':ancient_repair,
                   'pale_residence_decor_recovery':pale_repair,
                   'stray_event_pool_repair':{'path':EVENT_POOL,'removed_location':DANGLING_EVENT,'removed_weight':2,
                                              'upstream_missing_in_checked_releases':True},
                   'restored_templates':len(rows)+len(closure),'existing_entries_preserved':sum(files[p]==v for p,v in original.items()),
                   'old_pack_installed':False,'all_reported_bugs_fixed':False,'production_accepted':False}
