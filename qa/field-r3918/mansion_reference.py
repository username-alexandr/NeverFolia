#!/usr/bin/env python3
"""Correct only two verified mansion pool resource-identifier typos.
No template reconstruction, aliases, entity edits or feature suppression.
"""
from pathlib import Path
import copy,json,sys,unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'qa/field-r3915'))
import restore_swift as s
BASE='0e747781b9ea875631f1453903c0ac912d49f14a3a46ad48bbf604148532c621'
CORE='845d0e90fcbe0fbebad7a613aa9934f608cce64a9d41abdfdf012e39e21c1d40'
POOLS={
 'data/minecraft/worldgen/template_pool/illager_mansion/illager_mansion_room.json':'illager_manor_room_degradation',
 'data/minecraft/worldgen/template_pool/illager_mansion/illager_mansion_room_basement.json':'illager_manor_generic_degradation',
}

def repair_pool(raw,processor):
    obj=json.loads(raw);before=copy.deepcopy(obj)
    entries=obj.get('elements');s.need(isinstance(entries,list) and len(entries)>1,'Incomplete pool')
    hits=[i for i,e in enumerate(entries) if e.get('element',{}).get('location')=='minecraft/empty']
    s.need(hits==[0],'Unreviewed occurrence or order of malformed identifier')
    old={'weight':20,'element':{'location':'minecraft/empty','processors':processor,'projection':'rigid','element_type':'minecraft:single_pool_element'}}
    s.need(entries[0]==old,'Unexpected source empty-template element')
    entries[0]['element']['location']='minecraft:empty'
    check=copy.deepcopy(obj);check['elements'][0]['element']['location']='minecraft/empty'
    s.need(check==before,'Changed more than the identifier')
    return (json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode()

def build(raw):
    s.need(s.sha(raw)==BASE,'Wrong integrated pack; do not lose existing patches')
    before=s.read_zip(raw);files=before.copy();changes=[]
    for path,processor in POOLS.items():
        s.need(path in files,'Expected pool absent')
        files[path]=repair_pool(files[path],processor)
        changes.append({'path':path,'before_sha256':s.sha(before[path]),'after_sha256':s.sha(files[path]),'old_location':'minecraft/empty','new_location':'minecraft:empty','weight':20,'processor':processor,'element_type_preserved':'minecraft:single_pool_element'})
    fp=s.load('r3918_mansion_fingerprint',ROOT/'scripts/fingerprint-never-overworld-pack.py')
    encoded=(json.dumps(fp.fingerprint_document(files),ensure_ascii=False,indent=2)+'\n').encode()
    for path in s.FP:files[path]=encoded
    s.need(set(before)==set(files),'No template additions or removals allowed')
    s.need(all(files[p]==v for p,v in before.items() if p not in (*POOLS,*s.FP)),'Unrelated input changed')
    output=s.write_zip(files);s.need(s.read_zip(output)==files and output==s.write_zip(files),'Packaging mismatch')
    return output,{'pass':True,'base_sha256':BASE,'output_sha256':s.sha(output),'changed_pools':changes,'preserved_entries':sum(files[p]==v for p,v in before.items()),'new_geometry':False,'all_reported_bugs_fixed':False}

class Tests(unittest.TestCase):
    def fixture(self):
        return {'name':'example:pool','fallback':'minecraft:empty','elements':[{'weight':20,'element':{'location':'minecraft/empty','processors':'p','projection':'rigid','element_type':'minecraft:single_pool_element'}},{'weight':1,'element':{'location':'example:actual_room','processors':'q','projection':'rigid','element_type':'minecraft:single_pool_element'}}]}
    def apply(self,obj):return json.loads(repair_pool(json.dumps(obj).encode(),'p'))
    def test_only_identifier(self):
        old=self.fixture();new=self.apply(old);self.assertEqual(new['elements'][0]['element']['location'],'minecraft:empty');new['elements'][0]['element']['location']='minecraft/empty';self.assertEqual(old,new)
    def test_weight_change_refused(self):
        x=self.fixture();x['elements'][0]['weight']=1
        with self.assertRaises(ValueError):self.apply(x)
    def test_processor_change_refused(self):
        x=self.fixture();x['elements'][0]['element']['processors']='other'
        with self.assertRaises(ValueError):self.apply(x)
    def test_type_change_refused(self):
        x=self.fixture();x['elements'][0]['element']['element_type']='minecraft:empty_pool_element'
        with self.assertRaises(ValueError):self.apply(x)
    def test_missing_refused(self):
        x=self.fixture();x['elements'][0]['element']['location']='minecraft:empty'
        with self.assertRaises(ValueError):self.apply(x)
    def test_duplicate_refused(self):
        x=self.fixture();x['elements'].append(copy.deepcopy(x['elements'][0]))
        with self.assertRaises(ValueError):self.apply(x)
    def test_wrong_pack_refused(self):
        with self.assertRaises(ValueError):build(b'not the pinned archive')
    def test_invalid_json_refused(self):
        with self.assertRaises(ValueError):repair_pool(b'{bad','p')

if __name__=='__main__':unittest.main(verbosity=2)
