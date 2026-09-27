#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import sys
import unittest
import review

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('r395_launch_tests',ROOT/'qa/field-r395/run_water.py')
water=importlib.util.module_from_spec(spec)
spec.loader.exec_module(water)
RUN='c4262a0b-f0bf-4998-901e-cf72253b64f1'

class LaunchTests(unittest.TestCase):
    def test_only_one_reviewed_agent(self):
        command=water.launch_command('/x/server.jar','/x/observer.jar',RUN,['-Dexample=true'])
        self.assertEqual([x for x in command if x.startswith('-javaagent:')],['-javaagent:/x/observer.jar'])
        self.assertEqual(command[-3:],['-jar','/x/server.jar','--nogui'])
        self.assertIn('-DPaper.WorkerThreadCount=1',command)
        self.assertIn('-XX:ActiveProcessorCount=4',command)
        self.assertIn('-Dneverfolia.waterAuditRunId='+RUN,command)
    def test_extra_agent_rejected(self):
        with self.assertRaises(ValueError):water.launch_command('/a','/b',RUN,['-javaagent:/other'])
    def test_extra_executable_rejected(self):
        with self.assertRaises(ValueError):water.launch_command('/a','/b',RUN,['-jar','other.jar'])
    def test_duplicate_run_rejected(self):
        with self.assertRaises(ValueError):water.launch_command('/a','/b',RUN,['-Dneverfolia.waterAuditRunId=other'])
    def test_missing_run_rejected(self):
        with self.assertRaises(ValueError):water.launch_command('/a','/b','',[])
    def test_nonstring_extra_rejected(self):
        with self.assertRaises(ValueError):water.launch_command('/a','/b',RUN,[None])
    def test_paths_remain_single_arguments(self):
        command=water.launch_command('/space name/server.jar','/space name/observer.jar',RUN,[])
        self.assertIn('-javaagent:/space name/observer.jar',command)
        self.assertEqual(command[-2],'/space name/server.jar')

class GeometryTests(unittest.TestCase):
    def test_full_chunk_face(self):
        data=review.components([[15,y,z] for y in range(40,60) for z in range(16)],'x')
        self.assertEqual(len(data),1)
        self.assertEqual((data[0]['faces'],data[0]['width'],data[0]['height']),(320,16,20))
        self.assertEqual(data[0]['rectangle_occupancy'],1.0)
    def test_transpose_z_face(self):
        data=review.components([[x,y,15] for y in range(40,60) for x in range(16)],'z')
        self.assertEqual((data[0]['faces'],data[0]['width'],data[0]['height']),(320,16,20))
    def test_disconnected_components(self):
        data=review.components([[15,1,0],[15,1,1],[15,5,5]],'x')
        self.assertEqual([x['faces'] for x in data],[2,1])
    def test_l_shape_not_rectangle(self):
        data=review.components([[15,0,0],[15,0,1],[15,1,1]],'x')
        self.assertEqual(data[0]['rectangle_occupancy'],.75)
    def test_empty_not_wall(self):self.assertEqual(review.components([],'x'),[])
    def test_unreadable_mask_not_air(self):self.assertIsNone(review.cell({},(-3217,46,-3398)))
    def test_mask_index_at_negative_coordinates(self):
        size=640*256
        before=bytearray(size);after=bytearray(size)
        x,y,z=-3217,46,-3398
        column=((z&15)<<4)|(x&15);idx=((y+511)<<8)|column
        before[idx]=1;after[idx]=3
        masks={(x//16,z//16):(-511,128,tuple(range(256)),before,after)}
        self.assertEqual(review.cell(masks,(x,y,z)),(1,3,column))
        self.assertIsNone(review.cell(masks,(x,129,z)))
    def test_structure_box_contains_camera(self):
        row={'key':'test:dungeon','chunk':[-202,-213],'data':{'Children':[{'BB':{'$int_array':[-3220,40,-3400,-3210,50,-3390]},'pool_element':{'location':'test:room'}}]}}
        value=review.compact_structure(row)
        self.assertEqual(value['template_counts'],{'test:room':1})
        self.assertEqual(value['pieces_containing_camera']['(-3217, 46, -3398)'],1)
        self.assertEqual(value['pieces_containing_camera']['(-3259, 46, -3397)'],0)

if __name__=='__main__':unittest.main(verbosity=2)
