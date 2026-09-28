#!/usr/bin/env python3
import copy,unittest
import combine_content as c

class PaletteTests(unittest.TestCase):
    def root(self,block_name='minecraft:jigsaw',explicit_id=None):
        n={'name':(8,'test:input'),'target':(8,'test:output'),'pool':(8,'minecraft:empty')}
        if explicit_id is not None:n['id']=(8,explicit_id)
        return {'palette':(9,(10,[{'Name':(8,block_name)}])), 'blocks':(9,(10,[{'pos':(9,(3,[1,2,3])),'state':(3,0),'nbt':(10,n)}]))}
    def test_missing_optional_id_is_still_jigsaw(self):self.assertEqual(len(list(c.joints(self.root()))),1)
    def test_explicit_id(self):self.assertEqual(len(list(c.joints(self.root(explicit_id='minecraft:jigsaw')))),1)
    def test_nonjigsaw_not_selected_by_nbt(self):self.assertEqual(list(c.joints(self.root('minecraft:stone','minecraft:jigsaw'))),[])
    def test_invalid_palette_index(self):
        root=self.root();root['blocks'][1][1][0]['state']=(3,5)
        with self.assertRaises(ValueError):list(c.joints(root))
    def test_contradictory_id(self):
        with self.assertRaises(ValueError):list(c.joints(self.root(explicit_id='minecraft:chest')))
    def test_missing_target(self):
        root=self.root();del root['blocks'][1][1][0]['nbt'][1]['target']
        with self.assertRaises(ValueError):list(c.joints(root))
    def test_multiple_palettes_refused(self):
        root=self.root();root['palettes']=(9,(9,[]))
        with self.assertRaises(ValueError):list(c.joints(root))

class ChildTests(unittest.TestCase):
    def setUp(self):
        self.target='nova_structures:tavern_villager_mangrove'
        self.rows=[{'template':'authored-child.nbt','names':[self.target],
                    'entities':(9,(10,[{'nbt':(10,{'id':(8,'minecraft:villager')})}]))}]
    def test_already_valid_target_requires_no_edit(self):
        before=copy.deepcopy(self.rows)
        self.assertEqual(c.validate_compatibility(self.target,{self.target},self.rows),['authored-child.nbt'])
        self.assertEqual(self.rows,before)
    def test_missing_target_is_not_silently_replaced(self):
        with self.assertRaises(ValueError):c.validate_compatibility('nova_structures:missing',{self.target},self.rows)
    def test_empty_matching_template_rejected(self):
        self.rows[0]['entities']=(9,(10,[]))
        with self.assertRaises(ValueError):c.validate_compatibility(self.target,{self.target},self.rows)
    def test_wrong_entity_rejected(self):
        self.rows[0]['entities'][1][1][0]['nbt'][1]['id']=(8,'minecraft:pig')
        with self.assertRaises(ValueError):c.validate_compatibility(self.target,{self.target},self.rows)
    def test_name_union_without_corresponding_row_rejected(self):
        with self.assertRaises(ValueError):c.validate_compatibility(self.target,{self.target},[])
if __name__=='__main__':unittest.main(verbosity=2)
