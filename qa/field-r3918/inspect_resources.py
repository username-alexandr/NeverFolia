#!/usr/bin/env python3
"""Inspect pinned combined resources without modifying the pack or world."""
from pathlib import Path
import collections, difflib, hashlib, importlib.util, json, zipfile

ROOT = Path(__file__).resolve().parents[2]
PACK_SHA = '0e747781b9ea875631f1453903c0ac912d49f14a3a46ad48bbf604148532c621'
OUT = ROOT / 'r3918-evidence'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def load_reader():
    path = ROOT / 'scripts/build-never-overworld-external-structures-r19.py'
    spec = importlib.util.spec_from_file_location('r3918_nbt_reader', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unwrap(tag, kind, label):
    need(isinstance(tag, (list, tuple)) and len(tag) == 2 and tag[0] == kind, 'Wrong typed NBT: ' + label)
    return tag[1]


def inspect_template(raw, reader):
    root = reader._nbt_parse(raw)[2]
    size = unwrap(root['size'], 9, 'size')
    need(size[0] == 3, 'Noninteger size')
    palette = unwrap(root['palette'], 9, 'palette')
    need(palette[0] == 10 and 'palettes' not in root, 'Unreviewed palettes')
    blocks = unwrap(root.get('blocks', (9, (10, []))), 9, 'blocks')
    need(blocks[0] == 10, 'Wrong blocks')
    joints = []
    counts = collections.Counter()
    for block in blocks[1]:
        index = unwrap(block['state'], 3, 'state')
        need(type(index) is int and 0 <= index < len(palette[1]), 'Bad palette index')
        state = palette[1][index]
        name = unwrap(state['Name'], 8, 'Name')
        counts[name] += 1
        if name != 'minecraft:jigsaw':
            continue
        nbt = unwrap(block['nbt'], 10, 'jigsaw')
        pos = unwrap(block['pos'], 9, 'pos')
        need(pos[0] == 3, 'Noninteger position')
        joints.append({'pos':pos[1], 'state':state,
                       'nbt': {k: v[1] for k, v in nbt.items()}})
    entities = root.get('entities', (9, (10, [])))
    return {'size':size[1], 'sha256':hashlib.sha256(raw).hexdigest(),
            'blocks':dict(sorted(counts.items())), 'joints':joints, 'entities':entities}


def main():
    OUT.mkdir(exist_ok=True)
    candidates = list((ROOT/'combined-input').rglob('NeverOverworld-R3915-Combined.zip'))
    need(len(candidates) == 1, 'Missing or ambiguous combined pack')
    raw = candidates[0].read_bytes()
    need(hashlib.sha256(raw).hexdigest() == PACK_SHA, 'Combined pack identity changed')
    with zipfile.ZipFile(candidates[0]) as z:
        need(len(z.namelist()) == len(set(z.namelist())), 'Duplicate archive members')
        need(z.testzip() is None, 'Bad ZIP CRC')
        files = {name: z.read(name) for name in z.namelist() if not name.endswith('/')}
    reader = load_reader()
    report = {'input_pack_sha256':PACK_SHA, 'pack_unchanged':True, 'templates':{}, 'pools':{}, 'matching_joints':[], 'missing':[]}
    for path, data in sorted(files.items()):
        if 'pale_residence' in path:
            if path.endswith('.nbt'):
                obj = inspect_template(data, reader)
                report['templates'][path] = obj
                print('PALE_TEMPLATE', json.dumps({'path':path, **obj}, ensure_ascii=False), flush=True)
            elif '/worldgen/template_pool/' in path and path.endswith('.json'):
                obj = json.loads(data)
                report['pools'][path] = obj
                print('PALE_POOL', path, json.dumps(obj, ensure_ascii=False), flush=True)
    # Scan all authored template connectors: matching names can live outside a directory.
    for path, data in sorted(files.items()):
        if '/structure/' not in path or not path.endswith('.nbt'):
            continue
        root = reader._nbt_parse(data)[2]
        for block in root.get('blocks',(9,(10,[])))[1][1]:
            nbt = block.get('nbt')
            if not nbt or nbt[0] != 10:
                continue
            v = nbt[1]
            texts = {k:x[1] for k,x in v.items() if x[0] == 8}
            if any('pale_residence/decor_inside' in str(x) for x in texts.values()):
                item={'path':path,'pos':block.get('pos'), 'nbt':texts}
                report['matching_joints'].append(item)
                print('DECOR_REFERENCE',json.dumps(item,ensure_ascii=False),flush=True)
    audits = list((ROOT/'combined-input').rglob('combined-resource-after.json'))
    need(len(audits) == 1, 'Missing executed resource report')
    audit = json.loads(audits[0].read_text())
    report['audit_counts'] = audit['counts']
    template_paths = [p for p in files if '/structure/' in p and p.endswith('.nbt')]
    for entry in audit['missing']:
        entry=dict(entry)
        if entry['kind']=='template':
            namespace, name = entry['id'].split(':',1)
            target=f'data/{namespace}/structure/{name}.nbt'
            entry['similar_existing_paths']=difflib.get_close_matches(target,template_paths,n=4,cutoff=0.72)
        report['missing'].append(entry)
        print('MISSING_RESOURCE',json.dumps(entry,ensure_ascii=False),flush=True)
    need(hashlib.sha256(candidates[0].read_bytes()).hexdigest()==PACK_SHA, 'Input changed')
    (OUT/'resource-inspection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('INSPECTION_DONE',json.dumps({'templates':len(report['templates']),'pools':len(report['pools']),'matching_joints':len(report['matching_joints']),'audit_counts':audit['counts'],'worldgen_changed':False}),flush=True)

if __name__=='__main__':
    main()
