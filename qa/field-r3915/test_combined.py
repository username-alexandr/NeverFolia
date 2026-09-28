#!/usr/bin/env python3
"""Contract tests only; these are not Minecraft runtime scenarios."""
import copy,json,tempfile,unittest,zipfile
from pathlib import Path
import run_combined as r

class Tests(unittest.TestCase):
    def setUp(self):
        self.cases=[]
        for ident in sorted(r.expected_ids()):
            suffix=ident.split('trader_car_',1)[1];role,biome=suffix.rsplit('_',1)
            self.cases.append({'id':ident,'role':role,'biome':biome,'expected_villagers':0 if biome=='pale' else 1,'target':'nova_structures:tavern_trader_car_'+biome,'root_size':[5,5,5]})
        rows=[]
        for i,c in enumerate(self.cases):
            row=copy.deepcopy(c);row.update({'pass':True,'observed_villagers':c['expected_villagers'],'workstations':1,'remaining_jigsaws':0,'nonair_cart_blocks':20,'npc_observations':[{'uuid':f'npc-{i}'}] if c['expected_villagers'] else []});rows.append(row)
        self.result={'pass':True,'nonce':'fresh','seed':r.SEED,'completed':25,'checks':rows,'entity_teardowns':[{'next_case':i,'live_after_barrier':0} for i in range(25)]}
    def check(self):r.validate_cart(self.result,'fresh',self.cases)
    def rejected(self):
        with self.assertRaises(ValueError):self.check()
    def test_complete(self):self.check()
    def test_stale_nonce(self):self.result['nonce']='previous';self.rejected()
    def test_failed_result(self):self.result['pass']=False;self.rejected()
    def test_wrong_seed(self):self.result['seed']=0;self.rejected()
    def test_missing_variant(self):self.result['checks'].pop();self.rejected()
    def test_duplicate_variant(self):self.result['checks'][1]['id']=self.result['checks'][0]['id'];self.rejected()
    def test_changed_expectation(self):self.result['checks'][0]['expected_villagers']=99;self.rejected()
    def test_wrong_npc_count(self):self.result['checks'][0]['observed_villagers']=9;self.rejected()
    def test_missing_station(self):self.result['checks'][0]['workstations']=0;self.rejected()
    def test_unfinished_joint(self):self.result['checks'][0]['remaining_jigsaws']=1;self.rejected()
    def test_contamination(self):self.result['entity_teardowns'][1]['live_after_barrier']=1;self.rejected()
    def test_barrier_missing(self):self.result['entity_teardowns'].pop();self.rejected()
    def test_missing_npc_evidence(self):
        row=next(x for x in self.result['checks'] if x['expected_villagers']);row['npc_observations']=[];self.rejected()
    def test_missing_parent_refuses_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'pack.zip';dst=Path(d)/'fixture.zip'
            with zipfile.ZipFile(src,'w') as z:z.writestr('pack.mcmeta',json.dumps({'pack':{'min_format':[107,1],'max_format':[107,1],'description':'test'}}))
            with self.assertRaises(ValueError):r.root_fixture(src,self.cases,dst)
    def test_original_processors_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'pack.zip';dst=Path(d)/'fixture.zip'
            elements=[{'element_type':'minecraft:single_pool_element','location':x['id'],'projection':'rigid','processors':'minecraft:empty'} for x in self.cases]
            with zipfile.ZipFile(src,'w') as z:
                z.writestr('pack.mcmeta',json.dumps({'pack':{'min_format':[107,1],'max_format':[107,1],'description':'test'}}))
                z.writestr('data/original/worldgen/template_pool/roots.json',json.dumps({'elements':[{'weight':7,'element':e} for e in elements],'fallback':'minecraft:empty'}))
            before=r.sha(src);out=r.root_fixture(src,self.cases,dst);self.assertFalse(out['child_pools_replaced']);self.assertEqual(r.sha(src),before)
            with zipfile.ZipFile(dst) as z:
                self.assertEqual(len(z.namelist()),26)
                for i,e in enumerate(elements):self.assertEqual(json.loads(z.read(f'data/neverfolia_qa/worldgen/template_pool/cart/case_{i}.json'))['elements'][0]['element'],e)
if __name__=='__main__':unittest.main(verbosity=2)
