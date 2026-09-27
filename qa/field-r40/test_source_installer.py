#!/usr/bin/env python3
from pathlib import Path
import importlib.util,shutil,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
M=load('source_r40',ROOT/'scripts/apply-never-overworld-ocean-r40.py')
OLD=load('source_r399',ROOT/'scripts/apply-never-overworld-dry-mine-r399.py')
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.java=self.root/M.JAVA;chunk=self.java/M.CHUNK;chunk.mkdir(parents=True)
        self.light=(ROOT/'source-contract/ChunkLightTask.java').read_bytes()
        self.assertEqual(M.sha(self.light),M.LIGHT_SHA)
        p=self.java/M.LIGHT;p.parent.mkdir(parents=True);p.write_bytes(self.light)
        (chunk/'NeverOverworldWaterPolicyR38.java').write_bytes((ROOT/'native/overworld-r38/NeverOverworldWaterPolicyR38.java').read_bytes())
        self.mine=OLD.transform(OLD.SOURCE.read_bytes())
        (chunk/'NeverOverworldDryMinesR12.java').write_bytes(self.mine)
    def snapshot(self):return {p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
    def test_read_only_preflight(self):
        before=self.snapshot();staged=M.prepare(self.root)
        self.assertEqual(len(staged),3);self.assertEqual(before,self.snapshot())
    def test_install_and_idempotence(self):
        self.assertEqual(M.install(self.root),3);snapshot=self.snapshot()
        self.assertEqual(M.install(self.root),0);self.assertEqual(snapshot,self.snapshot())
    def test_inherited_fixes_preserved(self):
        before={n:(self.java/M.CHUNK/n).read_bytes() for n in M.GUARDS}
        M.install(self.root)
        self.assertEqual(before,{n:(self.java/M.CHUNK/n).read_bytes() for n in M.GUARDS})
    def test_original_light_backup(self):
        M.install(self.root);path=self.java/M.LIGHT
        self.assertEqual(path.with_name(path.name+'.before-r40').read_bytes(),self.light)
        self.assertEqual(path.read_bytes(),self.light.replace(M.ANCHOR,M.CALL+M.ANCHOR,1))
    def test_missing_r399_rejected_without_writes(self):
        (self.java/M.CHUNK/'NeverOverworldDryMinesR12.java').write_bytes(OLD.SOURCE.read_bytes());before=self.snapshot()
        with self.assertRaises(ValueError):M.install(self.root)
        self.assertEqual(before,self.snapshot())
    def test_missing_r396_rejected_without_writes(self):
        p=self.java/M.CHUNK/'NeverOverworldWaterPolicyR38.java';p.write_bytes(p.read_bytes().replace(b'y >= floor',b'y > floor'));before=self.snapshot()
        with self.assertRaises(ValueError):M.install(self.root)
        self.assertEqual(before,self.snapshot())
    def test_changed_light_rejected(self):
        (self.java/M.LIGHT).write_bytes(self.light+b'// unrelated change\n');before=self.snapshot()
        with self.assertRaises(ValueError):M.install(self.root)
        self.assertEqual(before,self.snapshot())
    def test_conflicting_helper_rejected(self):
        p=self.java/M.CHUNK/'OceanConnectivityR395.java';p.write_text('class Unknown {}');before=self.snapshot()
        with self.assertRaises(ValueError):M.install(self.root)
        self.assertEqual(before,self.snapshot())
    def test_misplaced_existing_call_rejected(self):
        with self.assertRaises(ValueError):M.light_transform(M.CALL+self.light)
    def test_duplicate_call_rejected(self):
        with self.assertRaises(ValueError):M.light_transform(self.light.replace(M.ANCHOR,M.CALL+M.CALL+M.ANCHOR,1))
    def test_known_partially_copied_helpers_complete(self):
        name='OceanConnectivityR395.java'
        (self.java/M.CHUNK/name).write_bytes((ROOT/'native/overworld-r395'/name).read_bytes())
        self.assertEqual(M.install(self.root),2)
        self.assertTrue(all(p.read_bytes()==raw for p,raw in M.prepare(self.root).items()))
if __name__=='__main__':unittest.main(verbosity=2)
