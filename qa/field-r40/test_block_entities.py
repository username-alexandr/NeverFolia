#!/usr/bin/env python3
"""No Minecraft launch. Tests only the complete block-entity comparator."""
import copy
import unittest
from block_entity_compare import compare_block_entities, index_block_entities

class Tests(unittest.TestCase):
    def setUp(self):
        self.a={'id':'minecraft:chest','x':1,'y':64,'z':2,'Items':[{'Slot':0,'id':'minecraft:diamond','count':3}],'unknown':{'values':[1,2]}}
        self.b={'id':'minecraft:trial_spawner','x':4,'y':65,'z':5,'normal_config':{'spawn_potentials':[{'weight':1,'data':{'entity':{'id':'minecraft:zombie'}}}]}}
    def cmp(self,left,right):return compare_block_entities(left,right,0,0)
    def test_exact_equal(self):self.assertTrue(self.cmp([self.a,self.b],copy.deepcopy([self.a,self.b]))['equal'])
    def test_outer_order_only(self):
        result=self.cmp([self.a,self.b],[self.b,self.a]);self.assertTrue(result['equal']);self.assertTrue(result['order_only']);self.assertEqual(result['differences'],[])
    def test_empty_lists(self):self.assertTrue(self.cmp([],[])['equal'])
    def test_item_count_change(self):
        changed=copy.deepcopy(self.a);changed['Items'][0]['count']=4
        self.assertFalse(self.cmp([self.a],[changed])['equal'])
    def test_item_removed(self):
        changed=copy.deepcopy(self.a);changed['Items']=[]
        self.assertFalse(self.cmp([self.a],[changed])['equal'])
    def test_unknown_field_change(self):
        changed=copy.deepcopy(self.a);changed['unknown']['values'][0]=9
        self.assertFalse(self.cmp([self.a],[changed])['equal'])
    def test_nested_list_order_not_normalized(self):
        changed=copy.deepcopy(self.a);changed['unknown']['values'].reverse()
        self.assertFalse(self.cmp([self.a],[changed])['equal'])
    def test_added_field_not_ignored(self):
        changed=copy.deepcopy(self.a);changed['new_field']=0
        self.assertFalse(self.cmp([self.a],[changed])['equal'])
    def test_removed_field_not_ignored(self):
        changed=copy.deepcopy(self.a);del changed['unknown']
        self.assertFalse(self.cmp([self.a],[changed])['equal'])
    def test_id_change(self):
        changed=copy.deepcopy(self.a);changed['id']='minecraft:barrel'
        self.assertFalse(self.cmp([self.a],[changed])['equal'])
    def test_coordinate_change(self):
        changed=copy.deepcopy(self.a);changed['x']=2
        result=self.cmp([self.a],[changed]);self.assertFalse(result['equal']);self.assertEqual(len(result['differences']),2)
    def test_added_entity(self):self.assertFalse(self.cmp([self.a],[self.a,self.b])['equal'])
    def test_removed_entity(self):self.assertFalse(self.cmp([self.a,self.b],[self.a])['equal'])
    def test_duplicate_identical_records_rejected(self):
        with self.assertRaises(ValueError):self.cmp([self.a,self.a],[self.a])
    def test_duplicate_after_records_rejected(self):
        with self.assertRaises(ValueError):self.cmp([self.a],[self.a,self.a])
    def test_non_list_rejected(self):
        with self.assertRaises(ValueError):self.cmp({},[])
    def test_non_compound_rejected(self):
        with self.assertRaises(ValueError):self.cmp([None],[])
    def test_missing_id_rejected(self):
        changed=copy.deepcopy(self.a);del changed['id']
        with self.assertRaises(ValueError):self.cmp([changed],[])
    def test_missing_coordinate_rejected(self):
        changed=copy.deepcopy(self.a);del changed['x']
        with self.assertRaises(ValueError):self.cmp([changed],[])
    def test_boolean_coordinate_rejected(self):
        changed=copy.deepcopy(self.a);changed['x']=True
        with self.assertRaises(ValueError):self.cmp([changed],[])
    def test_fractional_coordinate_rejected(self):
        changed=copy.deepcopy(self.a);changed['x']=1.0
        with self.assertRaises(ValueError):self.cmp([changed],[])
    def test_other_owner_rejected(self):
        changed=copy.deepcopy(self.a);changed['x']=16
        with self.assertRaises(ValueError):self.cmp([changed],[])
    def test_height_outside_envelope_rejected(self):
        for y in (-513,512):
            changed=copy.deepcopy(self.a);changed['y']=y
            with self.assertRaises(ValueError):self.cmp([changed],[])
    def test_negative_coordinate_floor_division(self):
        changed=copy.deepcopy(self.a);changed.update(x=-1,z=-16)
        self.assertEqual(list(index_block_entities([changed],-1,-1)),[(-1,64,-16)])
        with self.assertRaises(ValueError):index_block_entities([changed],0,0)
    def test_inputs_not_mutated(self):
        left=[self.a,self.b];right=[self.b,self.a];before=copy.deepcopy((left,right));self.cmp(left,right);self.assertEqual((left,right),before)
    def test_spawner_nested_entity_change(self):
        changed=copy.deepcopy(self.b);changed['normal_config']['spawn_potentials'][0]['data']['entity']['id']='minecraft:skeleton'
        self.assertFalse(self.cmp([self.b],[changed])['equal'])

if __name__=='__main__':unittest.main(verbosity=2)
