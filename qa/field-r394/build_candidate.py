#!/usr/bin/env python3
"""Reconstruct missing full 5x4x5 biome carts from original profession models.
121 existing variants must match after the derived biome change, excluding only
root DataVersion. Every generated model retains its own original DataVersion;
no version is forged and runtime loading remains a separate mandatory test.
"""
from __future__ import annotations
from pathlib import Path
import argparse,copy,gzip,hashlib,importlib.util,io,json,tempfile,unittest,zipfile
ROOT=Path(__file__).resolve().parents[2]
SOURCE='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
BIOMES=('acacia','birch','cherry','desert','jungle','mangrove','oak','pale','snowy','spruce','swamp')
ROLES=('armorer','butcher','farmer','fisher','fletcher','grindstone','leather_worker','librarian','loom','smithing_table','stonecutter')
RECOVER=('cartographer','cleric')
PREFIX='data/nova_structures/structure/tavern/tavern_event_trader_car_'
FINGERPRINTS=('neveroverworld-worldgen-fingerprint.json','data/neverfolia/neveroverworld/worldgen_fingerprint.json')
BASE_HASHES={'cartographer':'6e6312ee2b2a8a569a9a85ab877afa9d3764779a1faafef97bede8bdea9dd21e','cleric':'8ca276de099594ff75a4bc46f982ea7cfb1e0b99b9d698d7edcbe678fc304b79'}
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def sha(data):return hashlib.sha256(data).hexdigest()
def need(ok,message):
    if not ok:raise ValueError(message)
def content(root):
    need(root.get('DataVersion',(None,None))[0]==3,'Missing root DataVersion');return {k:v for k,v in root.items() if k!='DataVersion'}
def changes(a,b,path=()):
    need(type(a) is type(b),'Type change at '+repr(path))
    if isinstance(a,dict):
        need(a.keys()==b.keys(),'Key change at '+repr(path));return [r for k in sorted(a) for r in changes(a[k],b[k],path+(k,))]
    if isinstance(a,(list,tuple)):
        need(len(a)==len(b),'Length change at '+repr(path));return [r for i,(x,y) in enumerate(zip(a,b)) for r in changes(x,y,path+(i,))]
    return [] if a==b else [(path,a,b)]
def allowed(path):
    return (len(path)==6 and path[:3]==('palette',1,1) and isinstance(path[3],int) and path[4:]==('Name',1)) or (len(path)==8 and path[:3]==('blocks',1,1) and isinstance(path[3],int) and path[4:6]==('nbt',1) and path[6] in ('name','pool','target') and path[7]==1)
def assign(node,path,before,after):
    if not path:need(node==before,'Unexpected source value');return copy.deepcopy(after)
    key=path[0]
    if isinstance(node,tuple):
        items=list(node);items[key]=assign(items[key],path[1:],before,after);return tuple(items)
    node=copy.deepcopy(node);node[key]=assign(node[key],path[1:],before,after);return node
def transform(root,ops):
    result=copy.deepcopy(root)
    for path,before,after in ops:
        need(allowed(path),'Unapproved biome field '+repr(path));need(isinstance(before,str) and isinstance(after,str),'Expected string field');result=assign(result,path,before,after)
    restored=copy.deepcopy(result)
    for path,before,after in reversed(ops):restored=assign(restored,path,after,before)
    need(restored==root,'Unrelated data mutation');return result
def validate_cart(root,biome=None):
    need(root.get('size')==(9,(3,[5,4,5])),'Cart must be 5x4x5');entities=root.get('entities');need(entities is not None and entities[0]==9 and entities[1][1]==[],'Expected no direct entities')
    need(root.get('blocks',(None,(None,[])))[0]==9 and len(root['blocks'][1][1])==100,'Expected 100 original blocks')
    joints={tuple(block['pos'][1][1]):block['nbt'][1] for block in root['blocks'][1][1] if block.get('nbt',(10,{}))[1].get('id')==(8,'minecraft:jigsaw')}
    need(set(joints)=={(4,0,0),(2,1,1)},'Connector geometry changed');suffix='' if biome is None else '_'+biome
    need(joints[(4,0,0)]['name']==(8,'nova_structures:tavern_trader_car'+suffix),'Wrong parent connector');need(joints[(2,1,1)]['target']==(8,'nova_structures:tavern_villager'+suffix),'Wrong villager connector')
    if biome is not None:need(joints[(2,1,1)]['pool']==(8,'nova_structures:tavern_trader'),'Wrong villager pool')
