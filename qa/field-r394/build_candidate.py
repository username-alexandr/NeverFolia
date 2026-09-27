#!/usr/bin/env python3
"""Recover only missing one-block tavern routers; preserve the existing cart models.

R39.3 is immutable. The two missing professions already have their complete original
cart templates and pools. All 121 existing profession/biome routers must agree after
normalizing exactly two typed-NBT string fields before reconstruction is allowed.
This is a patterned reconstruction, not a claim to have found original missing bytes.
"""
from __future__ import annotations
from pathlib import Path
import argparse,copy,gzip,hashlib,importlib.util,io,json,os,tempfile,unittest,zipfile
ROOT=Path(__file__).resolve().parents[2]
SOURCE='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
BIOMES=('acacia','birch','cherry','desert','jungle','mangrove','oak','pale','snowy','spruce','swamp')
ROLES=('armorer','butcher','farmer','fisher','fletcher','grindstone','leather_worker','librarian','loom','smithing_table','stonecutter')
RECOVER=('cartographer','cleric')
BASE_CART_HASHES={'cleric':'9dff523585cefa571c2b2793506294263ab46f3a1c76351f9abac01f59d52380','cartographer':'968c941d579e09ec071613ba1d7f807d5a9d3036e0358c5716ec89cd38c99b9d5'}
PREFIX='data/nova_structures/structure/tavern/tavern_event_trader_car_'
FINGERPRINTS=('neveroverworld-worldgen-fingerprint.json','data/neverfolia/neveroverworld/worldgen_fingerprint.json')

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def sha(raw):return hashlib.sha256(raw).hexdigest()
def need(condition,message):
    if not condition:raise ValueError(message)

def router(root,role,biome,new_role):
    need(role in ROLES+RECOVER and new_role in ROLES+RECOVER,'Unknown profession')
    need(biome in BIOMES,'Unknown biome')
    need(root.get('size')==(9,(3,[1,1,1])),'Router is not exactly one block')
    need(root.get('entities',(9,(10,[])))==(9,(10,[])),'Router must not create its own entities')
    need('palettes' not in root,'Multiple router palettes are unsupported')
    palette=root.get('palette')
    need(palette is not None and palette[0]==9 and palette[1][0]==10 and len(palette[1][1])==1,'Unexpected palette')
    state=palette[1][1][0]
    need(state.get('Name')==(8,'minecraft:jigsaw'),'Router block must be a jigsaw')
    need(state.get('Properties',(10,{}))[1].get('orientation')==(8,'east_up'),'Unexpected router orientation')
    blocks=root.get('blocks')
    need(blocks is not None and blocks[0]==9 and blocks[1][0]==10 and len(blocks[1][1])==1,'Router needs exactly one block')
    block=blocks[1][1][0]
    need(block.get('pos')==(9,(3,[0,0,0])) and block.get('state')==(3,0),'Unexpected router block position/state')
    nbt=block.get('nbt')
    need(nbt is not None and nbt[0]==10,'Missing router compound')
    nbt=nbt[1]
    expected={'id':'minecraft:jigsaw','joint':'rollable','name':f'minecraft:event/trader/{role}_{biome}','pool':f'nova_structures:tavern/trader/{role}','target':'minecraft:trader','final_state':'minecraft:air'}
    for key,value in expected.items():need(nbt.get(key)==(8,value),'Unexpected router field '+key)
    result=copy.deepcopy(root);changed=result['blocks'][1][1][0]['nbt'][1]
    changed['name']=(8,f'minecraft:event/trader/{new_role}_{biome}')
    changed['pool']=(8,f'nova_structures:tavern/trader/{new_role}')
    restored=copy.deepcopy(result);restored['blocks'][1][1][0]['nbt'][1]['name']=nbt['name'];restored['blocks'][1][1][0]['nbt'][1]['pool']=nbt['pool']
    need(restored==root,'Unapproved router mutation')
    return result

def encode(builder,compression,name,root):
    raw=builder._nbt_encode('raw',name,root)
    need(builder._nbt_parse(raw)==('raw',name,root),'Typed NBT round trip failed')
    if compression=='gzip':
        out=bytearray(gzip.compress(raw,compresslevel=9,mtime=0));out[9]=255;return bytes(out)
    need(compression=='raw','Unreviewed router compression')
    return raw

