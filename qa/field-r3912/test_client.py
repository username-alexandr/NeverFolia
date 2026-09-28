#!/usr/bin/env python3
import io,json,tempfile,unittest,zipfile
from pathlib import Path
from build_client import archive_bytes,download,classify_pack,RU,TECH_KEY,jbytes

class Tests(unittest.TestCase):
    def test_member_order_deterministic(self):
        self.assertEqual(archive_bytes({'b':b'B','a':b'A'}),archive_bytes({'a':b'A','b':b'B'}))
    def test_payload_verbatim(self):
        payload=bytes(range(256))*8
        with zipfile.ZipFile(io.BytesIO(archive_bytes({'asset':payload}))) as z:
            self.assertEqual(z.read('asset'),payload)
    def test_absolute_rejected(self):
        with self.assertRaises(ValueError): archive_bytes({'/root':b'x'})
    def test_parent_rejected(self):
        with self.assertRaises(ValueError): archive_bytes({'a/../b':b'x'})
    def test_backslash_rejected(self):
        with self.assertRaises(ValueError): archive_bytes({'a\\b':b'x'})
    def test_foreign_dependency_rejected_without_request(self):
        with self.assertRaises(ValueError): download('https://example.com/mixin.jar')
    def test_http_rejected_without_request(self):
        with self.assertRaises(ValueError): download('http://maven.fabricmc.net/file')
    def test_wrong_pack_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'pack.zip';p.write_bytes(archive_bytes({'pack.mcmeta':b'{}'}))
            with self.assertRaises(ValueError): classify_pack(p)
    def test_russian_keys_have_no_debug_label(self):
        self.assertEqual(len(RU),18)
        self.assertNotIn('Bug Enchant',json.dumps(RU))
        self.assertEqual(RU['swift_soar'],'Стремительный полёт')
        self.assertEqual(RU['wither_coated'],'Иссушающее покрытие')
    def test_unicode_roundtrip(self):
        self.assertEqual(json.loads(jbytes(RU)),RU)
    def test_only_custom_namespace_keys(self):
        self.assertTrue(TECH_KEY.startswith('enchantment.dnt.'))
        self.assertNotIn('knockback',RU)
    def test_crc_and_metadata_reproducible(self):
        raw=archive_bytes({'pack.mcmeta':jbytes({'pack':{'min_format':[88,0],'max_format':[88,0],'description':'test'}})})
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(json.loads(z.read('pack.mcmeta'))['pack']['min_format'],[88,0])
if __name__=='__main__':unittest.main(verbosity=2)
