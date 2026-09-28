import io,json,unittest,zipfile
from unittest.mock import patch
import restore_swift as s
class Tests(unittest.TestCase):
    def test_wrong_base_before_any_source_work(self):
        with patch.object(s,'load',side_effect=AssertionError('must not load')):
            with self.assertRaisesRegex(ValueError,'Unknown base'):s.restore(b'wrong',b'wrong')
    def test_wrong_author_before_any_source_work(self):
        with patch.object(s,'BASE',s.sha(b'base')),patch.object(s,'load',side_effect=AssertionError('must not load')):
            with self.assertRaisesRegex(ValueError,'Unknown original'):s.restore(b'base',b'wrong')
    def test_utf8_roundtrip(self):
        f={'data/nova/test.json':json.dumps({'name':'Стремительный полёт'},ensure_ascii=False).encode()};self.assertEqual(s.read_zip(s.write_zip(f)),f)
    def test_deterministic_member_order(self):
        self.assertEqual(s.write_zip({'b':b'2','a':b'1'}),s.write_zip({'a':b'1','b':b'2'}))
    def test_unsafe_parent(self):
        with self.assertRaisesRegex(ValueError,'Unsafe'):s.read_zip(s.write_zip({'../escape':b'x'}))
    def test_unsafe_absolute(self):
        with self.assertRaisesRegex(ValueError,'Unsafe'):s.read_zip(s.write_zip({'/escape':b'x'}))
    def test_unsafe_backslash(self):
        with self.assertRaisesRegex(ValueError,'Unsafe'):s.read_zip(s.write_zip({'a\\b':b'x'}))
    def test_duplicate_refused(self):
        f=io.BytesIO()
        with zipfile.ZipFile(f,'w') as z:
            z.writestr('same',b'1');z.writestr('same',b'2')
        with self.assertRaisesRegex(ValueError,'duplicate'):s.read_zip(f.getvalue())
    def test_only_explicit_predicate_closure(self):self.assertEqual(s.PREDICATES,('forward_key','ridden_by_player','sprint_key'))
    def test_no_debug_renaming(self):self.assertEqual(s.ENCHANT,'data/nova_structures/enchantment/swift_soar.json')
if __name__=='__main__':unittest.main(verbosity=2)
