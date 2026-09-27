#!/usr/bin/env python3
"""Static jigsaw closure using the pinned engine's one-hop alias semantics.

No pack/world writes. This checks possible references, not connector geometry,
biome eligibility, generation depth, processors, loot, mob AI or runtime physics.
Missing resources and unsupported constructs fail; nothing becomes an empty room.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import zipfile

MAX_CONTEXTS = 4096
SCOPE = ('Potential jigsaw pool/template and placed-feature-holder references from '
         'structure_set roots; root-local correlated aliases and bundled vanilla. '
         'Not geometry, depth, biome, processor, feature-content, loot or gameplay proof.')


def rid(value):
    if not isinstance(value, str) or not value:
        raise ValueError('Resource identifier must be a nonempty string')
    value = value if ':' in value else 'minecraft:' + value
    if not re.fullmatch(r'[a-z0-9_.-]+:[a-z0-9_./-]+', value):
        raise ValueError('Invalid resource identifier: ' + value)
    return value


def weighted(items):
    if not isinstance(items, list) or not items:
        raise ValueError('Empty or invalid weighted choice')
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Invalid weighted entry')
        weight = item.get('weight', 1)
        if isinstance(weight, bool) or not isinstance(weight, int) or weight < 0:
            raise ValueError('Invalid weight')
        if weight:
            result.append(item)
    if not result:
        raise ValueError('No positive-weight alternative')
    return result


def combine(left, right, limit=MAX_CONTEXTS):
    result = {}
    for a in left:
        for b in right:
            overlap = set(a) & set(b)
            if overlap:
                raise ValueError('Duplicate simultaneously selected alias: ' + ', '.join(sorted(overlap)))
            value = {**a, **b}
            result[tuple(sorted(value.items()))] = value
            if len(result) > limit:
                raise ValueError('Alias context limit exceeded; audit not complete')
    return list(result.values())


def alias_contexts(bindings, limit=MAX_CONTEXTS):
    if not isinstance(bindings, list):
        raise ValueError('pool_aliases must be a list')
    result = [{}]
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ValueError('Invalid alias binding')
        kind = rid(binding.get('type'))
        if kind == 'minecraft:direct':
            choices = [{rid(binding['alias']): rid(binding['target'])}]
        elif kind == 'minecraft:random':
            choices = [{rid(binding['alias']): rid(v['data'])} for v in weighted(binding['targets'])]
        elif kind == 'minecraft:random_group':
            choices = []
            for group in weighted(binding['groups']):
                choices.extend(alias_contexts(group['data'], limit))
                if len(choices) > limit:
                    raise ValueError('Alias group limit exceeded; audit not complete')
        else:
            raise ValueError('Unsupported alias binding: ' + kind)
        result = combine(result, choices, limit)
    return result


class Audit:
    """Loader supplies decoded JSON or the declared pool IDs of NBT jigsaws."""
    def __init__(self, indexes, loader):
        self.indexes, self.loader, self.cache = indexes, loader, {}
        self.issues, self.errors = {}, set()
        self.visited_pools, self.visited_templates = set(), set()
        self.root_reports, self.center_fallbacks = [], set()

    def load(self, kind, name):
        key = (kind, name)
        if key not in self.cache:
            self.cache[key] = self.loader(kind, name)
        return self.cache[key]

    def exists(self, kind, name, origin, root, context):
        if name in self.indexes.get(kind, {}):
            return True
        item = self.issues.setdefault((kind, name), {
            'kind': kind, 'id': name, 'origins': set(), 'roots': set(), 'contexts': set(), 'examples': []})
        item['origins'].add(origin)
        item['roots'].add(root)
        key = (root, tuple(sorted(context.items())))
        if key not in item['contexts'] and len(item['examples']) < 3:
            item['examples'].append({'structure': root, 'aliases': context})
        item['contexts'].add(key)
        return False

    def run_root(self, root):
        if not self.exists('structure', root, 'structure_set', root, {}):
            return
        data = self.load('structure', root)
        if not isinstance(data, dict):
            raise ValueError('Invalid structure object: ' + root)
        if rid(data.get('type')) != 'minecraft:jigsaw':
            self.root_reports.append({'id': root, 'jigsaw': False,
                                      'reason': 'non-jigsaw structure outside this closure scope'})
            return
        start = rid(data['start_pool'])
        contexts = alias_contexts(data.get('pool_aliases', []))
        self.root_reports.append({'id': root, 'jigsaw': True, 'alias_contexts': len(contexts)})
        for context in contexts:
            # The original start holder must decode before the alias is consulted.
            if not self.exists('pool', start, 'structure:' + root, root, context):
                continue
            mapped = context.get(start, start)
            if mapped not in self.indexes['pool']:
                self.center_fallbacks.add((root, start, mapped))
                mapped = start
            queue = collections.deque([(mapped, 'structure:' + root)])
            seen_pools, seen_templates = set(), set()

            def template(name, origin):
                name = rid(name)
                if not self.exists('template', name, origin, root, context) or name in seen_templates:
                    return
                seen_templates.add(name)
                self.visited_templates.add(name)
                for pool in self.load('template', name):
                    pool = rid(pool)
                    # PoolAliasLookup performs one lookup, not recursive substitution.
                    queue.append((context.get(pool, pool), 'template:' + name))

            def element(node, origin):
                if not isinstance(node, dict):
                    raise ValueError('Invalid pool element in ' + origin)
                kind = rid(node.get('element_type'))
                if kind in ('minecraft:single_pool_element', 'minecraft:legacy_single_pool_element'):
                    template(node['location'], origin)
                elif kind == 'minecraft:list_pool_element':
                    values = node['elements']
                    if not isinstance(values, list) or not values:
                        raise ValueError('Invalid list pool element in ' + origin)
                    for child in values:
                        element(child, origin)
                elif kind == 'minecraft:empty_pool_element':
                    pass
                elif kind == 'minecraft:feature_pool_element':
                    feature = node.get('feature')
                    # FeaturePoolElement holds PlacedFeature, NOT ConfiguredFeature.
                    if isinstance(feature, str):
                        self.exists('placed_feature', rid(feature), origin, root, context)
                    elif not isinstance(feature, dict):
                        raise ValueError('Invalid feature element in ' + origin)
                else:
                    raise ValueError('Unsupported pool element ' + kind + ' in ' + origin)

            while queue:
                name, origin = queue.popleft()
                if not self.exists('pool', name, origin, root, context) or name in seen_pools:
                    continue
                seen_pools.add(name)
                self.visited_pools.add(name)
                pool = self.load('pool', name)
                fallback = rid(pool['fallback'])
                # Fallback is already a holder; its ID is NOT alias-remapped.
                if fallback != name:
                    queue.append((fallback, 'fallback:' + name))
                values = pool.get('elements')
                if not isinstance(values, list):
                    raise ValueError('Invalid pool elements in ' + name)
                if not values:
                    if name != 'minecraft:empty':
                        raise ValueError('Noncanonical zero-sized pool: ' + name)
                    continue
                for entry in weighted(values):
                    element(entry['element'], 'pool:' + name)

    def run(self):
        roots = set()
        for name in sorted(self.indexes.get('set', {})):
            try:
                for entry in weighted(self.load('set', name)['structures']):
                    roots.add(rid(entry['structure']))
            except (Exception, SystemExit) as error:
                self.errors.add('structure_set:' + name + ': ' + repr(error))
        if not roots:
            self.errors.add('No structure_set roots found; empty coverage is not a pass')
        for root in sorted(roots):
            try:
                self.run_root(root)
            except (Exception, SystemExit) as error:
                self.errors.add('structure:' + root + ': ' + repr(error))
        issues = []
        for _, item in sorted(self.issues.items()):
            issues.append({k: sorted(v) if isinstance(v, set) else v for k, v in item.items() if k != 'contexts'})
            issues[-1]['context_count'] = len(item['contexts'])
        return {'schema': 2, 'scope': SCOPE, 'pass': not issues and not self.errors,
                'counts': {'roots': len(roots), 'jigsaw_roots': sum(r['jigsaw'] for r in self.root_reports),
                           'alias_contexts': sum(r.get('alias_contexts', 0) for r in self.root_reports),
                           'reachable_pools': len(self.visited_pools), 'reachable_templates': len(self.visited_templates),
                           'missing_pools': sum(r['kind'] == 'pool' for r in issues),
                           'missing_templates': sum(r['kind'] == 'template' for r in issues),
                           'other_missing': sum(r['kind'] not in ('pool', 'template') for r in issues)},
                'missing': issues, 'errors': sorted(self.errors), 'roots': self.root_reports,
                'center_alias_fallbacks': [dict(zip(('root', 'original', 'unavailable_target'), row))
                                           for row in sorted(self.center_fallbacks)]}


def unique_zip(archive):
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError('Duplicate ZIP member names are not supported')
    return set(names)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def audit_files(jar_path, pack_path):
    source = Path(__file__).with_name('build-never-overworld-external-structures-r19.py')
    spec = importlib.util.spec_from_file_location('r39_nbt', source)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    with zipfile.ZipFile(jar_path) as bundler:
        names = unique_zip(bundler)
        nested = [n for n in names if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
        if len(nested) != 1:
            raise ValueError('Expected exactly one pinned Folia 26.2 bundled server')
        raw = bundler.read(nested[0])
    with zipfile.ZipFile(io.BytesIO(raw)) as vanilla, zipfile.ZipFile(pack_path) as pack:
        pn = unique_zip(pack)
        names = pn | unique_zip(vanilla)
        metadata = json.loads(pack.read('pack.mcmeta'))
        if metadata.get('overlays') or metadata.get('filter'):
            raise ValueError('Pack overlays/filters require explicit effective-resource resolution')
        def read(name):
            return (pack if name in pn else vanilla).read(name)
        families = {'pool': ('worldgen/template_pool', 'json'), 'structure': ('worldgen/structure', 'json'),
                    'set': ('worldgen/structure_set', 'json'), 'template': ('structure', 'nbt'),
                    'placed_feature': ('worldgen/placed_feature', 'json')}
        indexes = {}
        for kind, (family, ext) in families.items():
            pattern = re.compile('data/([^/]+)/' + re.escape(family) + '/(.+)\\.' + ext)
            indexes[kind] = {m[1] + ':' + m[2]: name for name in names if (m := pattern.fullmatch(name))}
        def load(kind, name):
            raw = read(indexes[kind][name])
            if kind != 'template':
                return json.loads(raw)
            _, _, root = builder._nbt_parse(raw)
            result = []
            for block in root.get('blocks', (9, (10, [])))[1][1]:
                compound = block.get('nbt', (10, {}))[1]
                pool = compound.get('pool')
                if pool:
                    if pool[0] != 8:
                        raise ValueError('Non-string jigsaw pool in ' + name)
                    result.append(rid(pool[1]))
            return result
        report = Audit(indexes, load).run()
        report['inputs'] = {'server_sha256': sha(jar_path), 'pack_sha256': sha(pack_path)}
        report['resource_index_counts'] = {k: len(v) for k, v in indexes.items()}
        return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jar', type=Path, required=True)
    p.add_argument('--pack', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    try:
        report = audit_files(a.jar, a.pack)
    except (Exception, SystemExit) as error:
        report = {'schema': 2, 'scope': SCOPE, 'pass': False, 'errors': [repr(error)]}
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: report[k] for k in ('pass', 'counts', 'errors') if k in report}, indent=2))
    for row in report.get('missing', []):
        print(row['kind'], row['id'], 'roots=', ','.join(row['roots'][:3]))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
