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
        report.update(passing_gate_fields())
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

def passing_gate_fields():
    return {'ore':{'pass':True},'candidate_vs_repeated_baseline':{'pass':True},
            'execution_protocol_match':True,'baseline_repeatability':{'pass':True},
            'ore_phase_stability':True,'dry_mines_pass':True,
            'tree_observation':{'reduced_in_sample':True}}


class ControlledTests(unittest.TestCase):
    def setup_control(self):
        from copy import deepcopy
        areas=[{'kind':'forest','target':f'forest-{n}','located_xz':[n*32,0],
                'chunks':[[n*2,0]]} for n in range(3)]
        for n,target in enumerate(P.MINE_TARGETS):
            areas.append({'kind':'mine','target':target,'located_xz':[320+n*32,0],
                'start_chunk':[20+n*2,0], 'chunks':[[20+n*2,0]],
                'initial_boxes':[[322+n*32,60,2,324+n*32,62,4]]})
        evidence={'jar_sha256':P.BASE_JAR_SHA,'seed':P.SEED,
            'pack_sha256':{'NeverOverworld.zip':'ow','NeverNether.zip':'nn'},
            'phases':[{'name':n,'normal_stop':True,'exit_code':0} for n in ('initial','complete','restart')],
            'areas':areas,'requests':[{'operation':'locate','target':'forest-0'}],
            'ore_transitions':[{'changed_positions':0},{'changed_positions':0}]}
        before=deepcopy(evidence);repeat=deepcopy(evidence);after=deepcopy(evidence)
        after['jar_sha256']='c'*64
        old={(x,60,2):'iron' for x in range(400)}
        new={p:k for p,k in old.items() if p[0]%2==0}
        return before,repeat,after,old,dict(old),new
    def test_equal_control_and_nested_half_pass(self):
        args=self.setup_control();r=P.controlled_checks(*args)
        self.assertTrue(r['execution_protocol_match']);self.assertTrue(r['baseline_repeatability']['pass'])
        self.assertTrue(r['candidate_vs_repeated_baseline']['pass']);self.assertTrue(r['ore_phase_stability'])
    def test_equal_count_control_reroll_is_detected(self):
        args=list(self.setup_control());args[4][(1000,60,2)]=args[4].pop((399,60,2))
        r=P.controlled_checks(*args)
        self.assertEqual(r['baseline_repeatability']['changed_positions'],2)
        self.assertFalse(r['baseline_repeatability']['pass'])
    def test_control_retyping_is_not_hidden_by_equal_count(self):
        args=list(self.setup_control());args[4][(1,60,2)]='gold'
        r=P.controlled_checks(*args)
        self.assertFalse(r['baseline_repeatability']['pass'])
        self.assertEqual(r['baseline_repeatability']['changes'][0]['before'],'iron')
    def test_phase_mismatch_rejects_protocol(self):
        args=self.setup_control();args[1]['phases'].pop(0)
        self.assertFalse(P.controlled_checks(*args)['execution_protocol_match'])
    def test_request_or_binary_or_seed_or_pack_mismatch_rejects(self):
        for field,value in [('requests',[]),('jar_sha256','different'),('seed',42),('pack_sha256',{})]:
            with self.subTest(field=field):
                args=self.setup_control();args[1][field]=value
                self.assertFalse(P.controlled_checks(*args)['execution_protocol_match'])
    def test_failed_stop_is_not_control_evidence(self):
        for value in (1,False,None):
            args=self.setup_control();args[1]['phases'][0]['exit_code']=value
            self.assertFalse(P.controlled_checks(*args)['execution_protocol_match'])
    def test_changed_located_area_rejected(self):
        args=self.setup_control();args[2]['areas'][0]['located_xz']=[200,0]
        self.assertFalse(P.controlled_checks(*args)['execution_protocol_match'])
    def test_post_full_resource_changes_fail_stability(self):
        args=self.setup_control();args[2]['ore_transitions'][1]['changed_positions']=1
        self.assertFalse(P.controlled_checks(*args)['ore_phase_stability'])
    def test_missing_transition_is_not_zero_changes(self):
        args=self.setup_control();args[1]['ore_transitions']=[]
        self.assertFalse(P.controlled_checks(*args)['ore_phase_stability'])
    def test_control_can_never_override_old_ore_gate(self):
        r=passing_gate_fields();r['ore']['pass']=False
        self.assertFalse(P.controlled_gate(r))
        r=passing_gate_fields();r['baseline_repeatability']['pass']=False
        self.assertFalse(P.controlled_gate(r))
    def test_every_gate_field_is_required_and_typed(self):
        from copy import deepcopy
        good=passing_gate_fields();self.assertTrue(P.controlled_gate(good))
        for field in good:
            r=deepcopy(good);del r[field];self.assertFalse(P.controlled_gate(r))
            r=deepcopy(good);r[field]={} if isinstance(good[field],dict) else 'true'
            self.assertFalse(P.controlled_gate(r))
    def test_delta_is_complete_and_includes_negative_edges(self):
        old={(x,-80,0):'coal' for x in range(-100,100)}
        new={(-1,10,-1):'diamond'}
        r=P.ore_delta(old,new)
        self.assertEqual(r['changed_positions'],201);self.assertEqual(len(r['changes']),201)
        self.assertEqual(r['by_height'],{'below_minus64':200,'at_or_above_minus64':1})
        self.assertEqual(r['by_chunk_location']['chunk_face'],201)
    def test_order_of_dictionary_is_not_a_resource_difference(self):
        a={(0,0,0):'iron',(2,0,0):'coal'}
        self.assertEqual(P.ore_delta(a,dict(reversed(list(a.items()))))['changed_positions'],0)
    def test_same_plan_coordinate_lists_and_tuples_compare_equal(self):
        args=self.setup_control();a=args[0]['areas'];b=json.loads(json.dumps(a))
        b[0]['chunks']=[tuple(p) for p in b[0]['chunks']]
        self.assertEqual(P.plan_signature(a),P.plan_signature(b))
    def test_invalid_plan_does_not_skip_missing_area(self):
        args=self.setup_control()
        with self.assertRaises(ValueError):P.plan_signature(args[0]['areas'][:-1])
        args[0]['areas'][0]['chunks']*=2
        with self.assertRaises(ValueError):P.plan_signature(args[0]['areas'])
    def test_packaging_requires_actual_control_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);jar,packs,r,o=PairedTests().package_fixture(root)
            r['baseline_repeatability']['pass']=False
            with self.assertRaisesRegex(ValueError,'controlled'):P.package(root,jar,packs,r,'a'*40,1,o)
            self.assertFalse(any(root.glob('NeverFolia-*.zip')))


