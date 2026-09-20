#!/usr/bin/env python3
"""Synthetic regressions for the saved-world observer, not generated-world evidence."""
import copy
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

if __name__=='__main__':unittest.main(verbosity=2)
