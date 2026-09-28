import copy,unittest
from build_carts import diff
from snow_contract import compare
class SnowContractTests(unittest.TestCase):
    def model(self,layers='1',y=4,block='minecraft:snow'):
        return {'blocks':{(1,y,2):{'state':{'Name':(8,block),'Properties':(10,{'layers':(8,layers)})}}}}
    def check(self,a,b,biome='snowy'):
        return compare(a,b,biome,diff(a,b))
    def test_identical_recorded_as_identical(self):
        a=self.model();self.assertTrue(self.check(a,copy.deepcopy(a))['exact_serialized_model_equal'])
    def test_allowed_decoration_not_labeled_identical(self):
        a=self.model('1');b=self.model('2');r=self.check(a,b)
        self.assertFalse(r['exact_serialized_model_equal']);self.assertEqual(len(r['roof_snow_layer_variations']),1)
    def test_no_model_mutation(self):
        a=self.model('1');b=self.model('2');snap=(copy.deepcopy(a),copy.deepcopy(b));self.check(a,b);self.assertEqual((a,b),snap)
    def test_three_layers_rejected(self):
        with self.assertRaises(ValueError):self.check(self.model('1'),self.model('3'))
    def test_lower_snow_rejected(self):
        with self.assertRaises(ValueError):self.check(self.model('1',3),self.model('2',3))
    def test_other_biome_rejected(self):
        with self.assertRaises(ValueError):self.check(self.model('1'),self.model('2'),'pale')
    def test_non_snow_rejected(self):
        with self.assertRaises(ValueError):self.check(self.model('1',block='minecraft:stone'),self.model('2',block='minecraft:stone'))
    def test_block_removal_rejected(self):
        with self.assertRaises(ValueError):self.check(self.model(),{'blocks':{}})
    def test_workstation_change_rejected(self):
        a=self.model();b=copy.deepcopy(a);b['blocks'][(1,4,2)]['state']['Name']=(8,'minecraft:brewing_stand')
        with self.assertRaises(ValueError):self.check(a,b)
    def test_jigsaw_nbt_change_rejected(self):
        a=self.model();b=copy.deepcopy(a);b['blocks'][(1,4,2)]['nbt']=(10,{'pool':(8,'minecraft:empty')})
        with self.assertRaises(ValueError):self.check(a,b)
    def test_size_change_rejected(self):
        a=self.model();a['size']=(9,(3,[5,5,5]));b=copy.deepcopy(a);b['size']=(9,(3,[5,6,5]))
        with self.assertRaises(ValueError):self.check(a,b)
    def test_extra_state_property_rejected(self):
        a=self.model();b=copy.deepcopy(a);b['blocks'][(1,4,2)]['state']['Properties'][1]['waterlogged']=(8,'true')
        with self.assertRaises(ValueError):self.check(a,b)
if __name__=='__main__':unittest.main(verbosity=2)
