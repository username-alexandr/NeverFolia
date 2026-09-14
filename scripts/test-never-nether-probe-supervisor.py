#!/usr/bin/env python3
"""Real short-lived CHILD PROCESS tests, not fake Minecraft/worldgen results."""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


R = module('nn_runner_test', ROOT / 'qa/nevernether-r8/run-stage-probe.py')
S = R.SUPERVISOR
V = module('nn_resume_test', ROOT / 'qa/nevernether-r11/resume-stage-probe.py')

CHILD_SETUP = '''import json,os,sys,time,select
from pathlib import Path
p=Path('plugins/NN-STAGE-R8-QA/report.json');p.parent.mkdir(parents=True,exist_ok=True)
def emit(stage='running',n=0):
 rows=[{'phase':'carvers','x':64,'z':i} for i in range(n)]
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps({'stage':stage,'observations':rows}));os.replace(tmp,p)
def stopped():
 ready,_,_=select.select([sys.stdin],[],[],0)
 return bool(ready) and sys.stdin.readline().strip()=='stop'
'''


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def child(self, body, **kwargs):
        # Synthetic children use only stdlib; avoid unrelated site hooks exceeding
        # deliberately sub-second supervisor timeouts. Minecraft flags are unchanged.
        command = [sys.executable, '-S', '-u', '-c', CHILD_SETUP + '\n' + body]
        limits = dict(timeout=3, heartbeat=0.05, stall_timeout=0.4, poll_interval=0.01,
                      stop_grace=0.4, terminate_grace=0.4, kill_grace=1)
        limits.update(kwargs)
        text = io.StringIO()
        with contextlib.redirect_stderr(text):
            result = S.execute(command, self.root, **limits)
        result['test_console'] = text.getvalue()
        return result

    def test_successful_child_reports_progress_then_stops_normally(self):
        result = self.child("emit(n=1)\ntime.sleep(.12)\nemit('completed',2)\nprint(sys.stdin.readline().strip())")
        self.assertEqual(result['stage'], 'completed')
        self.assertEqual(result['process_exit_code'], 0)
        self.assertFalse(result['forced_stop'])
        self.assertIn('phase=carvers', result['test_console'])
        self.assertIn('stop', result['log_tail'])
        final = json.loads((self.root / 'probe-progress.json').read_text())
        self.assertTrue(final['terminal'])
        self.assertEqual(final['observations'], 2)
        self.assertFalse(final['release_ready'])

    def test_no_report_has_its_own_startup_stall_reason(self):
        result = self.child('print(sys.stdin.readline().strip())')
        self.assertEqual(result['stage'], 'startup_stalled')
        self.assertEqual(result['process_exit_code'], 0)
        self.assertFalse(result['forced_stop'])

    def test_running_without_new_observations_stalls(self):
        result = self.child("emit(n=1)\nprint(sys.stdin.readline().strip())")
        self.assertEqual(result['stage'], 'stalled')
        self.assertEqual(result['last_observation_count'], 1)

    def test_log_spam_and_rewritten_identical_report_do_not_count_as_progress(self):
        result = self.child("emit(n=1)\nwhile not stopped():\n print('still alive');emit(n=1);time.sleep(.01)")
        self.assertEqual(result['stage'], 'stalled')
        self.assertLess(result['elapsed_seconds'], 2)
        self.assertIn('still alive', result['log_tail'])

    def test_total_timeout_still_applies_to_advancing_progress(self):
        result = self.child("n=0\nwhile not stopped():\n n+=1;emit(n=n);time.sleep(.025)", timeout=0.4, stall_timeout=2)
        self.assertEqual(result['stage'], 'timeout')
        self.assertGreater(result['last_observation_count'], 1)

    def test_early_process_exit_is_not_a_probe_pass(self):
        result = self.child('sys.exit(3)')
        self.assertEqual(result['stage'], 'exited_early')
        self.assertEqual(result['process_exit_code'], 3)

    def test_malformed_report_stops_child_without_waiting_for_total_timeout(self):
        result = self.child("p.write_text('{broken');sys.stdin.readline()")
        self.assertEqual(result['stage'], 'invalid_report')
        self.assertEqual(result['process_exit_code'], 0)
        self.assertFalse(result['forced_stop'])

    def test_explicit_failed_report_keeps_failure(self):
        result = self.child("emit('failed',1);sys.stdin.readline()")
        self.assertEqual(result['stage'], 'failed')
        self.assertEqual(result['process_exit_code'], 0)

    def test_child_ignoring_normal_stop_is_terminated_and_not_accepted(self):
        result = self.child('time.sleep(30)', stop_grace=0.05)
        self.assertEqual(result['stage'], 'startup_stalled')
        self.assertTrue(result['forced_stop'])
        self.assertIsNotNone(result['process_exit_code'])
        self.assertNotEqual(result['process_exit_code'], 0)

    def test_stale_report_never_starts_a_new_child(self):
        report = self.root / 'plugins/NN-STAGE-R8-QA/report.json'
        report.parent.mkdir(parents=True)
        report.write_text('{"stage":"completed"}')
        with patch.object(S.subprocess, 'Popen') as start, self.assertRaises(ValueError):
            S.execute(['unused'], self.root, 2)
        start.assert_not_called()
        self.assertFalse((self.root / 'run.log').exists())

    def test_existing_log_is_not_overwritten(self):
        path = self.root / 'run.log'; path.write_text('old evidence')
        with self.assertRaises(ValueError):
            S.execute(['unused'], self.root, 2)
        self.assertEqual(path.read_text(), 'old evidence')

    def test_spawn_failure_records_terminal_diagnostics(self):
        with contextlib.redirect_stderr(io.StringIO()):
            result = S.execute(['/no/such/nevernether/java'], self.root, 1)
        self.assertEqual(result['stage'], 'spawn_failed')
        self.assertIsNone(result['process_exit_code'])
        self.assertIn('FileNotFoundError', result['error'])
        self.assertTrue((self.root / 'probe-supervisor-result.json').is_file())

    def test_observation_regression_is_invalid(self):
        path = self.root / 'report.json'; path.write_text('{"stage":"running","observations":[]}')
        with self.assertRaises(ValueError): S.report_status(path, 1)

    def test_disappeared_report_is_invalid(self):
        with self.assertRaises(ValueError): S.report_status(self.root / 'missing', 0)

    def test_unknown_stage_and_bad_rows_are_invalid(self):
        for data in ({'stage':'anything'}, {'stage':'running','observations':[None]}, []):
            path = self.root / 'report.json'; path.write_text(json.dumps(data))
            with self.subTest(data=data), self.assertRaises(ValueError): S.report_status(path, -1)

    def test_invalid_timeout_is_rejected_before_files_or_process(self):
        for value in (0, -1, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError): S.execute(['unused'], self.root, value)
        self.assertEqual(list(self.root.iterdir()), [])


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.runtime = self.root / 'runtime'; (self.runtime / 'classes').mkdir(parents=True)
        (self.runtime / 'classpath.txt').write_text('classes\n')
        (self.runtime / 'classes/A.class').write_bytes(b'synthetic class fixture')
        self.java = self.root / 'java'; self.java.write_text('not executed in preflight')
        self.world = self.root / 'checkpoint'; self.world.mkdir()
        (self.world / '.nevernether-r8-isolated').write_text('test')
        (self.world / 'server.properties').write_text('server-ip=127.0.0.1\n')
        for name in ('world/datapacks', 'plugins/NN-STAGE-R8-QA/carvers'):
            (self.world / name).mkdir(parents=True, exist_ok=True)
        (self.world / 'world/session.lock').write_bytes(b'lock')
        (self.world / 'world/datapacks/NeverNether.zip').write_bytes(b'synthetic fixture pack')
        (self.world / 'plugins/survey-qa.jar').write_bytes(b'synthetic fixture plugin')
        self.plan = {'seed':1, 'chunks':[[64,0]], 'stop_after_carvers':True}
        self.write('stage-plan.json', self.plan)
        self.observations = self.world / 'plugins/NN-STAGE-R8-QA'
        states = self.observations / 'states.json'; states.write_text('{"0":"minecraft:air"}')
        block = self.observations / 'carvers/64_0.bin.gz'; block.write_bytes(b'synthetic snapshot fixture')
        metadata = self.observations / 'carvers/64_0.substrate.nbt'; metadata.write_bytes(b'synthetic metadata fixture')
        self.report = {'stage':'completed','seed':1,'plan':self.plan,'state_dictionary_sha256':R.sha(states),
            'observations':[{'x':64,'z':0,'phase':'carvers','status':'minecraft:carvers','simulation_frozen':True,
                'file':'carvers/64_0.bin.gz','sha256':R.sha(block),'bytes':block.stat().st_size,
                'metadata_file':'carvers/64_0.substrate.nbt','metadata_sections':64,'metadata_sha256':R.sha(metadata)}]}
        self.save_report()
        _, inventory = R.runtime_inventory(self.runtime)
        self.write('runtime-inventory.json', inventory)
        self.old = {'schema':2,'stage':'completed','seed':1,'process_exit_code':0,'forced_stop':False,
            'runtime_unchanged':True,'inputs_unchanged':True,'runtime_payload_sha256':inventory['payload_sha256'],
            'classpath_manifest_sha256':inventory['manifest_sha256'], 'java_executable_sha256':R.sha(self.java),
            'pack_sha256':R.sha(self.world/'world/datapacks/NeverNether.zip'),
            'qa_plugin_sha256':R.sha(self.world/'plugins/survey-qa.jar'),'jvm_flags':list(S.JVM_FLAGS),
            'order':'forward','release_ready':False}
        self.write('run-evidence.json', self.old)
        (self.world / 'run.log').write_text('old log retained')

    def tearDown(self): self.temp.cleanup()
    def write(self, name, value): (self.world / name).write_text(json.dumps(value))
    def save_report(self): self.write('plugins/NN-STAGE-R8-QA/report.json', self.report)
    def snapshot(self): return {str(p.relative_to(self.world)):p.read_bytes() for p in self.world.rglob('*') if p.is_file()}
    def validate(self): return V.validate(self.world, self.runtime, self.java)
    def reject(self):
        before = self.snapshot()
        with self.assertRaises((ValueError,OSError)): self.validate()
        self.assertEqual(self.snapshot(), before)

    def test_valid_checkpoint_preflight_does_not_mutate_files(self):
        before=self.snapshot(); old,plan,_,_=self.validate()
        self.assertEqual(plan,self.plan);self.assertEqual(old,self.old);self.assertEqual(self.snapshot(),before)

    def test_resume_check_only_does_not_move_evidence_or_start_process(self):
        args=['resume','--resume-directory',str(self.world),'--runtime-dir',str(self.runtime),
              '--java',str(self.java),'--acknowledge-disposable-checkpoint','--check-only']
        before=self.snapshot(); output=io.StringIO()
        with patch.object(sys,'argv',args),patch.object(V.subprocess,'Popen') as start,contextlib.redirect_stdout(output),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(V.main(),0)
        start.assert_not_called();self.assertEqual(before,self.snapshot());self.assertFalse(json.loads(output.getvalue())['evidence_moved'])

    def test_new_world_check_only_creates_no_directory(self):
        target=self.root/'absent-world'
        args=['start','--new-directory',str(target),'--java',str(self.java),'--runtime-dir',str(self.runtime),
              '--pack',str(self.world/'world/datapacks/NeverNether.zip'),'--qa-plugin',str(self.world/'plugins/survey-qa.jar'),
              '--plan',str(self.world/'stage-plan.json'),'--seed','1','--accept-eula','--check-only']
        with patch.object(sys,'argv',args),patch.object(R.subprocess,'Popen') as start,contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(R.main(),0)
        start.assert_not_called();self.assertFalse(target.exists())

    def test_verification_error_still_writes_failing_run_evidence(self):
        evidence=dict(self.old)
        (self.runtime/'classpath.txt').unlink()
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            result=R.finish(evidence,self.world,self.runtime,{},self.world/'world/datapacks/NeverNether.zip',self.world/'plugins/survey-qa.jar')
        self.assertEqual(result,2)
        saved=json.loads((self.world/'run-evidence.json').read_text())
        self.assertFalse(saved['runtime_unchanged'])
        self.assertTrue(saved['verification_errors'])

    def test_java_option_injection_rejected_before_mutation(self):
        self.old['jvm_flags'].append('-javaagent:unreviewed.jar');self.write('run-evidence.json',self.old);self.reject()
    def test_corrupted_state_dictionary_rejected(self):
        (self.observations/'states.json').write_text('{}');self.reject()
    def test_corrupted_block_snapshot_rejected(self):
        (self.observations/'carvers/64_0.bin.gz').write_bytes(b'changed');self.reject()
    def test_corrupted_metadata_rejected(self):
        (self.observations/'carvers/64_0.substrate.nbt').write_bytes(b'changed');self.reject()
    def test_report_plan_mismatch_rejected(self):
        self.report['plan']={'seed':1,'chunks':[[65,0]],'stop_after_carvers':True};self.save_report();self.reject()
    def test_snapshot_path_mismatch_rejected(self):
        self.report['observations'][0]['file']='../../outside';self.save_report();self.reject()
    def test_manifest_change_with_same_payload_is_rejected(self):
        (self.runtime/'classpath.txt').write_text('./classes\n');self.reject()
    def test_runtime_payload_change_rejected(self):
        (self.runtime/'classes/A.class').write_bytes(b'changed');self.reject()
    def test_failed_checkpoint_rejected(self):
        self.old['stage']='stalled';self.write('run-evidence.json',self.old);self.reject()
    def test_forced_stop_checkpoint_rejected(self):
        self.old['forced_stop']=True;self.write('run-evidence.json',self.old);self.reject()
    def test_already_resumed_checkpoint_rejected(self):
        (self.world/'checkpoint-evidence').mkdir();self.reject()
    def test_missing_marker_rejected(self):
        (self.world/'.nevernether-r8-isolated').unlink();self.reject()
    def test_unknown_resume_mode_rejected(self):
        with self.assertRaises(ValueError):V.validate(self.world,self.runtime,self.java,'unchecked')
    def test_environment_injection_rejected(self):
        with patch.dict(os.environ,{'JAVA_TOOL_OPTIONS':'-javaagent:bad.jar'}),self.assertRaises(ValueError):S.checked_environment()


if __name__=='__main__':unittest.main(verbosity=2)
