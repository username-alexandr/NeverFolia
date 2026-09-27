#!/usr/bin/env python3
"""Reproduce the reviewed R39.3 resource candidate from the pinned R38 pack.
Only template-reference locations, two terminal NBT pool strings and fingerprints
change. No missing rooms are fabricated and no saved world or core is modified.
"""
from pathlib import Path
import argparse,collections,copy,gzip,hashlib,io,json,os,tempfile,unittest,zipfile
BASE_PACK='32ea5160f0bed3a80cf400c907622c7dbb76a9bb4160e309cacb5d712a8bd9f7'
OUTPUT_CONTENT='24d1e22d76bc77aa990a1c0e0910e8bbc2ca186be52f4db2a3382ea5b694d7e0'
FINGERPRINTS=('neveroverworld-worldgen-fingerprint.json','data/neverfolia/neveroverworld/worldgen_fingerprint.json')
MAPPINGS={
'nova_structures:bunker/bunker_underground_room_library':'nova_structures:bunker/bunker_underground_library',
'nova_structures:bunker/bunker_underground_room_library_big':'nova_structures:bunker/bunker_underground_library_big',
'nova_structures:catacomb/hallway/catacomb_path_t-crossspecial_1':'nova_structures:catacomb/hallway/catacomb_path_t-cross_special_1',
'nova_structures:cave_chamber/chambers/cave_chamber_crop_farm_1':'nova_structures:cave_chamber/chambers/cave_chamber_crops_farm_1',
'nova_structures:cave_chamber/chambers/cave_chamber_crop_farm_1_roof':'nova_structures:cave_chamber/chambers/cave_chamber_crops_farm_1_roof',
'nova_structures:cave_chamber/chambers/cave_chamber_crop_farm_2':'nova_structures:cave_chamber/chambers/cave_chamber_crops_farm_2',
'nova_structures:cave_chamber/chambers/cave_chamber_crop_farm_2_roof':'nova_structures:cave_chamber/chambers/cave_chamber_crops_farm_2_roof',
'nova_structures:cave_chamber/chambers/cave_chamber_crop_farm_3':'nova_structures:cave_chamber/chambers/cave_chamber_crops_farm_3',
'nova_structures:cave_chamber/chambers/cave_chamber_crop_farm_3_roof':'nova_structures:cave_chamber/chambers/cave_chamber_crops_farm_3_roof',
'nova_structures:conduit_ruin/road/conduit_ruin_road_cruve_1':'nova_structures:conduit_ruin/road/conduit_ruin_road_curve_1',
'nova_structures:conduit_ruin/road/conduit_ruin_road_cruve_2':'nova_structures:conduit_ruin/road/conduit_ruin_road_curve_2',
'nova_structures:creeping_crypt/crypt_spawner/cc_hallawy_azalea':'nova_structures:creeping_crypt/crypt_spawner/cc_hallway_azalea',
'nova_structures:lone_citadel/room_content/deko_cemter_books':'nova_structures:lone_citadel/room_content/deko_center_books',
'nova_structures:lone_citadel/room_content/deko_pffice':'nova_structures:lone_citadel/room_content/deko_office',
'nova_structures:pale_residence/village/deco/pale_deco0':'nova_structures:pale_residence/village/deco/pale_deco_0',
'nova_structures:stray_fort/funiture/stray_fort_funiture_pahntom_goetze_1':'nova_structures:stray_fort/funiture/stray_fort_funiture_phantom_goetze_1',
'nova_structures:stray_fort/funiture/stray_fort_funiture_pahntom_goetze_2':'nova_structures:stray_fort/funiture/stray_fort_funiture_phantom_goetze_2',
'nova_structures:stray_fort/funiture/stray_fort_funiture_pahntom_goetze_3':'nova_structures:stray_fort/funiture/stray_fort_funiture_phantom_goetze_3',
'nova_structures:stray_fort/house/fort_village_house_10_ruin':'nova_structures:stray_fort/house/fort_village_house_10_ruins',
'nova_structures:toxic_lair/funiture/toxic_surface_deco_bonfire':'nova_structures:toxic_lair/funiture/toxic_surface_deco_bornfire',
'nova_structures:trident_trials_monument/small_monument/room_parts/small_monument_oof_wall4':'nova_structures:trident_trials_monument/small_monument/room_parts/small_monument_roof_wall4',
'nova_structures:village/birch/birch_shepert':'nova_structures:village/birch/birch_shephert',
'nova_structures:shrine/shrine_combat/combat_shrine/rooms/shrine_combat_room_size2_t_cross_a':'nova_structures:shrine/shrine_combat/combat_shrine/rooms/shrine_combat_room_size2_t_curve_a',
'nova_structures:shrine/shrine_combat/combat_shrine/rooms/shrine_combat_room_size2_t_cross_b':'nova_structures:shrine/shrine_combat/combat_shrine/rooms/shrine_combat_room_size2_t_curve_b',
'nova_structures:shrine/shrine_combat/combat_shrine/rooms/shrine_combat_room_size2_t_cross_c':'nova_structures:shrine/shrine_combat/combat_shrine/rooms/shrine_combat_room_size2_t_curve_c',
'nova_structures:shrine/shrine_six/room/shrine_6_room_size2_t_cross':'nova_structures:shrine/shrine_six/room/shrine_6_room_size2_t_curve',
'nova_structures:shrine/shrine_six/spawner/shrine_v6_spawner_bogged_parched':'nova_structures:shrine/shrine_six/spawner/shrine_v6_spawner_parched_random',
'minecraft:illager_mansion/mansion_house_2library_left_1':'minecraft:illager_mansion/mansion_house_library_left_1',
'minecraft:illager_mansion/mansion_house_2library_left_2':'minecraft:illager_mansion/mansion_house_library_left_2',
'nova_structures:creeping_crypt/crypt_rooms/cc_small_hallway_1':'nova_structures:creeping_crypt/crypt_rooms/cc_small_hallway',
'nova_structures:pale_residence/village/road/pale_path_small_t_cross':'nova_structures:pale_residence/village/road/pale_path_small_t_cross_1',
'nova_structures:illager_barracks/features/small_wargon':'nova_structures:illager_barracks/features/small_wargon_1',
'nova_structures:lone_citadel/room_content/deko_barrel':'nova_structures:lone_citadel/room_content/deko_barrels',
}
for biome in ('acacia','birch','cherry','dark_oak','desert','jungle','mangrove','oak','pale','snowy','spruce','swamp'):
    MAPPINGS['nova_structures:tavern/tavern_event_bench_'+biome]='nova_structures:tavern/tavern_event_bench_table_'+biome
