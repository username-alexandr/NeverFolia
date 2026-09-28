#!/usr/bin/env python3
"""Contract tests only; real jigsaw/Swift checks are a separate workflow step."""
import copy,json,tempfile,unittest,uuid,zipfile
from pathlib import Path
import authored_npc as n
import run_combined as r
import combine_content as c

def entities(*kinds):return (9,(10,[{'nbt':(10,{'id':(8,k)})} for k in kinds]))

class SourceTests(unittest.TestCase):
    def test_villager(self):self.assertEqual(n.entity_signature(entities('minecraft:villager'),True),{'minecraft:villager':1})
    def test_witch(self):self.assertEqual(n.entity_signature(entities('minecraft:witch'),True),{'minecraft:witch':1})
    def test_multiple_exact(self):self.assertEqual(n.entity_signature(entities('minecraft:witch','minecraft:villager','minecraft:witch'),True),{'minecraft:villager':1,'minecraft:witch':2})
    def test_absent_root(self):self.assertEqual(n.entity_signature(None),{})
    def test_empty_end_list(self):self.assertEqual(n.entity_signature((9,(0,[]))),{})
    def test_required_empty(self):
        with self.assertRaises(ValueError):n.entity_signature(entities(),True)
    def test_required_absent(self):
        with self.assertRaises(ValueError):n.entity_signature(None,True)
    def test_wrong_type(self):
        with self.assertRaises(ValueError):n.entity_signature((8,'bad'),True)
    def test_unknown_kind(self):
        with self.assertRaises(ValueError):n.entity_signature(entities('minecraft:pig'),True)
    def test_missing_id(self):
        with self.assertRaises(ValueError):n.entity_signature((9,(10,[{'nbt':(10,{})}])),True)
    def test_passenger_graph_refused(self):
        value=entities('minecraft:villager');value[1][1][0]['nbt'][1]['Passengers']=(9,(10,[{'id':(8,'minecraft:witch')}]))
        with self.assertRaises(ValueError):n.entity_signature(value,True)
    def test_compatible_witch_preserves_input(self):
        rows=[{'template':'child.nbt','sha256':'a'*64,'names':['x:join'],'entities':entities('minecraft:witch')}];before=copy.deepcopy(rows)
        self.assertEqual(c.validate_compatibility('x:join',{'x:join'},rows),['child.nbt'])
        self.assertEqual(rows,before)
        got=n.cart_contract({},[('x:join',rows)])
        self.assertEqual(got['expected_npcs'],[{'minecraft:witch':1}]);self.assertEqual(got['npc_sources'][0]['sha256'],'a'*64)
    def test_root_and_child_combined(self):
        rows=[{'template':'child.nbt','sha256':'a'*64,'names':['x:join'],'entities':entities('minecraft:witch')}]
        self.assertEqual(n.cart_contract({'entities':entities('minecraft:villager')},[('x:join',rows)])['expected_npcs'],[{'minecraft:villager':1,'minecraft:witch':1}])
    def test_childless_is_explicit(self):self.assertEqual(n.cart_contract({},[])['expected_npcs'],[{}])
    def test_missing_joint_refused(self):
        with self.assertRaises(ValueError):n.cart_contract({},[('x:join',[{'names':['x:wrong']}])])
    def test_unsupported_multiple_joints(self):
        with self.assertRaises(ValueError):n.cart_contract({},[('x:a',[]),('x:b',[])])

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.cases=[]
        for ident in sorted(r.expected_ids()):
            role,biome=ident.split('trader_car_',1)[1].rsplit('_',1)
            signature={} if biome=='pale' else {('minecraft:witch' if biome in ('swamp','mangrove') else 'minecraft:villager'):1}
            self.cases.append({'id':ident,'role':role,'biome':biome,'expected_npcs':[signature],'target':'nova_structures:tavern_trader_car_'+biome,'root_size':[5,5,5]})
        rows=[]
        for i,case in enumerate(self.cases):
            row=copy.deepcopy(case);actual=case['expected_npcs'][0]
            evidence=[{'uuid':str(uuid.UUID(int=100+i)),'type':k} for k in actual]
            row.update({'pass':True,'observed_npcs':copy.deepcopy(actual),'workstations':1,'remaining_jigsaws':0,'nonair_cart_blocks':20,'npc_observations':evidence});rows.append(row)
        self.result={'pass':True,'nonce':'fresh','seed':r.SEED,'completed':25,'checks':rows,'entity_teardowns':[{'next_case':i,'live_after_barrier':0} for i in range(25)]}
    def check(self):r.validate_cart(self.result,'fresh',self.cases)
    def rejected(self):
        with self.assertRaises(ValueError):self.check()
    def witch(self):return next(x for x in self.result['checks'] if x['observed_npcs']=={'minecraft:witch':1})
    def test_exact_populations(self):self.check()
    def test_witch_missing_cannot_pass(self):self.witch()['observed_npcs']={};self.rejected()
    def test_witch_replaced_by_villager_cannot_pass(self):self.witch()['observed_npcs']={'minecraft:villager':1};self.rejected()
    def test_witch_extra_cannot_pass(self):self.witch()['observed_npcs']={'minecraft:witch':2};self.rejected()
    def test_foreign_npc_cannot_pass(self):self.witch()['observed_npcs']['minecraft:pig']=1;self.rejected()
    def test_wrong_evidence_type_cannot_pass(self):self.witch()['npc_observations'][0]['type']='minecraft:villager';self.rejected()
    def test_missing_evidence(self):self.witch()['npc_observations']=[];self.rejected()
    def test_duplicate_uuid(self):self.witch()['npc_observations']*=2;self.rejected()
    def test_bad_uuid(self):self.witch()['npc_observations'][0]['uuid']='not-a-uuid';self.rejected()
    def test_wrong_expectation(self):self.witch()['expected_npcs']=[{}];self.rejected()
    def test_no_implicit_empty_swamp(self):
        row=next(c for c in self.cases if c['biome']=='swamp');row['expected_npcs']=[{}];self.rejected()
    def test_negative_expected(self):self.cases[0]['expected_npcs']=[{'minecraft:villager':-1}];self.rejected()
    def test_bool_expected(self):self.cases[0]['expected_npcs']=[{'minecraft:villager':True}];self.rejected()
    def test_stale_nonce(self):self.result['nonce']='previous';self.rejected()
    def test_failed_result(self):self.result['pass']=False;self.rejected()
    def test_wrong_seed(self):self.result['seed']=0;self.rejected()
    def test_missing_variant(self):self.result['checks'].pop();self.rejected()
    def test_duplicate_variant(self):self.result['checks'][1]['id']=self.result['checks'][0]['id'];self.rejected()
    def test_missing_station(self):self.result['checks'][0]['workstations']=0;self.rejected()
    def test_unfinished_joint(self):self.result['checks'][0]['remaining_jigsaws']=1;self.rejected()
    def test_contamination(self):self.result['entity_teardowns'][1]['live_after_barrier']=1;self.rejected()
    def test_missing_barrier(self):self.result['entity_teardowns'].pop();self.rejected()
    def test_missing_parent(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'source.zip'
            with zipfile.ZipFile(src,'w') as z:z.writestr('pack.mcmeta',json.dumps({'pack':{'min_format':[107,1],'max_format':[107,1],'description':'test'}}))
            with self.assertRaises(ValueError):r.root_fixture(src,self.cases,Path(d)/'fixture.zip')
    def test_original_processors_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'source.zip';dest=Path(d)/'fixture.zip'
            elements=[{'element_type':'minecraft:single_pool_element','location':c['id'],'projection':'rigid','processors':'minecraft:empty'} for c in self.cases]
            with zipfile.ZipFile(src,'w') as z:
                z.writestr('pack.mcmeta',json.dumps({'pack':{'min_format':[107,1],'max_format':[107,1],'description':'test'}}))
                z.writestr('data/source/worldgen/template_pool/root.json',json.dumps({'fallback':'minecraft:empty','elements':[{'weight':7,'element':e} for e in elements]}))
            old=r.sha(src);r.root_fixture(src,self.cases,dest);self.assertEqual(old,r.sha(src))
            with zipfile.ZipFile(dest) as z:
                self.assertEqual(len(z.namelist()),26)
                for i,e in enumerate(elements):self.assertEqual(json.loads(z.read(f'data/neverfolia_qa/worldgen/template_pool/cart/case_{i}.json'))['elements'][0]['element'],e)
if __name__=='__main__':unittest.main(verbosity=2)
