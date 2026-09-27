#!/usr/bin/env python3
import unittest
import witness as w

class WitnessTests(unittest.TestCase):
    def test_open_volume(self):
        cells=bytes([3]*18);sky=bytes([0,0,0,0,1,0,0,0,0])
        positions,visited=w.certify(3,3,2,cells,sky,b'',b'\x03')
        self.assertEqual(positions,[(0,0,0),(0,1,0)]);self.assertEqual(visited,18)
    def test_no_ocean_source(self):
        self.assertEqual(w.certify(3,3,2,bytes([3]*18),bytes(9),b'',b'')[0],[])
    def test_water_not_automatic_seed(self):
        cells=bytearray([3]*18);cells[4]=4
        self.assertEqual(w.certify(3,3,2,cells,bytes(9),b'',b'')[1],0)
    def test_side_path_under_roof(self):
        cells=bytearray([3]*18);cells[13]=1
        sky=bytearray(9);sky[0]=1
        self.assertEqual(w.certify(3,3,2,cells,sky,b'',b'\x01')[0],[(0,0,0)])
    def test_protected_cell_never_written(self):
        cells=bytearray([3]*18);cells[4]=2
        positions,_=w.certify(3,3,2,cells,bytes([1]*9),b'',b'\x02')
        self.assertEqual(positions,[(0,1,0)])
    def test_lava_neighbour_barrier(self):
        cells=bytearray([3]*18);cells[3]=5
        self.assertEqual(w.certify(3,3,2,cells,bytes([1]*9),b'',b'\x02')[0],[(0,1,0)])
    def test_extra_lava_barrier(self):
        mask=bytearray(3);w.setbit(mask,4)
        self.assertEqual(w.certify(3,3,2,bytes([3]*18),bytes([1]*9),mask,b'\x02')[0],[(0,1,0)])
    def test_diagonal_not_connected(self):
        cells=bytearray([1]*9);cells[0]=cells[4]=3
        self.assertEqual(w.certify(3,3,1,cells,bytes([1,0,0,0,0,0,0,0,0]),b'',b'')[0],[])
    def test_unknown_not_seed(self):
        cells=bytearray([3]*18);cells[13]=0
        self.assertEqual(w.certify(3,3,2,cells,bytes([0,0,0,0,1,0,0,0,0]),b'',b'')[0],[])
    def test_missing_write_rejected(self):
        with self.assertRaises(ValueError):w.certify(3,3,2,bytes([3]*18),bytes([1]*9),b'',b'\x02')
    def test_unproved_write_rejected(self):
        with self.assertRaises(ValueError):w.certify(3,3,2,bytes([3]*18),bytes(9),b'',b'\x01')
    def test_bad_envelope_rejected(self):
        with self.assertRaises(ValueError):w.certify(4,3,2,bytes(24),bytes(12),b'',b'')
    def test_bad_code_rejected(self):
        with self.assertRaises(ValueError):w.certify(3,3,1,bytes([9]*9),bytes(9),b'',b'')
    def test_extra_write_bits_rejected(self):
        with self.assertRaises(ValueError):w.certify(3,3,1,bytes([3]*9),bytes([1]*9),b'',b'\x81')
if __name__=='__main__':unittest.main(verbosity=2)