COUNTS={key:1 for key in MAPPINGS}
COUNTS.update({
'nova_structures:catacomb/hallway/catacomb_path_t-crossspecial_1':3,
'nova_structures:cave_chamber/chambers/cave_chamber_crop_farm_1':2,
'nova_structures:cave_chamber/chambers/cave_chamber_crop_farm_2':2,
'nova_structures:cave_chamber/chambers/cave_chamber_crop_farm_3':2,
'minecraft:illager_mansion/mansion_house_2library_left_1':2,
'nova_structures:pale_residence/village/road/pale_path_small_t_cross':2,
'nova_structures:illager_barracks/features/small_wargon':2})
NBT_INPUTS={
'data/nova_structures/structure/conduit_ruin/house/conduit_ruin_house_b_3.nbt':'a908a81101900894dc9c4900f694f267335bc3b569f7179a3e1ca05a3afc22a1',
'data/nova_structures/structure/conduit_ruin/house/conduit_ruin_house_b_4.nbt':'4a26dd29914e99b6efe3d8acf6ae20f5b7182c00bf6362ae6cffad44b16cf7d5'}

def sha(data):return hashlib.sha256(data).hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)

def content_digest(entries):
    h=hashlib.sha256()
    for path in sorted(entries):
        if path in FINGERPRINTS:continue
        name=path.encode();raw=entries[path]
        h.update(len(name).to_bytes(4,'big'));h.update(name)
        h.update(len(raw).to_bytes(8,'big'));h.update(raw)
    return h.hexdigest()

