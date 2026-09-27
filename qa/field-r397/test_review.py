#!/usr/bin/env python3
import gzip, importlib.util, struct, tempfile, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('r397_review',Path(__file__).with_name('review.py'))
review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)

class WitnessTests(unittest.TestCase):
    def raw(self):
        cells=bytes(48*48*640);sky=bytes(48*48)
        return struct.pack('>8i',0x52333937,-1699,-769,48,48,640,-511,len(cells))+cells+struct.pack('>i',len(sky))+sky+struct.pack('>ii',0,0)
    def parse(self,raw,name='-1699_-769.bin.gz'):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/name;p.write_bytes(gzip.compress(raw));return review.read(p)
    def changed_int(self,offset,value):
        a=bytearray(self.raw());struct.pack_into('>i',a,offset,value);return bytes(a)
    def test_roundtrip(self):
        a=self.parse(self.raw());self.assertEqual((a['cx'],a['cz']),(-1699,-769));self.assertEqual(len(a['cells']),1474560)
    def test_magic(self):
        with self.assertRaises(ValueError):self.parse(self.changed_int(0,0))
    def test_dimensions(self):
        with self.assertRaises(ValueError):self.parse(self.changed_int(12,47))
    def test_negative_length(self):
        with self.assertRaises(ValueError):self.parse(self.changed_int(28,-1))
    def test_wrong_cell_count(self):
        with self.assertRaises(ValueError):self.parse(self.changed_int(28,1474559))
    def test_truncated(self):
        with self.assertRaises(ValueError):self.parse(self.raw()[:-1])
    def test_trailing(self):
        with self.assertRaises(ValueError):self.parse(self.raw()+b'x')
    def test_unknown_code(self):
        a=bytearray(self.raw());a[32]=9
        with self.assertRaises(ValueError):self.parse(a)
    def test_invalid_sky(self):
        a=bytearray(self.raw());a[32+1474560+4]=2
        with self.assertRaises(ValueError):self.parse(a)
    def test_coordinate_filename(self):
        with self.assertRaises(ValueError):self.parse(self.raw(),'-1698_-769.bin.gz')
    def test_java_bitset_little_endian(self):
        for k in range(32):self.assertEqual(review.bit(b'\x81\x02',k),k in (0,7,9))
    def test_owner_position_negative_coordinates(self):
        a={'cx':-1699,'cz':-769}
        for x in (0,15):
            for z in (0,15):
                for y in (-511,67,68,128):
                    i=(y+511)*2304+(z+16)*48+x+16
                    p=review.position(a,i)
                    self.assertEqual(p,[-1699*16+x,y,-769*16+z])
                    self.assertEqual((p[0]//16,p[2]//16),(-1699,-769))
    def test_air_water_same_passability(self):
        self.assertEqual(review.canonical(3),review.canonical(4))
        for v in (0,1,2,5):self.assertNotEqual(review.canonical(3),review.canonical(v))

if __name__=='__main__':unittest.main(verbosity=2)
