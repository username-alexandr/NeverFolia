#!/usr/bin/env python3
"""Tests for failed/incomplete paired evidence; no Minecraft execution implied."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import zipfile
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('paired',ROOT/'scripts/probe-never-overworld-paired-r12.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)

class PairedTests(unittest.TestCase):
    def test_ore_half_nested_mask_passes(self):
        before={(x,0,0):'iron' for x in range(1000)}
        after={p:k for p,k in before.items() if p[0]%2==0}
        r=P.compare_ore(before,after)
        self.assertTrue(r['pass']);self.assertEqual(r['retained_ratio'],.5)
    def test_no_ore_reduction_is_rejected(self):
        before={(x,0,0):'iron' for x in range(300)}
        self.assertFalse(P.compare_ore(before,before)['pass'])
    def test_ore_insufficient_sample_is_not_success(self):
        self.assertFalse(P.compare_ore({}, {})['pass'])
        self.assertFalse(P.compare_ore({(0,0,0):'gold'}, {})['pass'])
    def test_rerolled_or_retyped_ore_rejected(self):
        old={(x,0,0):'iron' for x in range(300)}
        new={p:k for p,k in old.items() if p[0]%2==0};new[(400,0,0)]='gold'
        self.assertFalse(P.compare_ore(old,new)['pass'])
        del new[(400,0,0)];new[(0,0,0)]='diamond'
        self.assertFalse(P.compare_ore(old,new)['pass'])
    def test_ore_overthinning_rejected(self):
        old={(x,0,0):'iron' for x in range(300)}
        self.assertFalse(P.compare_ore(old,dict(list(old.items())[:50]))['pass'])
    def test_mine_coverage_negative_chunk_and_shell(self):
        self.assertEqual(P.coverage([[0,60,2,3,62,5]]),{(-1,0),(0,0)})
    def test_invalid_box_rejected(self):
        for b in ([0,1,2,0,0,2],[True,1,2,2,3,4],[0,-513,0,3,0,3],[0,0,0,300,1,1]):
            with self.assertRaises(ValueError):P.box_values(b)
    def test_invalid_metadata_rejected(self):
        for v in ([1,1,0,1],[2,1,0,0,0,1,1,1],[1,True,0,0,0,1,1,1]):
            with self.assertRaises(ValueError):P.pdc_boxes({'ChunkBukkitValues':{P.KEY:{'$int_array':v}}})
    def test_valid_metadata_roundtrip(self):
        box=[0,1,2,3,4,5]
        self.assertEqual(P.pdc_boxes({'ChunkBukkitValues':{P.KEY:{'$int_array':[1,1]+box}}}),{tuple(box)})
    def test_abnormal_stop_never_reads_nbt(self):
        nbt=Mock()
        for phase in ({},{'normal_stop':True,'exit_code':1},{'normal_stop':True,'exit_code':False}):
            with self.assertRaises(ValueError):P.saved_volume(Mock(),nbt,Path('.'),[(0,0)],phase)
        nbt.read_chunk_nbt.assert_not_called()
    def test_missing_saved_sections_rejected(self):
        nbt=Mock();nbt.read_chunk_nbt.return_value={'Status':'minecraft:full','xPos':0,'zPos':0,'sections':[]}
        with self.assertRaises(ValueError):P.saved_volume(Mock(),nbt,Path('.'),[(0,0)],{'normal_stop':True,'exit_code':0})
    def test_mine_liquid_is_reported_not_hidden(self):
        box=[0,60,0,1,61,1]
        root={'structures':{'starts':{'minecraft:mineshaft':{'id':'minecraft:mineshaft','Children':[{'BB':{'$int_array':box}}]}}}}
        volume=Mock();volume.roots={p:root for p in P.coverage([box])};volume.at.return_value={'Name':'minecraft:water'}
        area={'target':'minecraft:mineshaft','start_chunk':[0,0]}
        result=P.mine_evidence(volume,area,False)
        self.assertEqual(result['counts']['fluid_cells'],8)
        with self.assertRaises(ValueError):P.mine_evidence(volume,area,True)
    def test_waterlogged_interior_is_wet(self):
        b=[2,60,2,3,61,3]
        root={'structures':{'starts':{'minecraft:mineshaft':{'id':'minecraft:mineshaft','Children':[{'BB':b}]}}},
              'ChunkBukkitValues':{P.KEY:{'$int_array':[1,1]+b}}}
        volume=Mock();volume.roots={(0,0):root};volume.at.return_value={'Name':'minecraft:oak_fence','Properties':{'waterlogged':'true'}}
        self.assertEqual(P.mine_evidence(volume,{'target':'minecraft:mineshaft','start_chunk':[0,0]},True)['counts']['fluid_cells'],8)
    def test_failed_report_cannot_package(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for report in ({},{'paired_gate_pass':True,'production_ready':True},{'paired_gate_pass':'true','production_ready':False}):
                with self.assertRaises(ValueError):P.package(root,root/'absent.jar',{},report,'a'*40,1,None)
            self.assertEqual(list(root.iterdir()),[])

    def package_fixture(self, root):
        jar=root/'server.jar';jar.write_bytes(b'native-jar-fixture')
        packs={name:root/name for name in ('NeverOverworld.zip','NeverNether.zip')}
        for name,path in packs.items():path.write_bytes(name.encode())
        (root/'build-smoke.log').write_text('PASS FieldR12Smoke checks=1\nPASS TreePreservationSmoke checks=1\nPASS NeverNetherFieldCleanupR15Smoke checks=1\nBUILD SUCCESSFUL\n')
        observer=Mock();observer.sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
        report={'paired_gate_pass':True,'production_ready':False,'source_sha':'a'*40,'candidate_jar_sha256':observer.sha(jar),
            'pack_sha256':{name:observer.sha(path) for name,path in packs.items()}}
        return jar,packs,report,observer
    def test_bundle_contains_both_packs_and_valid_checksums(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);jar,packs,report,observer=self.package_fixture(root)
            result=P.package(root,jar,packs,report,'a'*40,1,observer)
            with zipfile.ZipFile(root/result['path']) as archive:
                self.assertEqual(archive.read('world/datapacks/NeverNether.zip'),packs['NeverNether.zip'].read_bytes())
                for line in archive.read('SHA256SUMS.txt').decode().splitlines():
                    digest,name=line.split('  ',1);self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),digest)
                self.assertFalse(json.loads(archive.read('BUILD-INFO.json'))['production_ready'])
    def test_bundle_rejects_missing_nether(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);jar,packs,report,observer=self.package_fixture(root)
            del packs['NeverNether.zip']
            with self.assertRaises(ValueError):P.package(root,jar,packs,report,'a'*40,1,observer)
    def test_bundle_rejects_changed_binary(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);jar,packs,report,observer=self.package_fixture(root)
            jar.write_bytes(b'different')
            with self.assertRaises(ValueError):P.package(root,jar,packs,report,'a'*40,1,observer)
    def test_bundle_requires_native_tests(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);jar,packs,report,observer=self.package_fixture(root)
            (root/'build-smoke.log').write_text('BUILD SUCCESSFUL')
            with self.assertRaises(ValueError):P.package(root,jar,packs,report,'a'*40,1,observer)
    def test_bundle_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);jar,packs,report,observer=self.package_fixture(root)
            output=root/'NeverFolia-FIELD-R12-TEST-aaaaaaa.zip';output.write_bytes(b'original')
            with self.assertRaises(FileExistsError):P.package(root,jar,packs,report,'a'*40,1,observer)
            self.assertEqual(output.read_bytes(),b'original')
    def test_unknown_mine_cell_rejected(self):
        root={'structures':{'starts':{'minecraft:mineshaft':{'id':'minecraft:mineshaft','Children':[{'BB':[2,60,2,3,61,3]}]}}}}
        volume=Mock();volume.roots={(0,0):root};volume.at.return_value=None
        with self.assertRaises(ValueError):P.mine_evidence(volume,{'target':'minecraft:mineshaft','start_chunk':[0,0]},False)

if __name__=='__main__':unittest.main(verbosity=2)