def build(source,output):
    source,output=Path(source),Path(output)
    need(not output.exists(),'Output already exists')
    raw=source.read_bytes();need(sha(raw)==SOURCE,'Not the exact R39.3 source')
    b=load('r394_nbt',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
    fp=load('r394_fingerprint',ROOT/'scripts/fingerprint-never-overworld-pack.py')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(len(z.namelist())==len(set(z.namelist())),'Duplicate ZIP entries')
        need(z.testzip() is None,'Source ZIP CRC failure')
        original={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
    need(len(original)==8007,'Unexpected source file count')
    need(original[FINGERPRINTS[0]]==original[FINGERPRINTS[1]],'Fingerprint documents disagree')
    need(json.loads(original[FINGERPRINTS[0]])==fp.fingerprint_document(original),'Invalid original fingerprint')
    files=original.copy();contracts=[];new_files=[]
    for role in RECOVER:
        name=PREFIX+role+'.nbt';need(sha(original[name])==BASE_CART_HASHES[role],'Original profession cart changed')
        _,_,cart=b._nbt_parse(original[name]);need(cart.get('size')==(9,(3,[5,4,3])),'Unexpected cart bounds')
        entities=cart.get('entities');need(entities and len(entities[1][1])==1,'Original cart needs its villager')
        pool_path=f'data/nova_structures/worldgen/template_pool/tavern/trader/{role}.json'
        pool=json.loads(original[pool_path]);expected={'elements':[{'weight':1,'element':{'element_type':'minecraft:single_pool_element','location':f'nova_structures:tavern/tavern_event_trader_car_{role}','processors':'nova_structures:detrail','projection':'rigid'}}],'fallback':'minecraft:empty'}
        need(pool==expected,'Original profession pool changed')
        need('data/nova_structures/worldgen/processor_list/detrail.json' in original,'Missing original processor')
    for biome in BIOMES:
        parent=PREFIX+'armorer_'+biome+'.nbt';compression,name,root=b._nbt_parse(original[parent])
        router(root,'armorer',biome,'armorer')
        for role in ROLES:
            path=PREFIX+role+'_'+biome+'.nbt';_,_,other=b._nbt_parse(original[path])
            need(router(other,role,biome,'armorer')==root,'Existing router differs beyond profession fields: '+path)
            contracts.append({'path':path,'sha256':sha(original[path]),'normalized_equal':True})
        for role in RECOVER:
            path=PREFIX+role+'_'+biome+'.nbt';need(path not in original,'Recovery would overwrite an existing template')
            changed=router(root,'armorer',biome,role);payload=encode(b,compression,name,changed)
            need(b._nbt_parse(payload)[2]==changed,'Written router round trip mismatch')
            files[path]=payload;new_files.append({'path':path,'sha256':sha(payload),'prototype':parent,'prototype_sha256':sha(original[parent]),'changed_fields':['blocks[0].nbt.name','blocks[0].nbt.pool'],'size':[1,1,1],'entities':0,'profession_cart_sha256':BASE_CART_HASHES[role]})
    need(len(new_files)==22 and len(contracts)==121,'Incomplete reconstruction contract')
    document=fp.fingerprint_document(files);payload=(json.dumps(document,indent=2,ensure_ascii=False)+'\n').encode()
    for path in FINGERPRINTS:files[path]=payload
    need(all(files[k]==v for k,v in original.items() if k not in FINGERPRINTS),'Existing gameplay data changed')
    output.parent.mkdir(parents=True,exist_ok=True);temp=None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent,suffix='.zip',delete=False) as f:temp=Path(f.name)
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for path,data in sorted(files.items()):
                info=zipfile.ZipInfo(path,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,data,compresslevel=9)
        with zipfile.ZipFile(temp) as z:
            need(z.testzip() is None and len(z.namelist())==8029,'Invalid output ZIP')
            need(all(z.read(k)==v for k,v in files.items()),'Output byte mismatch')
        need(source.read_bytes()==raw,'Source changed during build')
        # Exclusive publication; never replace a concurrent user's output.
        with output.open('xb') as out:out.write(temp.read_bytes())
    finally:
        if temp is not None:temp.unlink(missing_ok=True)
    return {'pass':True,'source_sha256':SOURCE,'output_sha256':sha(output.read_bytes()),'content_fingerprint':document,'original_files':len(original),'output_files':len(files),'original_unchanged':8005,'changed_originals':list(FINGERPRINTS),'added_templates':new_files,'existing_router_contracts':contracts,'scope':'Only 22 one-block routing wrappers reconstructed; existing cart geometry, professions, trade/entity payloads, pools, weights, functions and water unchanged. Natural generation/placement acceptance is separate.','runtime_tested':False,'production_accepted':False}

class Tests(unittest.TestCase):
    def fixture(self):
        return {'DataVersion':(3,999),'size':(9,(3,[1,1,1])),'entities':(9,(10,[])),'palette':(9,(10,[{'Name':(8,'minecraft:jigsaw'),'Properties':(10,{'orientation':(8,'east_up')})}])),'blocks':(9,(10,[{'pos':(9,(3,[0,0,0])),'state':(3,0),'nbt':(10,{'id':(8,'minecraft:jigsaw'),'joint':(8,'rollable'),'name':(8,'minecraft:event/trader/armorer_oak'),'pool':(8,'nova_structures:tavern/trader/armorer'),'target':(8,'minecraft:trader'),'final_state':(8,'minecraft:air'),'placement_priority':(3,0)})}]))}
    def test_exact_two_fields(self):
        root=self.fixture();out=router(root,'armorer','oak','cleric');self.assertEqual(out['blocks'][1][1][0]['nbt'][1]['name'],(8,'minecraft:event/trader/cleric_oak'));self.assertEqual(router(out,'cleric','oak','armorer'),root)
    def test_original_immutable(self):
        root=self.fixture();before=copy.deepcopy(root);router(root,'armorer','oak','cleric');self.assertEqual(root,before)
    def test_wrong_profession(self):
        with self.assertRaises(ValueError):router(self.fixture(),'armorer','oak','invented')
    def test_wrong_biome(self):
        with self.assertRaises(ValueError):router(self.fixture(),'armorer','moon','cleric')
    def test_reject_wider_model(self):
        root=self.fixture();root['size']=(9,(3,[5,4,3]))
        with self.assertRaises(ValueError):router(root,'armorer','oak','cleric')
    def test_reject_entities(self):
        root=self.fixture();root['entities']=(9,(10,[{}]))
        with self.assertRaises(ValueError):router(root,'armorer','oak','cleric')
    def test_wrong_block(self):
        root=self.fixture();root['palette'][1][1][0]['Name']=(8,'minecraft:stone')
        with self.assertRaises(ValueError):router(root,'armorer','oak','cleric')
    def test_wrong_orientation(self):
        root=self.fixture();root['palette'][1][1][0]['Properties'][1]['orientation']=(8,'west_up')
        with self.assertRaises(ValueError):router(root,'armorer','oak','cleric')
    def test_wrong_target(self):
        root=self.fixture();root['blocks'][1][1][0]['nbt'][1]['target']=(8,'minecraft:empty')
        with self.assertRaises(ValueError):router(root,'armorer','oak','cleric')
    def test_wrong_name(self):
        root=self.fixture();root['blocks'][1][1][0]['nbt'][1]['name']=(8,'minecraft:wrong')
        with self.assertRaises(ValueError):router(root,'armorer','oak','cleric')
    def test_wrong_pool(self):
        root=self.fixture();root['blocks'][1][1][0]['nbt'][1]['pool']=(8,'minecraft:empty')
        with self.assertRaises(ValueError):router(root,'armorer','oak','cleric')
    def test_two_blocks(self):
        root=self.fixture();root['blocks'][1][1].append(copy.deepcopy(root['blocks'][1][1][0]))
        with self.assertRaises(ValueError):router(root,'armorer','oak','cleric')
    def test_wrong_position(self):
        root=self.fixture();root['blocks'][1][1][0]['pos']=(9,(3,[1,0,0]))
        with self.assertRaises(ValueError):router(root,'armorer','oak','cleric')
    def test_preserve_unknown_tag(self):
        root=self.fixture();root['extra']=(8,'preserved');self.assertEqual(router(root,'armorer','oak','cleric')['extra'],root['extra'])
    def test_all_new_identifiers(self):self.assertEqual(len({PREFIX+r+'_'+b+'.nbt' for b in BIOMES for r in RECOVER}),22)
    def test_wrong_input_no_output(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'input';src.write_bytes(b'bad');out=Path(d)/'out'
            with self.assertRaises(ValueError):build(src,out)
            self.assertFalse(out.exists())

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path);p.add_argument('--output',type=Path);p.add_argument('--report',type=Path);p.add_argument('--self-test',action='store_true');a=p.parse_args()
    if a.self_test:return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful() else 1
    if not all((a.input,a.output,a.report)):p.error('--input --output --report required')
    report=build(a.input,a.output);a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('added_templates','existing_router_contracts')},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
