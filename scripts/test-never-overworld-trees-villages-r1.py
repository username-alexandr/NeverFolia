#!/usr/bin/env python3
"""Synthetic regressions for the saved-world observer, not generated-world evidence."""
import copy
import itertools
import json
import re
from types import SimpleNamespace
from unittest.mock import Mock, patch
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('observer',Path(__file__).with_name('probe-never-overworld-trees-villages-r1.py'))
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)


def fixture(changes=None,cx=0,cz=0):
    changes=changes or {}; sections=[]
    for sy in sorted({y//16 for x,y,z in changes}):
        palette=[{'Name':'minecraft:air'}]; indices=[0]*4096
        for (x,y,z), value in changes.items():
            if y//16 != sy: continue
            if isinstance(value,str): value={'Name':value}
            if value not in palette: palette.append(value)
            indices[((y&15)<<8)|((z&15)<<4)|(x&15)]=palette.index(value)
        states={'palette':palette}
        if len(palette)>1:
            bits=max(4,(len(palette)-1).bit_length()); per=64//bits; data=[0]*((4096+per-1)//per)
            for i,n in enumerate(indices): data[i//per] |= n << ((i%per)*bits)
            # Exercise Java signed long representation, too.
            data=[n-(1<<64) if n&(1<<63) else n for n in data]
            states['data']={'$long_array':data}
        sections.append({'Y':sy,'block_states':states})
    return {'xPos':cx,'zPos':cz,'Status':'minecraft:full','sections':sections}


def observed(changes,cx=0,cz=0):
    return P.observed_components(P.Volume({(cx,cz):fixture(changes,cx,cz)}))


class ObserverTests(unittest.TestCase):
    def test_submerged_component_is_observed_without_mutation(self):
        root=fixture({(7,120,7):'minecraft:oak_log',(7,121,7):'minecraft:oak_leaves',
                      (8,120,7):'minecraft:water'})
        before=copy.deepcopy(root)
        data=P.observed_components(P.Volume({(0,0):root}))
        self.assertEqual(data['counts']['wholly_submerged_components'],1)
        self.assertEqual(root,before)

    def test_partial_counts_are_blocks_not_depth(self):
        for n in (2,3):
            changes={(7,129,7):'minecraft:oak_log',(7,130,7):'minecraft:oak_leaves',
                     (8,128,7):'minecraft:water'}
            for y in range(129-n,129): changes[(7,y,7)]='minecraft:oak_log'
            result=observed(changes)
            self.assertEqual(result['counts'][f'partial_{n}_block_components'],1)
            self.assertEqual(result['counts']['wholly_submerged_components'],0)

    def test_horizontal_is_candidate_not_fallen_feature_proof(self):
        result=observed({(7,120,7):{'Name':'minecraft:birch_log','Properties':{'axis':'x'}},
                         (8,120,7):'minecraft:birch_leaves',(7,121,7):'minecraft:water'})
        self.assertEqual(result['counts']['horizontal_log_components'],1)
        self.assertIn('not proof',result['classification_scope'])

    def test_plain_air_below_sea_is_not_evidence_of_submersion(self):
        result=observed({(7,120,7):'minecraft:oak_log',(7,121,7):'minecraft:oak_leaves'})
        self.assertEqual(result['counts']['wholly_submerged_components'],0)

    def test_unloaded_neighbour_does_not_make_tree_complete(self):
        result=observed({(0,120,7):'minecraft:oak_log',(0,121,7):'minecraft:oak_leaves',
                         (1,120,7):'minecraft:water'})
        self.assertEqual(result['counts']['sample_boundary_components'],1)
        self.assertEqual(result['counts']['wholly_submerged_components'],0)

    def test_negative_coordinates_and_waterlogged_leaves(self):
        result=observed({(-9,120,-9):'minecraft:oak_log',(-9,121,-9):{
            'Name':'minecraft:oak_leaves','Properties':{'waterlogged':'true'}}},-1,-1)
        self.assertEqual(result['counts']['wholly_submerged_components'],1)
        self.assertEqual(result['examples'][0]['sample'],[-9,120,-9])

    def test_incomplete_status_and_wrong_coordinates_fail(self):
        for key,value in (('Status','minecraft:features'),('xPos',4),('zPos',4)):
            root=fixture();root[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): P.Volume({(0,0):root})

    def test_palette_padding_and_signed_longs(self):
        changes={(x,5,z):f'minecraft:test_{x+z*16}' for x in range(16) for z in range(16)}
        volume=P.Volume({(0,0):fixture(changes)})
        for point,name in changes.items():self.assertEqual(volume.at(*point)['Name'],name)

    def test_palette_payload_truncation_fails(self):
        root=fixture({(7,120,7):'minecraft:oak_log'})
        root['sections'][0]['block_states']['data']['$long_array'].pop()
        with self.assertRaises(ValueError):P.Volume({(0,0):root}).wood()

    def test_water_between_pieces_is_permitted_and_exported(self):
        changes={(x,128,z):'minecraft:water' for z in range(3,7) for x in range(3,11)}
        volume=P.Volume({(0,0):fixture(changes)})
        boxes=[[3,129,3,4,135,6],[9,129,3,10,135,6]]
        with tempfile.TemporaryDirectory() as raw:
            out=Path(raw)/'plane.csv';result=P.village_plane(volume,boxes,out)
            self.assertEqual(result['counts']['outside_piece_bbox_water'],16)
            self.assertFalse(result['visual_shape_accepted'])
            self.assertTrue(out.read_text().startswith('x,z,y128_block'))

    def test_missing_village_column_is_not_dry_success(self):
        with tempfile.TemporaryDirectory() as raw,self.assertRaises(ValueError):
            P.village_plane(P.Volume({(0,0):fixture()}),[[14,129,3,18,134,5]],Path(raw)/'plane.csv')

    def test_invalid_or_missing_start_fails(self):
        with self.assertRaises(ValueError):P.boxes_for_start({},'minecraft:village_plains')
        root={'structures':{'starts':{'minecraft:village_plains':{
            'id':'minecraft:village_plains','Children':[{'BB':{'$int_array':[0,1,2,3]}}]}}}}
        with self.assertRaises(ValueError):P.boxes_for_start(root,'minecraft:village_plains')

    def test_bbox_coverage_crosses_negative_boundary(self):
        self.assertEqual(set(P.coverage([[-2,120,-2,2,136,2]],0)),{(-1,-1),(-1,0),(0,-1),(0,0)})
        with self.assertRaises(ValueError):P.coverage([[0,0,0,10**20,4,10**20]])

    def test_abnormal_stop_fails_before_region_reads(self):
        for value in (False,'true',None):
            with self.subTest(value=value),self.assertRaises(ValueError):
                P.audit({'normal_stop':value},Path('/unused'),Path('/unused'),None)

    def test_existing_world_directory_is_never_removed(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);work=root/'.work/trees-villages-natural-r1';work.mkdir(parents=True)
            marker=work/'do-not-delete';marker.write_text('keep')
            with self.assertRaises(FileExistsError):P.generate(root,Path('unused'),Path('unused'),root,None)
            self.assertEqual(marker.read_text(),'keep')



class ConsoleTests(unittest.TestCase):
    def console(self, response='', previous=''):
        server=P.Server.__new__(P.Server)
        server.token=0; server.p=SimpleNamespace(poll=lambda:None)
        state={'text':previous, 'commands':[]}
        server.text=lambda:state['text']
        def send(command):
            state['commands'].append(command)
            state['text']+=response
        server.send=send
        return server,state

    def test_gamerule_requires_own_positive_reply_and_no_save_command(self):
        server,state=self.console('[12:26:21 INFO]: Gamerule random_tick_speed is now set to: 0\n',
                                  'Unknown or incomplete command from an earlier operation\n')
        server.disable_random_ticks()
        self.assertEqual(state['commands'],[
            'execute in minecraft:overworld run gamerule minecraft:random_tick_speed 0'])
        self.assertFalse(hasattr(server,'flush'))

    def test_unknown_command_is_not_mistaken_for_positive_acknowledgement(self):
        server,_=self.console('[12:26:21 INFO]: Unknown or incomplete command. See below for error\n')
        with self.assertRaisesRegex(ValueError,'command failed:.*gamerule'):
            server.disable_random_ticks()

    def test_stale_reply_and_unrelated_say_do_not_confirm_gamerule(self):
        previous='[12:26:21 INFO]: Gamerule random_tick_speed is now set to: 0\n'
        server,_=self.console('[12:26:21 INFO]: [Not Secure] [Server] DONE\n',previous)
        with patch.object(P.time,'monotonic',side_effect=[0,1,121]),patch.object(P.time,'sleep'),\
             self.assertRaises(TimeoutError):
            server.disable_random_ticks()

    def test_wrong_gamerule_value_does_not_pass(self):
        server,_=self.console('[12:26:21 INFO]: Gamerule random_tick_speed is now set to: 3\n')
        with patch.object(P.time,'monotonic',side_effect=[0,1,121]),patch.object(P.time,'sleep'),\
             self.assertRaises(TimeoutError):
            server.disable_random_ticks()

    def test_load_marker_rejects_command_echo_and_prefix_collision(self):
        pattern=P.Server.marker_pattern('TREE_LOADED_2_-1_0')
        self.assertIsNotNone(re.search(pattern,'[12:26:21 INFO]: [Not Secure] [Server] TREE_LOADED_2_-1_0\n'))
        self.assertIsNotNone(re.search(pattern,'[12:26:21 INFO]: [Server] TREE_LOADED_2_-1_0\n'))
        self.assertIsNone(re.search(pattern,'execute if loaded -16 0 0 run say TREE_LOADED_2_-1_0<--[HERE]\n'))
        self.assertIsNone(re.search(pattern,'[12:26:21 INFO]: [Server] TREE_LOADED_2_-1_00\n'))

    def load_console(self, omit=None):
        server,state=self.console()
        def send(command):
            state['commands'].append(command)
            if ' if loaded ' in command:
                token=command.split(' run say ')[-1]
                if token!=omit:
                    state['text']+='[12:26:21 INFO]: [Not Secure] [Server] '+token+'\n'
            elif command.startswith('say '):
                state['text']+='[12:26:21 INFO]: [Server] '+command[4:]+'\n'
        server.send=send
        return server,state

    def test_runtime_barrier_checks_each_requested_chunk(self):
        server,state=self.load_console()
        with patch.object(P.time,'sleep'):
            result=server.load([(-1,0),(0,0)],'test')
        self.assertEqual(result,[[-1,0],[0,0]])
        self.assertEqual(sum(' if loaded ' in c for c in state['commands']),2)
        self.assertFalse(any('save-all' in c for c in state['commands']))

    def test_missing_one_loaded_chunk_fails_before_unloading(self):
        server,state=self.load_console(omit='TREE_LOADED_2_0_0')
        with patch.object(P.time,'monotonic',side_effect=itertools.count()),patch.object(P.time,'sleep'),\
             self.assertRaisesRegex(ValueError,'load barrier timed out'):
            server.load([(-1,0),(0,0)],'test',timeout=2)
        self.assertFalse(any('remove all' in c for c in state['commands']))

    def test_failed_stop_is_not_a_read_barrier(self):
        nbt=SimpleNamespace(read_chunk_nbt=Mock())
        for phase in ({'normal_stop':False,'process_exit_code':0},
                      {'normal_stop':True,'process_exit_code':1},
                      {'normal_stop':True,'process_exit_code':False}):
            with self.assertRaises(ValueError):
                P.stopped_roots(phase,Path('unused'),[(0,0)],nbt)
        nbt.read_chunk_nbt.assert_not_called()


class LifecycleTests(unittest.TestCase):
    def harness(self, root, *, stop_failure=None, corrupt=False, tamper=False, missing=False):
        recorder={'active':None,'instances':[], 'reads':[], 'loaded':set()}
        village_centers={P.VILLAGES[0]:(64,0),P.VILLAGES[1]:(128,0)}
        class FakeServer:
            def __init__(self, jar, folder, log):
                assert recorder['active'] is None
                self.number=len(recorder['instances'])+1
                self.jar=jar;self.folder=folder;self.log=log;self.loads=[]
                log.write_text('fake server log\n')
                recorder['instances'].append(self);recorder['active']=self
            def wait(self,*args,**kwargs): pass
            def disable_random_ticks(self): pass
            def locate(self, kind, target, x, z):
                if target in village_centers:
                    a,b=village_centers[target];return a*16,b*16
                return P.FORESTS.index(target)*320,0
            def load(self,chunks,label):
                selected=sorted(set(map(tuple,chunks)))
                recorder['loaded'].update(selected);self.loads.append((label,selected))
                return [list(p) for p in selected]
            def stop(self):
                if stop_failure==self.number:raise ValueError('server failed normal stop')
                recorder['active']=None
                if tamper and self.number==1:
                    (self.folder/'world/datapacks/NeverOverworld.zip').write_bytes(b'changed')
                return 0
            def close(self): recorder['active']=None
        def read(region,cx,cz):
            assert recorder['active'] is None, 'attempt to read a live region'
            assert (cx,cz) in recorder['loaded'], 'read unrequested chunk'
            if missing and (cx,cz)==(0,0):raise FileNotFoundError('missing saved chunk')
            recorder['reads'].append((len(recorder['instances']),cx,cz))
            changes={(cx*16+7,120,cz*16+7):'minecraft:oak_log',
                     (cx*16+7,121,cz*16+7):'minecraft:oak_leaves',
                     (cx*16+8,120,cz*16+7):'minecraft:water'}
            doc=fixture(changes,cx,cz)
            if corrupt and (cx,cz)==(0,0):doc['Status']='minecraft:features'
            for target,center in village_centers.items():
                if center==(cx,cz):
                    doc['structures']={'starts':{target:{'id':target,'Children':[
                        {'BB':{'$int_array':[cx*16,129,0,cx*16+60,140,15]}}]}}}
            return doc
        jar=root/'server.jar';jar.write_bytes(b'unchanged jar')
        pack=root/'pack.zip';pack.write_bytes(b'unchanged pack')
        return FakeServer,SimpleNamespace(read_chunk_nbt=read),recorder,jar,pack

    def test_two_normal_stops_precede_all_nbt_reads_and_final_audit(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            fake,nbt,record,jar,pack=self.harness(root)
            with patch.object(P,'Server',fake):
                plan,region=P.generate(root,jar,pack,root,nbt,'a'*40)
            self.assertEqual(len(record['instances']),2)
            self.assertEqual(record['instances'][0].folder,record['instances'][1].folder)
            self.assertEqual(record['instances'][0].jar,record['instances'][1].jar)
            self.assertEqual({r[0] for r in record['reads']},{1,2})
            self.assertTrue(all(p['normal_stop'] for p in plan['phases']))
            self.assertEqual(plan['source_sha'],'a'*40)
            result=P.audit(plan,region,root,nbt)
            self.assertTrue(result['natural_observation_pass'])
            self.assertFalse(result['production_ready'])
            self.assertTrue(result['village_visual_review_required'])
            self.assertTrue(result['saved_evidence_after_normal_stops'])

    def test_first_stop_failure_never_restarts_or_reads(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);fake,nbt,record,jar,pack=self.harness(root,stop_failure=1)
            with patch.object(P,'Server',fake),self.assertRaisesRegex(ValueError,'normal stop'):
                P.generate(root,jar,pack,root,nbt)
            self.assertEqual(len(record['instances']),1)
            self.assertEqual(record['reads'],[])
            plan=json.loads((root/'tree-village-plan.json').read_text())
            self.assertFalse(plan['normal_stop'])
            self.assertFalse(plan['phases'][0]['normal_stop'])

    def test_second_stop_failure_cannot_produce_final_acceptance(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);fake,nbt,record,jar,pack=self.harness(root,stop_failure=2)
            with patch.object(P,'Server',fake),self.assertRaisesRegex(ValueError,'normal stop'):
                P.generate(root,jar,pack,root,nbt)
            self.assertEqual({r[0] for r in record['reads']},{1})
            plan=json.loads((root/'tree-village-plan.json').read_text())
            self.assertFalse(plan['normal_stop'])
            with self.assertRaises(ValueError):P.audit(plan,Path('unused'),root,nbt)
            self.assertFalse((root/'tree-village-natural.json').exists())

    def test_persisted_nonfull_is_rejected_before_phase_two(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);fake,nbt,record,jar,pack=self.harness(root,corrupt=True)
            with patch.object(P,'Server',fake),self.assertRaisesRegex(ValueError,'not FULL'):
                P.generate(root,jar,pack,root,nbt)
            self.assertEqual(len(record['instances']),1)
            self.assertFalse(json.loads((root/'tree-village-plan.json').read_text())['normal_stop'])

    def test_missing_saved_chunk_is_not_treated_as_air(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);fake,nbt,record,jar,pack=self.harness(root,missing=True)
            with patch.object(P,'Server',fake),self.assertRaises(FileNotFoundError):
                P.generate(root,jar,pack,root,nbt)
            self.assertEqual(len(record['instances']),1)

    def test_restart_rejects_changed_datapack_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);fake,nbt,record,jar,pack=self.harness(root,tamper=True)
            with patch.object(P,'Server',fake),self.assertRaisesRegex(ValueError,'binaries changed'):
                P.generate(root,jar,pack,root,nbt)
            self.assertEqual(len(record['instances']),1)
            self.assertEqual(pack.read_bytes(),b'unchanged pack')
            self.assertEqual((record['instances'][0].folder/'world/datapacks/NeverOverworld.zip').read_bytes(),b'changed')

    def test_aggregate_normal_stop_does_not_hide_missing_phase(self):
        plan={'schema':2,'normal_stop':True,'process_exit_code':0,'phases':[]}
        nbt=SimpleNamespace(read_chunk_nbt=Mock())
        with self.assertRaisesRegex(ValueError,'stopped-world phases'):
            P.audit(plan,Path('unused'),Path('unused'),nbt)
        nbt.read_chunk_nbt.assert_not_called()


if __name__=='__main__':unittest.main(verbosity=2)
