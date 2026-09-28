#!/usr/bin/env python3
import copy,io,tempfile,unittest,zipfile
from pathlib import Path
import build_carts as b
class Tests(unittest.TestCase):
    def root(self):
        return {'DataVersion':(3,4903),'size':(9,(3,[2,1,1])),'entities':(9,(10,[])),
            'palette':(9,(10,[{'Name':(8,'minecraft:stone')},{'Name':(8,'minecraft:cartography_table')} ])),
            'blocks':(9,(10,[{'pos':(9,(3,[0,0,0])),'state':(3,0)},{'pos':(9,(3,[1,0,0])),'state':(3,1)}]))}
    def test_palette_order(self):
        a=self.root();c=copy.deepcopy(a);c['palette'][1][1].reverse()
        for x in c['blocks'][1][1]:x['state']=(3,1-x['state'][1])
        self.assertEqual(b.semantic(a),b.semantic(c))
    def test_serialization_order(self):
        a=self.root();c=copy.deepcopy(a);c['blocks'][1][1].reverse();self.assertEqual(b.semantic(a),b.semantic(c))
    def test_duplicate_position_rejected(self):
        a=self.root();a['blocks'][1][1].append(copy.deepcopy(a['blocks'][1][1][0]))
        with self.assertRaises(ValueError):b.semantic(a)
    def test_bad_palette_index_rejected(self):
        a=self.root();a['blocks'][1][1][0]['state']=(3,500)
        with self.assertRaises(ValueError):b.semantic(a)
    def test_extra_snow_layer_reversible(self):
        a=b.semantic(self.root());c=copy.deepcopy(a);c['size']=(9,(3,[2,2,1]));c['blocks'][(0,1,0)]={'state':{'Name':(8,'minecraft:snow')}}
        self.assertEqual(b.apply(a,b.diff(a,c)),c)
    def test_removed_jigsaw_field_reversible(self):
        a=b.semantic(self.root());a['blocks'][(0,0,0)]['nbt']=(10,{'id':(8,'minecraft:jigsaw')});c=copy.deepcopy(a);del c['blocks'][(0,0,0)]['nbt']
        self.assertEqual(b.apply(a,b.diff(a,c)),c)
    def test_workstation_preserved(self):
        a=b.semantic(self.root());c=copy.deepcopy(a);c['blocks'][(0,0,0)]['state']['Name']=(8,'minecraft:acacia_planks')
        out=b.apply(a,b.diff(a,c));self.assertEqual(out['blocks'][(1,0,0)],a['blocks'][(1,0,0)])
    def test_unknown_source_value_rejected(self):
        a={'blocks':{(0,0,0):{'x':'old'}}};c={'blocks':{(0,0,0):{'x':'new'}}};d={'blocks':{(0,0,0):{'x':'unexpected'}}}
        with self.assertRaises(ValueError):b.apply(d,b.diff(a,c))
    def test_entities_cannot_be_recipe(self):
        with self.assertRaises(ValueError):b.apply({'entities':[]},[('replace',('entities',),[],[1])])
    def test_reencode_preserves_DataVersion(self):
        a=self.root();c=b.encode_model(a,b.semantic(a));self.assertEqual(c['DataVersion'],a['DataVersion']);self.assertEqual(b.semantic(a),b.semantic(c))
    def test_sparse_mask_is_preserved(self):
        a=self.root();a['blocks'][1][1].pop(0);model=b.semantic(a);c=b.encode_model(a,model)
        self.assertEqual(b.placement_mask(c),({(1,0,0)},{(0,0,0)}));self.assertEqual(len(c['blocks'][1][1]),1)
    def test_sparse_is_not_explicit_air(self):
        a=self.root();a['blocks'][1][1].pop(0);c=copy.deepcopy(a)
        c['palette'][1][1].append({'Name':(8,'minecraft:air')});c['blocks'][1][1].append({'pos':(9,(3,[0,0,0])),'state':(3,2)})
        self.assertNotEqual(b.semantic(a),b.semantic(c));self.assertNotEqual(b.placement_mask(a),b.placement_mask(c))
    def test_sparse_recipe_deletion_roundtrip(self):
        root=self.root();a=b.semantic(root);c=copy.deepcopy(a);del c['blocks'][(0,0,0)]
        rebuilt=b.encode_model(root,b.apply(a,b.diff(a,c)))
        self.assertEqual(b.semantic(rebuilt),c);self.assertEqual(b.placement_mask(rebuilt)[1],{(0,0,0)})
    def test_outside_mask_rejected(self):
        a=self.root();a['blocks'][1][1][0]['pos']=(9,(3,[-1,0,0]))
        with self.assertRaises(ValueError):b.placement_mask(a)
    def test_zip_deterministic(self):
        a=b.zip_bytes({'b.txt':b'b','a.txt':b'a'});self.assertEqual(a,b.zip_bytes({'a.txt':b'a','b.txt':b'b'}))
        with zipfile.ZipFile(io.BytesIO(a)) as z:self.assertIsNone(z.testzip());self.assertEqual(z.read('b.txt'),b'b')
    def test_wrong_pack_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input.zip';p.write_bytes(b'wrong');q=Path(d)/'output.zip'
            with self.assertRaises(ValueError):b.build(p,q)
            self.assertFalse(q.exists())
if __name__=='__main__':unittest.main(verbosity=2)
