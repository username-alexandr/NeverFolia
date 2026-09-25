#!/usr/bin/env python3
"""Synthetic patch contract checks; native and real-world checks are separate."""
from __future__ import annotations
import copy,importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('r10patch',ROOT/'scripts/apply-never-nether-experiment-r10.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)

class Contracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.folia=self.root/'Folia'
        self.profile=json.loads(P.PROFILE.read_text());self.original={}
        for name,rule in self.profile['files'].items():
            text='synthetic source\n'+'\n'.join((r['old']+'\n')*r['count'] for r in rule['replacements'])
            rule['sha256']=P.digest(text);self.original[name]=text
            target=self.folia/P.JAVA/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
        self.cfg=self.root/'profile.json';self.save()
        self.helper=self.root/'qa/nevernether-r10/candidate'/P.HELPER;self.helper.parent.mkdir(parents=True);self.helper.write_text('// synthetic helper\n')
        self.patches=[patch.object(P,'ROOT',self.root),patch.object(P,'PROFILE',self.cfg)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def save(self):self.cfg.write_text(json.dumps(self.profile))
    def snapshot(self):return {p.relative_to(self.folia).as_posix():p.read_bytes() for p in self.folia.rglob('*') if p.is_file()}
    def reject(self):
        old=self.snapshot()
        with self.assertRaises((ValueError,OSError,KeyError)):P.apply(self.folia)
        self.assertEqual(old,self.snapshot())
    def test_six_planned_files(self):self.assertEqual(len(P.prepare(self.folia)),6)
    def test_prepare_is_read_only(self):
        before=self.snapshot();P.prepare(self.folia);self.assertEqual(before,self.snapshot())
    def test_repeatable_plan(self):self.assertEqual(P.prepare(self.folia),P.prepare(self.folia))
    def test_apply_is_idempotent(self):
        P.apply(self.folia);before=self.snapshot();P.apply(self.folia);self.assertEqual(before,self.snapshot())
    def test_every_hook_exact(self):
        for name,rule in self.profile['files'].items():
            text=P.transform(self.original[name],rule)
            for r in rule['replacements']:self.assertEqual(text.count(r['new']),r['count'])
    def test_inversion_recovers_original_bytes(self):
        for name,rule in self.profile['files'].items():
            text=P.transform(self.original[name],rule)
            for r in reversed(rule['replacements']):text=text.replace(r['new'],r['old'])
            self.assertEqual(text,self.original[name])
    def test_last_source_missing_no_partial_write(self):
        (self.folia/P.JAVA/list(self.original)[-1]).unlink();self.reject()
    def test_changed_hash_no_partial_write(self):
        p=self.folia/P.JAVA/list(self.original)[-1];p.write_text(p.read_text()+'\n');self.reject()
    def test_installed_extra_edit_rejected(self):
        P.apply(self.folia);p=self.folia/P.JAVA/list(self.original)[-1];p.write_text(p.read_text()+'\n');self.reject()
    def test_installed_missing_hook_rejected(self):
        P.apply(self.folia);name=list(self.original)[-1];p=self.folia/P.JAVA/name;r=self.profile['files'][name]['replacements'][-1]
        p.write_text(p.read_text().replace(r['new'],r['old'],1));self.reject()
    def test_duplicate_hook_rejected(self):
        name=list(self.original)[0];r=self.profile['files'][name]['replacements'][0];p=self.folia/P.JAVA/name;t=p.read_text()+r['old']
        p.write_text(t);self.profile['files'][name]['sha256']=P.digest(t);self.save();self.reject()
    def test_missing_hook_rejected_even_under_matching_hash(self):
        name=list(self.original)[0];r=self.profile['files'][name]['replacements'][0];p=self.folia/P.JAVA/name;t=p.read_text().replace(r['old'],'',1)
        p.write_text(t);self.profile['files'][name]['sha256']=P.digest(t);self.save();self.reject()
    def test_existing_new_hook_in_original_rejected(self):
        name=list(self.original)[0];r=self.profile['files'][name]['replacements'][0];p=self.folia/P.JAVA/name;t=p.read_text()+r['new']
        p.write_text(t);self.profile['files'][name]['sha256']=P.digest(t);self.save();self.reject()
    def test_missing_helper_rejected(self):self.helper.unlink();self.reject()
    def test_empty_helper_rejected(self):self.helper.write_text(' \n');self.reject()
    def test_extra_helper_rejected(self):(self.helper.parent/'Unexpected.java').write_text('x');self.reject()
    def test_conflicting_installed_helper_rejected(self):
        p=self.folia/P.JAVA/P.HELPER;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('different');self.reject()
    def test_identical_installed_helper_accepted(self):
        p=self.folia/P.JAVA/P.HELPER;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(self.helper.read_bytes());self.assertEqual(len(P.prepare(self.folia)),6)
    def test_empty_contract_rejected(self):self.profile['files']={};self.save();self.reject()
    def test_unknown_schema_rejected(self):self.profile['schema']=2;self.save();self.reject()
    def test_traversal_rejected(self):
        self.profile['files']['../../outside.java']=self.profile['files'][list(self.original)[0]];self.save();self.reject()
    def test_unrelated_namespace_rejected(self):
        self.profile['files']['elsewhere/A.java']=self.profile['files'][list(self.original)[0]];self.save();self.reject()
    def test_cli_explicit_opt_in_required(self):
        run=subprocess.run([sys.executable,str(ROOT/'scripts/apply-never-nether-experiment-r10.py'),str(self.folia)],capture_output=True,text=True,timeout=10)
        self.assertEqual(run.returncode,2);self.assertIn('explicit opt-in',run.stderr)
    def test_production_entry_point_unchanged(self):
        s=(ROOT/'scripts/apply-neverfolia-post-patches.sh').read_text()
        self.assertNotIn('apply-never-nether-experiment-r10',s)
    def test_section_hook_covers_both_direct_and_normal_writes(self):
        profile=json.loads((ROOT/'worldgen-spec/never-nether-r10-hooks.json').read_text())
        text=json.dumps(profile['files']['net/minecraft/world/level/chunk/LevelChunkSection.java'])
        self.assertIn('checkThreading',text);self.assertIn('externalWrite',text);self.assertIn('transient volatile',text)
    def test_no_global_world_cache_in_final_candidate(self):
        source=(ROOT/'qa/nevernether-r10/candidate'/P.HELPER).read_text()
        self.assertNotIn('WeakHashMap',source);self.assertNotIn('static final Map<',source)
        self.assertIn('saved/reloaded intermediate chunks are not supported',source)

if __name__=='__main__':unittest.main(verbosity=2)
