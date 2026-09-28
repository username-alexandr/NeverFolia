#!/usr/bin/env python3
"""Compare the exact existing content delta in its complete configured QA stack.
A successful regression check is not full resource or production acceptance.
"""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'qa/field-r3915'))
import never_resource_stack as s
import combine_content as c
import run_combined as r
import run_runtime as swift

OUT = ROOT / 'artifacts'


def save(name, value):
    OUT.mkdir(exist_ok=True)
    with (OUT / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def configured_order(path, function):
    raw = path.read_bytes()
    tree = ast.parse(raw, filename=str(path))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function]
    s.need(len(functions) == 1, 'Unknown setup function: ' + function)
    found = []
    for node in ast.walk(functions[0]):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.extend(re.findall(r'initial-enabled-packs=([^\n]+)', node.value))
    s.need(len(found) == 1, 'Missing/ambiguous configured pack order in ' + str(path))
    return {'source': str(path.relative_to(ROOT)), 'function': function,
            'source_sha256': s.digest(raw), 'order': found[0].split(',')}


def record(path, expected, ident=None):
    result = {'path': str(path), 'sha256': expected}
    if ident is not None:
        result['id'] = ident
    return result


def missing(report):
    return {(x['kind'], x['id']) for x in report['missing']}


def roots(report):
    return {row['id'] for row in report['roots']}


def changed_non_tags(base, fixed):
    with zipfile.ZipFile(base) as a, zipfile.ZipFile(fixed) as b:
        old, new = set(a.namelist()), set(b.namelist())
        s.need(not old - new, 'Original resources were deleted')
        result = {}
        for name in sorted(new):
            parts = name.split('/')
            if not name.startswith('data/') or len(parts) < 4 or parts[2] == 'tags':
                continue
            after = b.read(name)
            if name not in old or a.read(name) != after:
                result[name] = s.digest(after)
        return result


def main():
    summary = {'pass': False, 'full_resource_acceptance': False, 'production_accepted': False,
               'all_reported_bugs_fixed': False, 'user_world_changed': False}
    try:
        build = s.decode_json((OUT / 'combined-content.json').read_bytes())
        old_delta = s.decode_json((OUT / 'combined-resource-delta.json').read_bytes())
        s.need(build.get('pass') is True and old_delta.get('pass') is True,
               'Existing build and isolated cart delta must succeed first')
        kernel = r.exact_file(ROOT / 'swift-input', 'server-r3915.jar', c.CORE)
        base = r.exact_file(ROOT / 'inputs', 'NeverOverworld.zip', c.BASE)
        fixed = r.exact_file(OUT, 'NeverOverworld-R3915-Combined.zip', build['output_sha256'])
        nether = r.exact_file(ROOT / 'inputs', 'NeverNether.zip', swift.NETHER)
        order = configured_order(ROOT / 'qa/field-r3915/run_runtime.py', 'setup')
        carts = configured_order(ROOT / 'qa/field-r3915/run_combined.py', 'cart_world')
        expected = ['vanilla', 'file/NeverOverworld.zip', 'file/NeverNether.zip']
        s.need(order['order'] == expected, 'Configured order changed; review required')
        s.need(carts['order'] == expected + ['file/CartQa.zip'], 'Cart fixture precedence changed')
        save('stack-order-source.json', {'base': order, 'cart_fixture': carts,
             'evidence_kind': 'configured isolated QA source; not yet runtime or production evidence',
             'cart_fixture_included_in_base_audit': False})
        def manifest(pack, sha):
            return {'schema': 1, 'server': record(kernel, c.CORE),
                    'packs': [record(pack, sha, expected[1]), record(nether, swift.NETHER, expected[2])]}
        manifests = {'before': manifest(base, c.BASE), 'after': manifest(fixed, build['output_sha256'])}
        # Publish both checked input identities first. The independent startup
        # witness must still run when a static decoder encounters a blocker.
        for label, value in manifests.items():
            save('stack-' + label + '-manifest.json', value)
        results = {}
        for label, value in manifests.items():
            result = s.audit_manifest(value)
            save('stack-' + label + '-resources.json', result)
            results[label] = result
            print('STACK_RESULT', label, json.dumps({k: result[k] for k in ('pass', 'audit_complete', 'counts', 'errors')}), flush=True)
            for row in result['missing']:
                print('STACK_MISSING', label, row['kind'], row['id'], 'roots=' + ','.join(row['roots']), flush=True)
        before, after = results['before'], results['after']
        s.need(before['audit_complete'] and after['audit_complete'], 'Graph audit has unhandled errors')
        added_missing = missing(after) - missing(before)
        removed_missing = missing(before) - missing(after)
        expected_removed = {('template', 'nova_structures:tavern/tavern_event_trader_car_' + role + '_' + biome)
                            for role in ('cartographer', 'cleric') for biome in c.BIOMES}
        s.need(not removed_missing - expected_removed, 'Unexplained resource closure changes')
        changed = changed_non_tags(base, fixed)
        providers = after['resource_resolution']['non_tag_providers']
        shadowed = [{'path': name, 'expected_sha256': sha, 'effective': providers.get(name)}
                    for name, sha in changed.items() if providers.get(name, {}).get('sha256') != sha]
        same_roots = roots(before) == roots(after)
        summary.update({'before': before['counts'], 'after': after['counts'],
            'removed_missing': sorted(removed_missing), 'introduced_missing': sorted(added_missing),
            'root_identity_preserved': same_roots, 'shadowed_content_changes': shadowed,
            'checked_content_changes': len(changed), 'order_low_to_high': expected,
            'full_resource_acceptance': after['pass'],
            'isolated_delta_preserved': old_delta['pass'],
            'isolated_after_counts': old_delta['after'],
            'effective_after_missing_count': len(after['missing']),
            'isolated_missing_resolved_in_stack': sorted(missing(s.decode_json((OUT / 'combined-resource-after.json').read_bytes())) - missing(after)),
            'new_stack_only_missing': sorted(missing(after) - missing(s.decode_json((OUT / 'combined-resource-after.json').read_bytes()))),
            'override_count': len(after['resource_resolution']['overrides']),
            'different_byte_override_count': sum(x['bytes_changed'] for x in after['resource_resolution']['overrides']),
            'server_sha256': c.CORE, 'overworld_sha256': build['output_sha256'], 'nether_sha256': swift.NETHER,
            'runtime_order_verified': False,
            'scope': 'Ordered base QA pack stack. CartQa synthetic roots are separate; tag merge, other registries, geometry and gameplay remain outside this audit.'})
        s.need(not added_missing and same_roots and not shadowed, 'Ordered-stack regression or shadowed content repair')
        summary['pass'] = True
    except Exception as error:
        summary['error'] = repr(error)
        raise
    finally:
        save('stack-delta.json', summary)
        print('STACK_DELTA', json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