def encode(builder,compression,name,root):
    raw=builder._nbt_encode('raw',name,root);need(builder._nbt_parse(raw)==('raw',name,root),'Raw NBT round trip failed');need(compression=='gzip','Unreviewed compression')
    result=bytearray(gzip.compress(raw,compresslevel=9,mtime=0));result[9]=255;result=bytes(result);need(builder._nbt_parse(result)==('gzip',name,root),'Compressed NBT round trip failed');return result
def build(source,output):
    source,output=Path(source),Path(output);need(not output.exists(),'Output already exists');raw=source.read_bytes();need(sha(raw)==SOURCE,'Wrong R39.3 bytes')
    b=load('r394_nbt',ROOT/'scripts/build-never-overworld-external-structures-r19.py');fp=load('r394_fp',ROOT/'scripts/fingerprint-never-overworld-pack.py')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(len(z.namelist())==len(set(z.namelist())) and z.testzip() is None,'Invalid source ZIP');original={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
    need(len(original)==8007,'Wrong resource count');need(original[FINGERPRINTS[0]]==original[FINGERPRINTS[1]],'Fingerprint copies differ');need(json.loads(original[FINGERPRINTS[0]])==fp.fingerprint_document(original),'Invalid fingerprint')
    parsed={role:b._nbt_parse(original[PREFIX+role+'.nbt']) for role in ROLES+RECOVER}
    for role in RECOVER:need(sha(original[PREFIX+role+'.nbt'])==BASE_HASHES[role],'Original model changed');validate_cart(parsed[role][2])
    need('data/nova_structures/worldgen/template_pool/tavern_trader.json' in original,'Missing villager pool');files=original.copy();proofs=[];added=[];transforms={}
    for biome in BIOMES:
        exemplar=b._nbt_parse(original[PREFIX+'armorer_'+biome+'.nbt'])[2];validate_cart(exemplar,biome);ops=changes(content(parsed['armorer'][2]),content(exemplar));transforms[biome]=ops
        for role in ROLES:
            expected=b._nbt_parse(original[PREFIX+role+'_'+biome+'.nbt'])[2];actual=transform(parsed[role][2],ops)
            if content(actual)!=content(expected):raise ValueError('Nonuniform biome recipe '+role+'_'+biome+': '+repr(changes(content(actual),content(expected))[:8]))
            validate_cart(actual,biome);need(actual['DataVersion']==parsed[role][2]['DataVersion'],'DataVersion was changed')
            proofs.append({'role':role,'biome':biome,'all_tags_except_root_DataVersion_equal':True,'retained_DataVersion':actual['DataVersion'][1],'reference_DataVersion':expected['DataVersion'][1],'source_sha256':sha(original[PREFIX+role+'_'+biome+'.nbt'])})
        for role in RECOVER:
            path=PREFIX+role+'_'+biome+'.nbt';need(path not in original,'Would overwrite existing model');compression,name,base=parsed[role];result=transform(base,ops);validate_cart(result,biome);need(result['DataVersion']==base['DataVersion'],'Forged DataVersion');payload=encode(b,compression,name,result);files[path]=payload
            added.append({'path':path,'source':PREFIX+role+'.nbt','source_sha256':BASE_HASHES[role],'sha256':sha(payload),'size':[5,4,5],'direct_entities':0,'retained_DataVersion':result['DataVersion'][1],'changed_leaf_fields':len(ops),'biome':biome,'role':role})
    need(len(proofs)==121 and len(added)==22,'Incomplete recovery proof');doc=fp.fingerprint_document(files);encoded=(json.dumps(doc,indent=2,ensure_ascii=False)+'\n').encode()
    for name in FINGERPRINTS:files[name]=encoded
    need(all(files[n]==v for n,v in original.items() if n not in FINGERPRINTS),'Original gameplay resource mutated');output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as folder:
        temp=Path(folder)/'result.zip'
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for name,data in sorted(files.items()):
                info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,data,compresslevel=9)
        with zipfile.ZipFile(temp) as z:need(len(z.namelist())==8029 and z.testzip() is None and all(z.read(n)==v for n,v in files.items()),'Invalid output ZIP')
        need(source.read_bytes()==raw,'Source changed during operation')
        with output.open('xb') as stream:stream.write(temp.read_bytes())
    return {'pass':True,'source_sha256':SOURCE,'output_sha256':sha(output.read_bytes()),'content_fingerprint':doc,'added_templates':added,'validated_existing_variants':proofs,'biome_transformations':transforms,'original_unchanged':8005,'changed_originals':list(FINGERPRINTS),'output_files':8029,'scope':'22 new full biome variants derived from original geometry; all 121 existing variants matched except root DataVersion. Original DataVersion preserved. Runtime loading, native placement and gameplay remain separate.','runtime_tested':False,'production_accepted':False}
