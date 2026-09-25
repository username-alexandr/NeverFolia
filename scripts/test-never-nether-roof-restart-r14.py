#!/usr/bin/env python3
"""R14 restart preflight: identity checks precede moving evidence or starting Java."""
import contextlib,copy,hashlib,importlib.util,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('restart_roof',ROOT/'qa/nevernether-r14/restart-roof-probe.py');M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
class RestartTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.world=self.root/'world';self.world.mkdir();self.runtime=self.root/'runtime'
        (self.runtime/'classes').mkdir(parents=True);(self.runtime/'classpath.txt').write_text('classes\n');(self.runtime/'classes/A.class').write_bytes(b'fixture')
        self.java=self.root/'java';self.java.write_text('preflight-only')
        (self.world/'.nevernether-r8-isolated').write_text('fixture');(self.world/'server.properties').write_text('server-ip=127.0.0.1\n')
        for n in ('world/datapacks','plugins'): (self.world/n).mkdir(parents=True,exist_ok=True)
        (self.world/'world/datapacks/NeverNether.zip').write_bytes(b'pack');(self.world/'plugins/survey-qa.jar').write_bytes(b'plugin')
        (self.world/'world/session.lock').write_bytes(b'lock');(self.world/'world/.neverfolia-nevernether-height.lock').write_text(M.C.PROFILE+'\n')
        _,inventory=M.R.runtime_inventory(self.runtime)
        self.run=dict(jvm_flags=M.P.JVM_FLAGS,java_executable_sha256=M.R.sha(self.java),runtime_payload_sha256=inventory['payload_sha256'],classpath_manifest_sha256=inventory['manifest_sha256'],pack_sha256=M.R.sha(self.world/'world/datapacks/NeverNether.zip'),qa_plugin_sha256=M.R.sha(self.world/'plugins/survey-qa.jar'))
        self.plan={'seed':1,'chunks':[[64,0]]}
        self.observations=dict(run=self.run,report={'plan':self.plan})
        self.patches=[patch.object(M.C,'load',return_value=self.observations),patch.object(M.H,'read_chunk_nbt',return_value={'xPos':64,'zPos':0,'Status':'minecraft:full'})]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def snapshot(self):return {str(p.relative_to(self.world)):p.read_bytes() for p in self.world.rglob('*') if p.is_file()}
    def validate(self):return M.validate(self.world,self.runtime,self.java)
    def reject(self):
        before=self.snapshot()
        with self.assertRaises((OSError,ValueError)):self.validate()
        self.assertEqual(self.snapshot(),before)
    def test_valid_preflight_read_only(self):
        before=self.snapshot();self.validate();self.assertEqual(self.snapshot(),before)
    def test_check_only_does_not_start_or_move(self):
        args=['test','--world',str(self.world),'--runtime-dir',str(self.runtime),'--java',str(self.java),'--acknowledge-disposable-checkpoint','--check-only']
        before=self.snapshot()
        with patch.object(sys,'argv',args),patch.object(M.R.SUPERVISOR,'execute') as execute,contextlib.redirect_stdout(io.StringIO()):self.assertEqual(M.main(),0)
        execute.assert_not_called();self.assertEqual(self.snapshot(),before)
    def test_memory_profile_matches_start(self):self.assertEqual(M.R.SUPERVISOR.JVM_FLAGS,M.P.JVM_FLAGS);self.assertIn('-Xmx2304M',M.P.JVM_FLAGS)
    def test_mutation_world_rejected(self):self.plan['test_mutations']=True;self.reject()
    def test_readback_cannot_be_implicitly_repeated(self):self.plan['readback']=True;self.reject()
    def test_existing_archived_evidence_rejected(self):(self.world/'before-r14-readback').mkdir();self.reject()
    def test_missing_marker_rejected(self):(self.world/'.nevernether-r8-isolated').unlink();self.reject()
    def test_non_loopback_binding_rejected(self):(self.world/'server.properties').write_text('server-ip=0.0.0.0\n');self.reject()
    def test_changed_flags_rejected(self):self.run['jvm_flags']=['-Xmx3200M'];self.reject()
    def test_changed_runtime_rejected(self):(self.runtime/'classes/A.class').write_bytes(b'changed');self.reject()
    def test_changed_java_rejected(self):self.java.write_bytes(b'changed');self.reject()
    def test_changed_pack_rejected(self):(self.world/'world/datapacks/NeverNether.zip').write_bytes(b'changed');self.reject()
    def test_changed_plugin_rejected(self):(self.world/'plugins/survey-qa.jar').write_bytes(b'changed');self.reject()
    def test_old_height_lock_rejected(self):(self.world/'world/.neverfolia-nevernether-height.lock').write_text('NN-R13-SUBSTRATE-1-RECONCILED-NATURAL\n');self.reject()
    def test_missing_lock_rejected(self):(self.world/'world/.neverfolia-nevernether-height.lock').unlink();self.reject()
    def test_target_must_exist_at_full(self):
        with patch.object(M.H,'read_chunk_nbt',return_value={'xPos':64,'zPos':0,'Status':'minecraft:noise'}):self.reject()
    def test_saved_coordinate_must_match(self):
        with patch.object(M.H,'read_chunk_nbt',return_value={'xPos':65,'zPos':0,'Status':'minecraft:full'}):self.reject()
if __name__=='__main__':unittest.main(verbosity=2)
