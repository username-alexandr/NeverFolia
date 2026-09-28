#!/usr/bin/env python3
import copy, json, tempfile, unittest
from pathlib import Path
import restore_pale as p

class Tests(unittest.TestCase):
    def fixture(self):
        joint=lambda pos,orientation,nbt:{'pos':pos,'state':{'Properties':(10,{'orientation':(8,orientation)})},'nbt':nbt}
        child={'size':[1,4,1],'joints':[joint([0,0,0],'down_south',{'name':p.ID,'pool':'minecraft:empty','target':'minecraft:empty','final_state':'minecraft:air'})],'entities':(9,(10,[])),'blocks':{'minecraft:white_banner':1,'minecraft:birch_wall_sign':1}}
        parent={'joints':[joint(list(pos),'up_south',{'pool':p.ID,'target':p.ID}) for pos in ((19,8,6),(22,8,6),(22,8,9),(19,8,9))]}
        return parent,child
    def test_exact_authored_contract(self):
        a,b=self.fixture();self.assertEqual(len(p.geometry(a,b)),4)
    def test_wrong_extent(self):
        a,b=self.fixture();b['size']=[1,5,1]
        with self.assertRaises(ValueError):p.geometry(a,b)
    def test_wrong_orientation(self):
        a,b=self.fixture();b['joints'][0]['state']['Properties'][1]['orientation']=(8,'up_south')
        with self.assertRaises(ValueError):p.geometry(a,b)
    def test_wrong_input_name(self):
        a,b=self.fixture();b['joints'][0]['nbt']['name']='minecraft:empty'
        with self.assertRaises(ValueError):p.geometry(a,b)
    def test_no_recursive_decoration(self):
        a,b=self.fixture();b['joints'][0]['nbt']['pool']=p.ID
        with self.assertRaises(ValueError):p.geometry(a,b)
    def test_no_entity_injection(self):
        a,b=self.fixture();b['entities']=(9,(10,[{'nbt':(10,{'id':(8,'minecraft:witch')})}]))
        with self.assertRaises(ValueError):p.geometry(a,b)
    def test_missing_parent_output(self):
        a,b=self.fixture();a['joints'].pop()
        with self.assertRaises(ValueError):p.geometry(a,b)
    def test_wrong_parent_target(self):
        a,b=self.fixture();a['joints'][0]['nbt']['target']='minecraft:empty'
        with self.assertRaises(ValueError):p.geometry(a,b)
    def test_no_missing_banner(self):
        a,b=self.fixture();b['blocks']['minecraft:white_banner']=0
        with self.assertRaises(ValueError):p.geometry(a,b)
    def test_no_input_mutation(self):
        a,b=self.fixture();before=copy.deepcopy((a,b));p.geometry(a,b);self.assertEqual((a,b),before)
    def test_nonempty_pool(self):
        e=p.RESTORED['elements'];self.assertEqual(len(e),1);self.assertEqual(e[0]['element']['location'],'nova_structures:pale_residence/decor/banner');self.assertEqual(e[0]['weight'],1)
    def test_reproducible_zip(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'a.zip';b=Path(d)/'b.zip';files={'pack.mcmeta':b'{}','data/a/x':bytes(range(255))};p.write(a,files);p.write(b,files);self.assertEqual(a.read_bytes(),b.read_bytes());self.assertEqual(p.read(a),files)

if __name__=='__main__':unittest.main(verbosity=2)
