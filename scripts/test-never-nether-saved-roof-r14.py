#!/usr/bin/env python3
"""Synthetic R14 persisted palette/provenance regressions, not world acceptance."""
import copy,hashlib,importlib.util,json,struct,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('saved_roof',ROOT/'qa/nevernether-r14/audit-saved-roof-r14.py');M=importlib.util.module_from_spec(s);s.loader.exec_module(M)

def simple():
    current=M.section_data({'palette':[{'Name':'minecraft:air'}]})[2]
    m={'Schema':1,'ChunkX':-1,'ChunkZ':2,'SectionY':32,'Seed':7270913,'Bits':0,'Profile':M.C.PROFILE,'Palette':['minecraft:air'],
       'Original':{'$long_array':[]},'External':{'$long_array':[]},'ProposalIndices':{'$int_array':[]},'ProposalStates':{'$int_array':[]},'CurrentHash':{'$byte_array':current}}
    m['Digest']={'$byte_array':M.canonical_digest(m)};return m

class SavedTests(unittest.TestCase):
    def test_known_single_air_hash_matches_native_string_serialization(self):
        _,_,digest=M.section_data({'palette':[{'Name':'minecraft:air'}]})
        raw=b'minecraft:air';self.assertEqual(digest,hashlib.sha256((struct.pack('>i',len(raw))+raw)*4096).hexdigest())
    def test_canonical_property_order(self):
        self.assertEqual(M.name({'Name':'minecraft:oak_stairs','Properties':{'waterlogged':'false','facing':'east'}}),'minecraft:oak_stairs[facing=east,waterlogged=false]')
    def test_metadata_digest_stable(self):
        m=simple();self.assertEqual(M.canonical_digest(copy.deepcopy(m)),m['Digest']['$byte_array'])
    def test_every_identity_field_affects_digest(self):
        m=simple()
        for field in ('Schema','ChunkX','ChunkZ','SectionY','Seed','Bits'):
            n=copy.deepcopy(m);n[field]+=1
            with self.subTest(field=field):self.assertNotEqual(M.canonical_digest(n),m['Digest']['$byte_array'])
    def test_profile_affects_digest(self):
        m=simple();n=copy.deepcopy(m);n['Profile']='other';self.assertNotEqual(M.canonical_digest(n),m['Digest']['$byte_array'])
    def test_current_hash_length_rejected(self):
        m=simple();m['CurrentHash']['$byte_array']='aa'
        with self.assertRaises(ValueError):M.canonical_digest(m)
    def test_single_substrate_consistent(self):M.provenance(simple(),['minecraft:air'],np.zeros(4096,dtype=np.int64))
    def test_untracked_write_rejected(self):
        with self.assertRaises(ValueError):M.provenance(simple(),['minecraft:stone'],np.zeros(4096,dtype=np.int64))
    def test_external_write_is_retained_not_reclassified(self):
        m=simple();m['External']['$long_array']=[-1]*64
        M.provenance(m,['minecraft:stone'],np.zeros(4096,dtype=np.int64))
    def test_only_marked_external_cell_permitted(self):
        m=simple();m['External']['$long_array']=[1];idx=np.zeros(4096,dtype=np.int64);idx[0]=1
        M.provenance(m,['minecraft:air','minecraft:stone'],idx)
        idx[1]=1
        with self.assertRaises(ValueError):M.provenance(m,['minecraft:air','minecraft:stone'],idx)
    def own(self):
        m=simple();m.update(Palette=['minecraft:air','minecraft:stone'],Bits=1)
        m['Original']['$long_array']=[0]*64;m['ProposalIndices']['$int_array']=[0];m['ProposalStates']['$int_array']=[1]
        idx=np.zeros(4096,dtype=np.int64);idx[0]=1;return m,idx
    def test_valid_owned_proposal(self):
        m,idx=self.own();M.provenance(m,['minecraft:air','minecraft:stone'],idx)
    def test_proposal_cannot_also_be_external(self):
        m,idx=self.own();m['External']['$long_array']=[1]
        with self.assertRaises(ValueError):M.provenance(m,['minecraft:air','minecraft:stone'],idx)
    def test_proposal_must_match_actual_block(self):
        m,idx=self.own();idx[0]=0
        with self.assertRaises(ValueError):M.provenance(m,['minecraft:air','minecraft:stone'],idx)
    def test_proposals_sorted_unique_and_bounded(self):
        for value in ([0,0],[1,0],[-1],[4096]):
            m,idx=self.own();m['ProposalIndices']['$int_array']=value;m['ProposalStates']['$int_array']=[1]*len(value)
            with self.subTest(value=value),self.assertRaises(ValueError):M.provenance(m,['minecraft:air','minecraft:stone'],idx)
    def test_proposal_state_palette_range(self):
        m,idx=self.own();m['ProposalStates']['$int_array']=[2]
        with self.assertRaises(ValueError):M.provenance(m,['minecraft:air','minecraft:stone'],idx)
    def test_palette_must_be_unique(self):
        m=simple();m['Palette']=['minecraft:air','minecraft:air']
        with self.assertRaises(ValueError):M.provenance(m,['minecraft:air'],np.zeros(4096,dtype=np.int64))
    def test_original_bit_width_must_match_palette(self):
        m=simple();m['Bits']=1
        with self.assertRaises(ValueError):M.provenance(m,['minecraft:air'],np.zeros(4096,dtype=np.int64))
    def test_original_length_must_match(self):
        m,idx=self.own();m['Original']['$long_array'].pop()
        with self.assertRaises(ValueError):M.provenance(m,['minecraft:air','minecraft:stone'],idx)
    def test_external_bitmap_bounded(self):
        m=simple();m['External']['$long_array']=[0]*65
        with self.assertRaises(ValueError):M.provenance(m,['minecraft:air'],np.zeros(4096,dtype=np.int64))
    def test_packed_native_block_palette_length_and_range(self):
        c={'palette':[{'Name':'minecraft:air'},{'Name':'minecraft:stone'}],'data':{'$long_array':[0]*256}}
        self.assertEqual(int(M.indices(c).max()),0)
        c['data']['$long_array'][0]=2
        with self.assertRaises(ValueError):M.indices(c)
        c['data']['$long_array'].pop()
        with self.assertRaises(ValueError):M.indices(c)
    def test_no_input_metadata_mutation(self):
        m,idx=self.own();before=copy.deepcopy(m);M.provenance(m,['minecraft:air','minecraft:stone'],idx);self.assertEqual(m,before)

if __name__=='__main__':unittest.main(verbosity=2)
