#!/usr/bin/env python3
"""Unit checks for data composition only; no claims about runtime geometry."""
import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import combine_content as c
import restore_swift as s

class Tests(unittest.TestCase):
    def setUp(self):
        self.base={'pack.mcmeta':b'meta','keep.bin':b'preserve',s.ENCHANT:b'old'}
        for p in s.FP:self.base[p]=b'base-fingerprint'
        self.cart=self.base.copy()
        self.cart_add={c.PREFIX+role+'_'+b+'.nbt' for role in ('cartographer','cleric') for b in c.BIOMES}
        self.cart.update({p:('cart:'+p).encode() for p in self.cart_add})
        self.swift=self.base.copy();self.swift[s.ENCHANT]=b'functional'
        self.swift_add={c.resource('function','nova_structures:swift_soar_'+str(i),'.mcfunction') for i in (1,2,3)}|{c.resource('predicate','nova_structures:'+p,'.json') for p in s.PREDICATES}
        self.swift.update({p:('swift:'+p).encode() for p in self.swift_add})
        for p in s.FP:self.cart[p]=b'cart-fingerprint';self.swift[p]=b'swift-fingerprint'
    def compose(self):return c.compose(*(s.write_zip(obj) for obj in (self.base,self.cart,self.swift)))
    def test_union_keeps_both_deltas(self):
        before,after,added=self.compose()
        self.assertEqual(before,self.base);self.assertEqual(added,self.cart_add)
        self.assertEqual(set(after),set(self.base)|self.cart_add|self.swift_add)
        self.assertEqual(after[s.ENCHANT],b'functional');self.assertEqual(after['keep.bin'],b'preserve')
    def test_missing_cart_refused(self):
        del self.cart[next(iter(self.cart_add))]
        with self.assertRaises(ValueError):self.compose()
    def test_extra_cart_refused(self):
        self.cart['data/unreviewed/structure/a.nbt']=b'x'
        with self.assertRaises(ValueError):self.compose()
    def test_cart_cannot_change_original(self):
        self.cart['keep.bin']=b'changed'
        with self.assertRaises(ValueError):self.compose()
    def test_cart_cannot_remove_original(self):
        del self.cart['keep.bin']
        with self.assertRaises(ValueError):self.compose()
    def test_swift_cannot_change_original(self):
        self.swift['keep.bin']=b'changed'
        with self.assertRaises(ValueError):self.compose()
    def test_missing_swift_refused(self):
        del self.swift[next(iter(self.swift_add))]
        with self.assertRaises(ValueError):self.compose()
    def test_extra_swift_refused(self):
        self.swift['data/nova_structures/function/unreviewed.mcfunction']=b'x'
        with self.assertRaises(ValueError):self.compose()
    def test_metadata_fingerprints_do_not_conflict(self):
        _,after,_=self.compose()
        for p in s.FP:self.assertEqual(after[p],self.cart[p])
    def test_resource_parent_path_refused(self):
        with self.assertRaises(ValueError):c.resource('structure','x:../bad','.nbt')
    def test_wrong_core_pin_refused_with_diagnostics(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'server.jar';path.write_bytes(b'new')
            with self.assertRaisesRegex(ValueError,'expected=.*actual='):
                c.exact(folder,'server.jar',s.sha(b'old'))
    def test_duplicate_exact_input_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            for sub in ('a','b'):
                p=Path(folder)/sub;p.mkdir();(p/'server.jar').write_bytes(b'same')
            with self.assertRaisesRegex(ValueError,'Ambiguous'):
                c.exact(folder,'server.jar',s.sha(b'same'))
    def test_current_core_is_reviewed_lifecycle_artifact(self):
        self.assertEqual(c.CORE,'845d0e90fcbe0fbebad7a613aa9934f608cce64a9d41abdfdf012e39e21c1d40')
if __name__=='__main__':unittest.main(verbosity=2)