def json_rewrite(raw,mappings):
    obj=json.loads(raw);expected=copy.deepcopy(obj);counts=collections.Counter()
    def visit(node):
        if isinstance(node,list):
            for child in node:visit(child)
        elif isinstance(node,dict):
            old=node.get('location')
            if isinstance(old,str) and old in mappings:
                require(node.get('element_type') in ('minecraft:single_pool_element','minecraft:legacy_single_pool_element'),'Non-template location')
                counts[old]+=1;node['location']=mappings[old]
            for child in node.values():visit(child)
    visit(expected);result=raw
    for old,count in counts.items():
        token=json.dumps(old).encode();require(result.count(token)==count,'Ambiguous JSON token')
        result=result.replace(token,json.dumps(mappings[old]).encode())
    require(json.loads(result)==expected,'Unexpected JSON edits')
    return result,counts

def terminal_rewrite(raw,expected):
    require(sha(raw)==expected,'Changed terminal template')
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as f:decoded=f.read(8*1024*1024+1)
    require(len(decoded)<=8*1024*1024,'NBT size limit')
    def field(value):return b'\x08\x00\x04pool'+len(value).to_bytes(2,'big')+value
    old=field(b'minecraft:minecraft_empty');new=field(b'minecraft:empty')
    require(decoded.count(old)==1,'Ambiguous terminal field')
    replaced=decoded.replace(old,new)
    result=bytearray(gzip.compress(replaced,mtime=0));result[9]=255
    require(gzip.decompress(result)==replaced,'NBT compression round trip')
    return bytes(result)

def build(source,output):
    source=Path(source);output=Path(output)
    require(not output.exists() and not output.is_symlink(),'Output exists')
    raw=source.read_bytes();require(sha(raw)==BASE_PACK,'Wrong R38 input')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist();names=[i.filename for i in infos]
        require(len(names)==len(set(names))==8007,'Unexpected/duplicate ZIP entries')
        require(sum(i.file_size for i in infos)<1024**3,'ZIP size limit')
        require(all(not i.is_dir() and i.file_size<128*1024**2 and not i.flag_bits&1 for i in infos),'Unsupported ZIP member')
        require(all(not n.startswith('/') and '\\' not in n and '..' not in n.split('/') for n in names),'Unsafe ZIP path')
        entries={i.filename:z.read(i) for i in infos};comment=z.comment
    old_fingerprint=json.loads(entries[FINGERPRINTS[0]])
    require(entries[FINGERPRINTS[0]]==entries[FINGERPRINTS[1]],'Fingerprints disagree')
    require(content_digest(entries)==old_fingerprint['content_sha256'],'Wrong input fingerprint')
    before=dict(entries);seen=collections.Counter();changed=[]
    for path in entries:
        if '/worldgen/template_pool/' not in path or not path.endswith('.json'):continue
        payload,counts=json_rewrite(entries[path],MAPPINGS)
        if counts:entries[path]=payload;seen.update(counts);changed.append(path)
    require(dict(seen)==COUNTS,'Wrong mapping occurrence set')
    require(len(changed)==27,'Wrong changed JSON set')
    for path,expected in NBT_INPUTS.items():
        entries[path]=terminal_rewrite(entries[path],expected);changed.append(path)
    actual=content_digest(entries)
    require(actual==OUTPUT_CONTENT,'Output content does not match reviewed local candidate')
    doc={'schema':1,'worldgen_id':'NR-DEV-1','algorithm':'sha256-path-and-content-v1','content_sha256':actual,'entry_count_excluding_fingerprint':8005}
    encoded=(json.dumps(doc,indent=2,ensure_ascii=False)+'\n').encode()
    for path in FINGERPRINTS:entries[path]=encoded
    require(set(before)==set(entries),'Resource added or deleted')
    changed_set={p for p in before if before[p]!=entries[p]}
    require(changed_set==set(changed)|set(FINGERPRINTS),'Unexpected byte changes')
    output.parent.mkdir(parents=True,exist_ok=True);tmp=None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent,delete=False) as f:tmp=Path(f.name)
        with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            z.comment=comment
            for info in infos:z.writestr(copy.copy(info),entries[info.filename])
        with zipfile.ZipFile(tmp) as z:
            require(z.testzip() is None and {n:z.read(n) for n in z.namelist()}==entries,'Output ZIP readback failed')
        require(sha(source.read_bytes())==BASE_PACK,'Source changed')
        os.link(tmp,output)
    finally:
        if tmp is not None:tmp.unlink(missing_ok=True)
    return {'pass':True,'source_sha256':BASE_PACK,'output_sha256':sha(output.read_bytes()),'output_content_sha256':actual,'mapping_count':len(MAPPINGS),'location_fields':sum(seen.values()),'changed_json':27,'changed_nbt':2,'changed_fingerprints':2,'unchanged_files':7976,'same_resource_set':True,'runtime_tested':False,'production_accepted':False}

