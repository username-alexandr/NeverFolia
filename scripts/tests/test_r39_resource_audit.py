#!/usr/bin/env python3
"""Small in-memory graphs; no server/datapack substitutions or network access."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'audit-neveroverworld-r39-resources.py'
spec = importlib.util.spec_from_file_location('r39audit', path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def direct(a, b):
    return {'type': 'minecraft:direct', 'alias': 'test:' + a, 'target': 'test:' + b}


def random(a, targets):
    return {'type': 'minecraft:random', 'alias': 'test:' + a,
            'targets': [{'weight': 1, 'data': 'test:' + v} for v in targets]}


def group(*choices):
    return {'type': 'minecraft:random_group',
            'groups': [{'weight': 1, 'data': choice} for choice in choices]}


def single(name):
    return {'element_type': 'minecraft:single_pool_element', 'location': 'test:' + name,
            'processors': 'minecraft:empty', 'projection': 'rigid'}


class Graph:
    def __init__(self):
        self.data = {k: {} for k in ('set', 'structure', 'pool', 'template', 'placed_feature', 'configured_feature')}
        self.data['pool']['minecraft:empty'] = {'fallback': 'minecraft:empty', 'elements': []}

    def root(self, name, start, aliases=None):
        self.data['set']['test:' + name] = {'structures': [{'weight': 1, 'structure': 'test:' + name}]}
        self.data['structure']['test:' + name] = {'type': 'minecraft:jigsaw', 'start_pool': 'test:' + start,
                                                'pool_aliases': aliases or []}
        return self

    def pool(self, name, *templates, fallback='minecraft:empty'):
        self.data['pool']['test:' + name] = {'fallback': fallback,
            'elements': [{'weight': 1, 'element': single(t)} for t in templates] or
                        [{'weight': 1, 'element': {'element_type': 'minecraft:empty_pool_element'}}]}
        return self

    def template(self, name, *pools):
        self.data['template']['test:' + name] = ['test:' + p for p in pools]
        return self

    def audit(self):
        return m.Audit(self.data, lambda k, name: self.data[k][name]).run()


class AliasTests(unittest.TestCase):
    def test_identifier_default_namespace(self):
        self.assertEqual(m.rid('empty'), 'minecraft:empty')

    def test_invalid_identifier(self):
        for value in ('', None, 'test:A', 'a:b:c'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.rid(value)

    def test_correlated_groups_not_independent_choices(self):
        out = m.alias_contexts([group([direct('a','red'), direct('b','red')],
                                     [direct('a','blue'), direct('b','blue')])])
        self.assertEqual(len(out), 2)
        self.assertTrue(all(v['test:a'] == v['test:b'] for v in out))

    def test_independent_product(self):
        self.assertEqual(len(m.alias_contexts([random('a',['a1','a2','a3']), random('b',['b1','b2','b3','b4'])])),12)

    def test_trial_chamber_context_count(self):
        out = m.alias_contexts([group(*[[direct('ranged',t),direct('slow',t)] for t in ('skeleton','stray','poison')]),
                               random('melee',['zombie','husk','spider']),
                               random('small',['slime','cave_spider','silverfish','baby_zombie'])])
        self.assertEqual(len(out),36)

    def test_shrine_context_count(self):
        bindings=[random('a',['v'+str(i) for i in range(12)]),random('b',['b1','b2','b3']),
                  random('c',['c1','c2','c3','c4']),random('d',['d1']),random('e',['e1','e2','e3','e4'])]
        self.assertEqual(len(m.alias_contexts(bindings)),576)

    def test_duplicate_alias_even_identical_target_is_error(self):
        with self.assertRaises(ValueError):m.alias_contexts([direct('a','b'),direct('a','b')])

    def test_duplicate_in_one_random_alternative_is_error(self):
        with self.assertRaises(ValueError):m.alias_contexts([direct('a','b'),group([direct('a','c')],[direct('d','e')])])

    def test_context_cap_is_error_not_truncation(self):
        with self.assertRaises(ValueError):m.alias_contexts([random('a',['x','y','z'])],limit=2)

    def test_zero_weight_not_selected(self):
        binding=random('a',['x','y']);binding['targets'][1]['weight']=0
        self.assertEqual(m.alias_contexts([binding]),[{'test:a':'test:x'}])

    def test_all_zero_negative_and_bool_weights_rejected(self):
        for weight in (0,-1,True):
            with self.subTest(weight=weight),self.assertRaises(ValueError):m.weighted([{'data':'x','weight':weight}])

    def test_unknown_alias_type_fails(self):
        with self.assertRaises(ValueError):m.alias_contexts([{'type':'test:unknown'}])

    def test_self_alias_is_allowed(self):
        self.assertEqual(m.alias_contexts([direct('a','a')]),[{'test:a':'test:a'}])


class ClosureTests(unittest.TestCase):
    def test_basic_graph(self):
        self.assertTrue(Graph().root('r','p').pool('p','t').template('t').audit()['pass'])

    def test_missing_template_fails(self):
        r=Graph().root('r','p').pool('p','missing').audit()
        self.assertFalse(r['pass']);self.assertEqual(r['counts']['missing_templates'],1)

    def test_declared_alias_is_not_a_missing_pool(self):
        g=Graph().root('r','p',[direct('dynamic','target')]).pool('p','t').template('t','dynamic').pool('target')
        self.assertTrue(g.audit()['pass'])

    def test_alias_context_does_not_leak_between_roots(self):
        g=Graph().root('r1','p',[direct('dynamic','target')]).root('r2','p')
        g.pool('p','t').template('t','dynamic').pool('target');r=g.audit()
        self.assertFalse(r['pass']);self.assertEqual(r['missing'][0]['roots'],['test:r2'])

    def test_alias_lookup_is_exactly_one_hop(self):
        g=Graph().root('r','p',[direct('a','b'),direct('b','c')]).pool('p','t').template('t','a').pool('c')
        r=g.audit();self.assertFalse(r['pass']);self.assertEqual(r['missing'][0]['id'],'test:b')

    def test_fallback_is_not_alias_remapped(self):
        g=Graph().root('r','p',[direct('fallback','wrong')]).pool('p',fallback='test:fallback').pool('fallback')
        self.assertTrue(g.audit()['pass'])

    def test_missing_start_holder_cannot_be_rescued_by_alias(self):
        r=Graph().root('r','missing',[direct('missing','present')]).pool('present').audit()
        self.assertFalse(r['pass']);self.assertEqual(r['missing'][0]['id'],'test:missing')

    def test_center_missing_alias_target_uses_existing_holder(self):
        r=Graph().root('r','p',[direct('p','absent')]).pool('p').audit()
        self.assertTrue(r['pass']);self.assertEqual(len(r['center_alias_fallbacks']),1)

    def test_existing_center_alias_redirects_graph(self):
        self.assertTrue(Graph().root('r','p',[direct('p','other')]).pool('p','missing').pool('other').audit()['pass'])

    def test_random_alternative_missing_target_is_failure(self):
        g=Graph().root('r','p',[random('dynamic',['present','missing'])]).pool('p','t').template('t','dynamic').pool('present')
        r=g.audit();self.assertFalse(r['pass']);self.assertEqual(r['missing'][0]['context_count'],1)

    def test_group_correlation_avoids_impossible_combination(self):
        g=Graph().root('r','p',[group([direct('entry','red'),direct('end','red_end')],
                                     [direct('entry','blue'),direct('end','blue_end')])])
        g.pool('p','t').template('t','entry').pool('red','red_t').template('red_t','end')
        g.pool('blue','blue_t').template('blue_t','end').pool('red_end').pool('blue_end')
        r=g.audit();self.assertTrue(r['pass']);self.assertEqual(r['counts']['alias_contexts'],2)

    def test_cycles_terminate(self):
        self.assertTrue(Graph().root('r','p').pool('p','t',fallback='test:p').template('t','p').audit()['pass'])

    def test_no_roots_is_not_pass(self):self.assertFalse(Graph().audit()['pass'])

    def test_missing_structure_is_not_silently_skipped(self):
        g=Graph().root('r','p');del g.data['structure']['test:r'];r=g.audit()
        self.assertFalse(r['pass']);self.assertEqual(r['missing'][0]['kind'],'structure')

    def test_non_jigsaw_scope_is_explicit(self):
        g=Graph().root('r','p');g.data['structure']['test:r']['type']='minecraft:stronghold';r=g.audit()
        self.assertTrue(r['pass']);self.assertEqual(r['counts']['jigsaw_roots'],0)
        self.assertIn('outside',r['roots'][0]['reason'])

    def test_unknown_element_not_silently_skipped(self):
        g=Graph().root('r','p').pool('p')
        g.data['pool']['test:p']['elements'][0]['element']={'element_type':'test:unknown'}
        self.assertFalse(g.audit()['pass'])

    def test_noncanonical_empty_pool_is_failure(self):
        g=Graph().root('r','p').pool('p');g.data['pool']['test:p']['elements']=[]
        self.assertFalse(g.audit()['pass'])

    def test_nested_list_traversed(self):
        g=Graph().root('r','p').pool('p')
        g.data['pool']['test:p']['elements'][0]['element']={'element_type':'minecraft:list_pool_element','elements':[single('missing')]}
        self.assertFalse(g.audit()['pass'])

    def feature_graph(self):
        g=Graph().root('r','p').pool('p')
        g.data['pool']['test:p']['elements'][0]['element']={'element_type':'minecraft:feature_pool_element','feature':'test:feature'}
        return g

    def test_feature_reference_is_checked(self):
        r=self.feature_graph().audit()
        self.assertFalse(r['pass']);self.assertEqual(r['missing'][0]['kind'],'placed_feature')

    def test_configured_feature_does_not_satisfy_placed_holder(self):
        g=self.feature_graph();g.data['configured_feature']['test:feature']={}
        self.assertFalse(g.audit()['pass'])

    def test_placed_feature_does_not_need_same_named_configured_feature(self):
        g=self.feature_graph();g.data['placed_feature']['test:feature']={}
        self.assertTrue(g.audit()['pass'])

    def test_unsupported_alias_produces_failing_report(self):
        r=Graph().root('r','p',[{'type':'test:unknown'}]).pool('p').audit()
        self.assertFalse(r['pass']);self.assertTrue(r['errors'])

    def test_nbt_parser_system_exit_retained_as_failure(self):
        g=Graph().root('r','p').pool('p','t').template('t')
        def load(kind,name):
            if kind=='template':raise SystemExit('malformed NBT')
            return g.data[kind][name]
        r=m.Audit(g.data,load).run()
        self.assertFalse(r['pass']);self.assertTrue(any('malformed NBT' in e for e in r['errors']))


if __name__=='__main__':unittest.main(verbosity=2)