class LifecycleTests(unittest.TestCase):
    """Exercise the real orchestration with fake server/NBT boundaries only."""
    def run_generations(self, root, *, fail_stop=False, fail_locate=False, drift=False):
        from types import SimpleNamespace
        from unittest.mock import patch
        trace=[];active=[False];instances=[]
        points={'minecraft:forest':(224,192),'minecraft:birch_forest':(11840,352),
                'minecraft:taiga':(-10560,-1504),P.MINE_TARGETS[0]:(8192,8240),
                P.MINE_TARGETS[1]:(8736,7904)}
        class FakeServer:
            def __init__(self,jar,work,log):
                self.log=log;active[0]=True;instances.append(self);trace.append(('start',log.name))
            def wait(self,*a,**k):pass
            def disable_random_ticks(self):pass
            def locate(self,kind,target,x,z):
                if fail_locate:raise ValueError('locate failure')
                trace.append(('locate',self.log.name,target))
                px,pz=points[target]
                return (px+32,pz) if drift and self.log.name.startswith('candidate') and target=='minecraft:forest' else (px,pz)
            def load_dimension(self,selected,dimension,dwell=0,serial_generation=False):trace.append(('load',self.log.name,selected,dimension,dwell,serial_generation))
            def stop(self):active[0]=False;trace.append(('stop',self.log.name));return 1 if fail_stop else 0
            def close(self):active[0]=False;trace.append(('close',self.log.name))
        def saved(observer,nbt,region,chunks,phase):
            self.assertFalse(active[0]);self.assertTrue(phase['normal_stop'])
            trace.append(('read',phase['name']))
            roots={}
            for point in map(tuple,chunks):
                starts={}
                for target in P.MINE_TARGETS:
                    x,z=points[target]
                    if point==(x//16,z//16):
                        starts[target]={'id':target,'Children':[{'BB':[x+2,-100,z+2,x+4,-98,z+4]}]}
                roots[point]={'structures':{'starts':starts}}
            return SimpleNamespace(roots=roots)
        observer=SimpleNamespace(FORESTS=tuple(points)[:3],AIR={'minecraft:air'},
            sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(),
            write_json=lambda p,v:p.write_text(json.dumps(v)),
            Volume=lambda roots:SimpleNamespace(roots=roots),
            observed_components=lambda v:{'counts':{'wholly_submerged_components':0}},
            unpack_section=lambda s:[{'Name':'minecraft:bedrock'}]*256+[{'Name':'minecraft:air'}]*3840)
        def nether(region,x,z):
            self.assertFalse(active[0]);return {'Status':'minecraft:full','xPos':x,'zPos':z,'sections':[{'Y':32,'block_states':{}}]}
        nbt=SimpleNamespace(read_chunk_nbt=nether)
        jar=root/'native.jar';jar.write_bytes(b'fixture')
        packs={n:root/n for n in ('NeverOverworld.zip','NeverNether.zip')}
        for n,p in packs.items():p.write_bytes(n.encode())
        out=root/'artifacts';out.mkdir()
        with patch.object(P,'make_server',return_value=FakeServer),patch.object(P,'saved_volume',side_effect=saved),\
             patch.object(P,'resources',return_value={(x,10,0):'iron' for x in range(300)}),\
             patch.object(P,'mine_evidence',return_value={'counts':{'air_cells':20},'fluid_examples':[]}):
            if fail_stop or fail_locate:
                with self.assertRaises(ValueError):P.generate(root,observer,nbt,jar,packs,out,'baseline',P.BASE_SHA)
                self.assertFalse(any(t[0]=='read' for t in trace));return trace,out,None
            first,_=P.generate(root,observer,nbt,jar,packs,out,'baseline',P.BASE_SHA)
            repeated,_=P.generate(root,observer,nbt,jar,packs,out,'baseline-repeat',P.BASE_SHA,first['areas'])
            if drift:
                with self.assertRaisesRegex(ValueError,'selection differs'):
                    P.generate(root,observer,nbt,jar,packs,out,'candidate','a'*40,first['areas'])
                return trace,out,None
            after,_=P.generate(root,observer,nbt,jar,packs,out,'candidate','a'*40,first['areas'])
            return trace,out,(first,repeated,after)
    def test_all_roles_locate_load_and_restart_identically(self):
        with tempfile.TemporaryDirectory() as folder:
            trace,out,runs=self.run_generations(Path(folder))
            self.assertEqual(len([t for t in trace if t[0]=='start']),9)
            self.assertEqual(len([t for t in trace if t[0]=='locate']),15)
            loads=[t for t in trace if t[0]=='load']
            self.assertTrue(all(t[-1] is True for t in loads if '-initial.log' in t[1]))
            self.assertTrue(all(t[-1] is False for t in loads if '-initial.log' not in t[1]))
            for r in runs:self.assertEqual([p['name'] for p in r['phases']],['initial','complete','restart'])
            self.assertEqual(runs[0]['requests'],runs[1]['requests']);self.assertEqual(runs[0]['requests'],runs[2]['requests'])
            self.assertEqual(len(list(out.glob('ore-census-*.json'))),9)
            self.assertEqual(len(list(out.glob('ore-transition-*.json'))),6)
            for r in runs:
                for phase in r['phases']:
                    p=out/phase['ore_census_file']
                    self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),phase['ore_census_sha256'])
                    self.assertEqual(len(json.loads(p.read_text())['records']),300)
    def test_nonzero_stop_never_reads_regions(self):
        with tempfile.TemporaryDirectory() as folder:
            trace,out,_=self.run_generations(Path(folder),fail_stop=True)
            p=json.loads((out/'baseline-plan.json').read_text())
            self.assertFalse(p['phases'][0]['normal_stop'])
    def test_locate_exception_never_reads_regions(self):
        with tempfile.TemporaryDirectory() as folder:self.run_generations(Path(folder),fail_locate=True)
    def test_replayed_plan_drift_preserves_diagnostics_and_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            trace,out,_=self.run_generations(Path(folder),drift=True)
            self.assertTrue((out/'candidate-plan.json').is_file())
            self.assertFalse(any(t[0]=='start' and t[1]=='candidate-complete.log' for t in trace))


if __name__=='__main__':unittest.main(verbosity=2)

