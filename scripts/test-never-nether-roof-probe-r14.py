#!/usr/bin/env python3
"""Synthetic R14 FULL/ceiling evidence validation. No simulated Minecraft PASS."""
import copy,gzip,hashlib,importlib.util,json,struct,tempfile,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('r14_compare',ROOT/'qa/nevernether-r14/compare-roof-r14.py');C=importlib.util.module_from_spec(s);s.loader.exec_module(C)
def write(p,o):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o))
def fixture(w,reverse=False):
 root=w/'plugins/NN-STAGE-R8-QA';root.mkdir(parents=True)
 coords=[[64,0],[65,0]]
 if reverse:coords.reverse()
 write(root/'states.json',{'0':'minecraft:air','1':'minecraft:bedrock','2':'minecraft:lava[level=0]','3':'minecraft:cave_air','4':'minecraft:crimson_stem[axis=y]'})
 rows=[{'entry':0,'file':'fixture','sha256':'1'*64}];blob=json.dumps(rows,sort_keys=True,separators=(',',':')).encode();h=hashlib.sha256(blob).hexdigest()
 write(w/'runtime-inventory.json',{'files':rows,'payload_sha256':h,'manifest_sha256':'b'*64})
 write(w/'run-evidence.json',{'schema':2,'stage':'completed','seed':1,'process_exit_code':0,'forced_stop':False,'runtime_unchanged':True,'inputs_unchanged':True,'pack_sha256':'a'*64,'qa_plugin_sha256':'c'*64,'classpath_manifest_sha256':'b'*64,'java_executable_sha256':'d'*64,'runtime_payload_sha256':h,'jvm_flags':[]})
 report={'schema':1,'probe':'NN-ROOF-R14','stage':'completed','seed':1,'simulation_frozen_before_probe':True,'boundary_checks':0,'boundary_failures':[],'plan':{'seed':1,'chunks':coords},'coverage_sha256':hashlib.sha256('64,0\n65,0\n'.encode()).hexdigest(),'target_FULL_requests':4,'state_dictionary_sha256':C.digest(root/'states.json'),'observations':[]}
 for phase in ('full','settled'):
  for x,z in coords:
   a=np.zeros(C.CELLS,dtype='>u4');a[(512+128)*256:(513+128)*256]=1
   p=root/phase/f'{x}_{z}.bin.gz';p.parent.mkdir(exist_ok=True);p.write_bytes(gzip.compress(struct.pack('>6i',0x4e4e5238,1,x,z,-128,656)+a.tobytes(),mtime=0))
   m=root/phase/f'{x}_{z}.substrate.nbt';m.write_bytes(b'fixture metadata not parsed as real NBT')
   report['observations'].append({'phase':phase,'x':x,'z':z,'status':'minecraft:full','simulation_frozen':True,'capture_protocol':'immutable-section-copy-r11','capture_status_before':'minecraft:full','capture_status_after':'minecraft:full','file':phase+'/'+p.name,'bytes':p.stat().st_size,'sha256':C.digest(p),'metadata_file':phase+'/'+m.name,'metadata_bytes':m.stat().st_size,'metadata_sections':41,'metadata_sha256':C.digest(m),'roof_non_bedrock':0,'padding_non_air':0})
 write(root/'report.json',report);return report
class RoofEvidenceTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.r=Path(self.tmp.name);self.a=self.r/'a';self.b=self.r/'b';self.ra=fixture(self.a);self.rb=fixture(self.b,True)
 def tearDown(self):self.tmp.cleanup()
 def save(self):write(self.a/'plugins/NN-STAGE-R8-QA/report.json',self.ra)
 def reject(self):
  with self.assertRaises((ValueError,KeyError,OSError,TypeError)):C.compare(self.a,self.b)
 def voxel(self,y,state):
  row=self.ra['observations'][0];p=self.a/'plugins/NN-STAGE-R8-QA'/row['file'];raw=bytearray(gzip.decompress(p.read_bytes()));struct.pack_into('>I',raw,24+(y+128)*256*4,state);p.write_bytes(gzip.compress(raw,mtime=0));row['bytes']=p.stat().st_size;row['sha256']=C.digest(p);self.save()
 def test_equal_does_not_promote_release(self):
  r=C.compare(self.a,self.b);self.assertTrue(r['block_equality']);self.assertTrue(r['roof_and_padding_pass']);self.assertFalse(r['release_ready'])
 def test_real_roof_hole_detected_despite_zero_claimed_errors(self):self.voxel(512,0);self.reject()
 def test_lava_in_padding_detected_despite_zero_claimed_errors(self):self.voxel(513,2);self.reject()
 def test_uppermost_padding_layer_checked(self):self.voxel(527,4);self.reject()
 def test_lava_below_roof_not_normalized(self):self.voxel(400,2);self.assertFalse(C.compare(self.a,self.b)['block_equality'])
 def test_air_variants_not_normalized(self):self.voxel(100,3);self.assertEqual(C.compare(self.a,self.b)['cross_order']['full']['different_blocks'],1)
 def test_roof511_instead_of512_rejected(self):self.voxel(511,1);self.voxel(512,0);self.reject()
 def test_old_protocol_not_accepted(self):self.ra['probe']='NN-FULL-R13';self.save();self.reject()
 def test_mutation_qa_not_order_acceptance(self):self.ra['plan']['test_mutations']=True;self.save();self.reject()
 def test_failed_boundary_assertions_rejected(self):self.ra['boundary_failures']=['failed'];self.save();self.reject()
 def test_64_section_metadata_rejected(self):self.ra['observations'][0]['metadata_sections']=64;self.save();self.reject()
 def test_lost_metadata_rejected(self):(self.a/'plugins/NN-STAGE-R8-QA/full/64_0.substrate.nbt').unlink();self.reject()
 def test_incomplete_observations_rejected(self):self.ra['observations'].pop();self.save();self.reject()
 def test_duplicate_observations_rejected(self):self.ra['observations'].append(self.ra['observations'][0]);self.save();self.reject()
 def test_status_change_rejected(self):self.ra['observations'][0]['capture_status_before']='minecraft:spawn';self.save();self.reject()
 def test_unfrozen_report_rejected(self):self.ra['simulation_frozen_before_probe']=False;self.save();self.reject()
 def test_unfrozen_observation_rejected(self):self.ra['observations'][0]['simulation_frozen']=False;self.save();self.reject()
 def test_wrong_order_rejected(self):self.ra['plan']['chunks'].reverse();self.save();self.reject()
 def test_different_input_rejected(self):
  p=self.a/'run-evidence.json';o=json.loads(p.read_text());o['pack_sha256']='f'*64;write(p,o);self.reject()
 def test_bad_runtime_inventory_rejected(self):
  p=self.a/'runtime-inventory.json';o=json.loads(p.read_text());o['files'][0]['file']='changed';write(p,o);self.reject()
 def test_partial_or_forced_run_rejected(self):
  p=self.a/'run-evidence.json';o=json.loads(p.read_text());o['forced_stop']=True;write(p,o);self.reject()
 def test_comparator_accepts_same_order_only_explicitly(self):
  self.ra['plan']['chunks'].reverse();self.save();self.assertTrue(C.compare(self.a,self.b,'same')['block_equality'])
 def test_bad_bounds_rejected(self):
  p=self.r/'bad.gz';p.write_bytes(gzip.compress(struct.pack('>6i',0x4e4e5238,1,64,0,-128,1024)+bytes(C.CELLS*4),mtime=0))
  with self.assertRaises(ValueError):C.snapshot(p,(64,0))
 def test_non_roof_plant_differences_not_filtered(self):self.voxel(500,4);self.assertFalse(C.compare(self.a,self.b)['block_equality'])
if __name__=='__main__':unittest.main(verbosity=2)