class UnitTests(unittest.TestCase):
    def test_only_location(self):
        raw=b'{"location":"x:a","element_type":"minecraft:single_pool_element","weight":4}'
        out,count=json_rewrite(raw,{'x:a':'x:b'});self.assertEqual(json.loads(out)['location'],'x:b');self.assertEqual(count,{'x:a':1})
    def test_ambiguous(self):
        with self.assertRaises(ValueError):json_rewrite(b'{"location":"x:a","name":"x:a","element_type":"minecraft:single_pool_element"}',{'x:a':'x:b'})
    def test_not_template(self):
        with self.assertRaises(ValueError):json_rewrite(b'{"location":"x:a","element_type":"minecraft:feature_pool_element"}',{'x:a':'x:b'})
    def test_noop(self):
        raw=b'{ "weight": 5 }';self.assertEqual(json_rewrite(raw,MAPPINGS),(raw,collections.Counter()))
    def test_recursive(self):
        raw=b'{"elements":[{"location":"x:a","element_type":"minecraft:legacy_single_pool_element"}]}'
        self.assertEqual(json_rewrite(raw,{'x:a':'x:b'})[1],{'x:a':1})
    def test_bad_nbt_hash(self):
        with self.assertRaises(ValueError):terminal_rewrite(b'x','not the hash')
    def test_missing_nbt_field(self):
        raw=gzip.compress(b'no tag',mtime=0)
        with self.assertRaises(ValueError):terminal_rewrite(raw,sha(raw))
    def test_duplicate_nbt_field(self):
        value=b'minecraft:minecraft_empty';field=b'\x08\x00\x04pool'+len(value).to_bytes(2,'big')+value
        raw=gzip.compress(field*2,mtime=0)
        with self.assertRaises(ValueError):terminal_rewrite(raw,sha(raw))
    def test_preserve_nbt_other_bytes(self):
        value=b'minecraft:minecraft_empty';field=b'\x08\x00\x04pool'+len(value).to_bytes(2,'big')+value
        raw=gzip.compress(b'before'+field+b'after',mtime=0)
        out=terminal_rewrite(raw,sha(raw));self.assertEqual(gzip.decompress(out),b'before\x08\x00\x04pool\x00\x0fminecraft:emptyafter');self.assertEqual(out[9],255)
    def test_wrong_input_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a';a.write_bytes(b'wrong');b=Path(tmp)/'b'
            with self.assertRaises(ValueError):build(a,b)
            self.assertFalse(b.exists());self.assertEqual(a.read_bytes(),b'wrong')
    def test_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a';p.write_bytes(b'keep')
            with self.assertRaises(ValueError):build(p,p)
            self.assertEqual(p.read_bytes(),b'keep')
    def test_map_contract(self):
        self.assertEqual(len(MAPPINGS),45);self.assertEqual(sum(COUNTS.values()),53);self.assertEqual(set(MAPPINGS),set(COUNTS))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path);p.add_argument('--output',type=Path);p.add_argument('--report',type=Path);p.add_argument('--self-test',action='store_true');a=p.parse_args()
    if a.self_test:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(UnitTests)
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
    if not a.input or not a.output:p.error('--input and --output required')
    report=build(a.input,a.output)
    if a.report:
        a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
