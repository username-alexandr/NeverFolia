#!/usr/bin/env python3
"""Synthetic source contracts. Actual native behavior is tested separately in Folia."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import nevernether_dnt_r6 as mod
from nevernether_source_inputs import Archive, inspect_dependencies, resource_path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('input_fixtures',ROOT/'scripts/test-never-nether-source-inputs.py')
fixtures=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fixtures;spec.loader.exec_module(fixtures)


def taverns():
    ids=['nova_structures:tavern_'+x for x in ('acacia','birch','cherry','dark_oak','desert','jungle','mangrove','oak','pale','snowy','spruce','swamp')]
    return {'pools':[{'rolls':1,'entries':[{'weight':i+1,'condition':{'predicate':{'location':{'structures':val}}}} for i,val in enumerate([ids,*ids])]}]}


class TransformTests(unittest.TestCase):
    def test_projectile_function_is_one_native_operation(self):
        for n in (1,2,3):
            out=mod.transform_function('ghasted_fireball_'+str(n),'irrelevant: caller verifies exact hash')
            self.assertEqual([s for s in out.splitlines() if not s.startswith('#')],['neverfolia:dnt fireball_'+str(n)])
    def test_unknown_function_rejected(self):
        with self.assertRaises(ValueError):mod.transform_function('other','')
    def test_unrecognized_fireball_level_rejected(self):
        with self.assertRaises(ValueError):mod.transform_function('ghasted_fireball_4','')
    def test_one_tick_regeneration_not_replaced_by_one_second_effect(self):
        s='data modify entity @s active_effects append value {id:"minecraft:regeneration",amplifier:6,duration:1,show_particles:0b}'
        self.assertEqual(mod.transform_function('hydro_veil_heal',s),'neverfolia:dnt regenerate')
    def test_changed_healing_contract_rejected(self):
        with self.assertRaises(ValueError):mod.transform_function('hydro_veil_heal','effect give @s regeneration')
    def test_missing_or_duplicate_expected_action_rejected(self):
        for s in ('','item replace entity @s saddle with air\nitem replace entity @s saddle with air'):
            with self.assertRaises(ValueError):mod.transform_function('jockey/make_drowned_into_jockey',s)
    def test_jockey_ride_command_retained(self):
        raw='execute summon zombie_nautilus run ride @n[type=drowned] mount @s\nitem replace entity @s saddle with air\n'
        out=mod.transform_function('jockey/make_drowned_into_jockey',raw)
        self.assertEqual(out.splitlines()[0],raw.splitlines()[0]);self.assertIn('neverfolia:dnt clear_saddle',out)
    def test_fixed_function_call_targets_retained(self):
        raw='\n'.join('execute if predicate test:x run function nova_structures:quest/add_trade_lv'+str(i) for i in range(2,6))
        out=mod.transform_function('quest/saddle_trade_checker',raw)
        for i in range(2,6):self.assertIn('neverfolia:dnt call_trade_'+str(i),out)
    def test_optional_tags_preserve_loot_branch_weights_and_source(self):
        value=taverns();old=copy.deepcopy(value);out,tags=mod.optional_locations(value)
        self.assertEqual(value,old);self.assertEqual(len(tags),13)
        self.assertEqual([e['weight'] for e in out['pools'][0]['entries']],list(range(1,14)))
        for raw in tags.values():
            for v in json.loads(raw)['values']:self.assertFalse(v['required'])
    def test_no_structure_definition_is_created(self):
        _,tags=mod.optional_locations(taverns())
        self.assertTrue(all('/tags/worldgen/structure/' in str(p) for p in tags))
    def test_incomplete_tavern_contract_rejected(self):
        v=taverns();v['pools'][0]['entries'].pop()
        with self.assertRaises(ValueError):mod.optional_locations(v)
    def test_unknown_tavern_rejected(self):
        v=taverns();v['pools'][0]['entries'][0]['condition']['predicate']['location']['structures'].append('other:new')
        with self.assertRaises(ValueError):mod.optional_locations(v)
    def test_minion_limit_keeps_inversion_and_exact_threshold(self):
        term={'condition':'minecraft:entity_scores','entity':'this','scores':{'dnt_boss_minion':{'min':7}}}
        v={'condition':'minecraft:inverted','term':term};before=copy.deepcopy(v);out=mod.local_minion_limit(v)
        self.assertEqual(v,before);self.assertEqual(out['condition'],'minecraft:inverted');self.assertIn(mod.LIMIT_TAG,out['term']['predicate']['nbt'])
    def test_changed_minion_threshold_rejected(self):
        with self.assertRaises(ValueError):mod.local_minion_limit({'condition':'minecraft:entity_scores','entity':'this','scores':{'dnt_boss_minion':{'min':8}}})
    def test_wrong_archive_fails_before_mutation(self):
        archive=SimpleNamespace(sha256='0'*64,entries={});before=copy.deepcopy(vars(archive))
        with self.assertRaises(ValueError):mod.apply_dnt(archive)
        self.assertEqual(vars(archive),before)
    def test_corrupt_contract_fails_before_mutation(self):
        archive=SimpleNamespace(sha256=mod.SOURCE_SHA,entries={});before=copy.deepcopy(vars(archive))
        with self.assertRaises(ValueError):mod.apply_dnt(archive)
        self.assertEqual(vars(archive),before)
    def test_unsafe_loot_function_rejected(self):
        for extra in ({'function':'minecraft:exploration_map'},{'random_sequence':'test:global'},{'condition':'minecraft:reference','name':'test:unknown'}):
            raw=json.dumps(extra).encode();a=SimpleNamespace(entries={PurePosixPath('data/test/loot_table/x.json'):raw})
            p={'trade_loot_hashes':{'data/test/loot_table/x.json':hashlib.sha256(raw).hexdigest()}}
            with self.assertRaises(ValueError):mod.validate_trade_loot(a,p)
    def test_scalar_trade_loot_is_accepted(self):
        raw=b'{"function":"minecraft:set_count","count":14}';a=SimpleNamespace(entries={PurePosixPath('data/test/loot_table/x.json'):raw})
        mod.validate_trade_loot(a,{'trade_loot_hashes':{'data/test/loot_table/x.json':hashlib.sha256(raw).hexdigest()}})


class DependencyTests(fixtures.InputsTests):
    # Only R6 methods are selected below, not the inherited suite a second time.
    def test_r6_physical_alias_pool_is_retained_with_targets(self):
        f=fixtures.base_files();root=f['data/test/worldgen/structure/tower.json']
        root['pool_aliases']=[{'type':'minecraft:direct','alias':'test:start','target':'test:resolved'}]
        f['data/test/worldgen/template_pool/resolved.json']={'fallback':'minecraft:empty','elements':[]}
        r=self.inspect(f)
        self.assertTrue(r['source_dependency_preflight_passed'])
        self.assertIn('data/test/worldgen/template_pool/start.json',r['selected_files']);self.assertIn('data/test/structure/start.nbt',r['selected_files'])
        self.assertIn('data/test/worldgen/template_pool/resolved.json',r['selected_files'])
    def test_r6_optional_external_structure_is_not_imported_even_when_in_archive(self):
        f=fixtures.base_files();f['data/test/worldgen/structure/excluded.json']={'type':'mod:unsupported'}
        f['data/test/structure/start.nbt']=fixtures.template(blocks=[{'nbt':{'id':'minecraft:chest','LootTable':'test:loot'}}])
        f['data/test/loot_table/loot.json']={'condition':'minecraft:entity_properties','predicate':{'location':{'structures':'#test:optional'}}}
        f['data/test/tags/worldgen/structure/optional.json']={'values':[{'id':'test:excluded','required':False}]}
        a=self.archive(f);a.optional_external_structures.add('test:excluded');r=inspect_dependencies(a,['test:tower'])
        self.assertTrue(r['source_dependency_preflight_passed']);self.assertNotIn('data/test/worldgen/structure/excluded.json',r['selected_files'])
    def test_r6_fixed_bridge_function_dependencies_are_traced(self):
        f=fixtures.base_files();f['data/test/structure/start.nbt']=fixtures.template(entities=[{'nbt':{'id':'minecraft:zombie','components':{'minecraft:enchantments':{'test:e':1}}}}])
        f['data/test/enchantment/e.json']={'effects':[{'type':'minecraft:run_function','function':'test:call'}]}
        f['data/test/function/call.mcfunction']=b'neverfolia:dnt call_trade_2\n'
        f['data/nova_structures/function/quest/add_trade_lv2.mcfunction']=b'neverfolia:dnt loot_emeralds\n'
        f['data/nova_structures/loot_table/villagers/villager_emerald_counts.json']={'pools':[]}
        r=self.inspect(f);self.assertTrue(r['source_dependency_preflight_passed']);self.assertIn('data/nova_structures/loot_table/villagers/villager_emerald_counts.json',r['selected_files'])
    def test_r6_scalar_optimization_keeps_block_entity_dependencies(self):
        f=fixtures.base_files();f['data/test/structure/start.nbt']=fixtures.template(blocks=[{'state':0,'pos':[0,0,0],'nbt':{'id':'minecraft:jigsaw','pool':'test:missing'}}])
        r=self.inspect(f);self.assertFalse(r['source_dependency_preflight_passed']);self.assertEqual(r['missing_required_references'][0][1],'test:missing')


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(TransformTests)
    for name in unittest.defaultTestLoader.getTestCaseNames(DependencyTests):
        if name.startswith('test_r6_'):suite.addTest(DependencyTests(name))
    result=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not result.wasSuccessful())