class Tests(unittest.TestCase):
    def test_diff_types(self):
        with self.assertRaises(ValueError):changes(1,'1')
    def test_diff_keys(self):
        with self.assertRaises(ValueError):changes({'a':1},{'b':1})
    def test_diff_length(self):
        with self.assertRaises(ValueError):changes([1],[1,2])
    def test_noop(self):self.assertEqual(changes({'a':(1,[2])},{'a':(1,[2])}),[])
    def test_assign_no_mutation(self):
        root={'a':(1,['old'])};self.assertEqual(assign(root,('a',1,0),'old','new'),{'a':(1,['new'])});self.assertEqual(root,{'a':(1,['old'])})
    def test_wrong_leaf(self):
        with self.assertRaises(ValueError):assign('old',(),'other','new')
    def test_palette_path(self):self.assertTrue(allowed(('palette',1,1,0,'Name',1)))
    def test_connector_path(self):self.assertTrue(allowed(('blocks',1,1,97,'nbt',1,'name',1)))
    def test_entity_forbidden(self):self.assertFalse(allowed(('entities',1,1,0,'id',1)))
    def test_position_forbidden(self):self.assertFalse(allowed(('blocks',1,1,97,'pos',1,1,0)))
    def test_type_tag_forbidden(self):self.assertFalse(allowed(('palette',1,1,0,'Name',0)))
    def test_version_forbidden(self):self.assertFalse(allowed(('DataVersion',1)))
    def test_version_preserved(self):self.assertEqual(transform({'DataVersion':(3,100)},[])['DataVersion'],(3,100))
    def test_only_root_version_excluded(self):self.assertEqual(content({'DataVersion':(3,100),'nested':{'DataVersion':(3,200)}}),{'nested':{'DataVersion':(3,200)}})
    def test_bad_input_no_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source';source.write_bytes(b'bad');output=Path(folder)/'output'
            with self.assertRaises(ValueError):build(source,output)
            self.assertFalse(output.exists())
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path);p.add_argument('--output',type=Path);p.add_argument('--report',type=Path);p.add_argument('--self-test',action='store_true');a=p.parse_args()
    if a.self_test:return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful() else 1
    if not all((a.input,a.output,a.report)):p.error('--input --output --report required')
    try:report=build(a.input,a.output)
    except (Exception,SystemExit) as error:report={'pass':False,'error':repr(error),'production_accepted':False}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('added_templates','validated_existing_variants','biome_transformations')},indent=2));return 0 if report['pass'] else 1
if __name__=='__main__':raise SystemExit(main())
