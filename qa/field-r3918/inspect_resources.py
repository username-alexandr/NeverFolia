#!/usr/bin/env python3
"""Inspect pinned combined resources without modifying the pack or world."""
from pathlib import Path
import collections, difflib, gzip, hashlib, importlib.util, io, json, sys, urllib.request, zipfile

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
    sys.modules[spec.name] = module
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
    builder = load_reader()
    dat = builder.SOURCES['dat']
    request = urllib.request.Request(dat['url'], headers={'User-Agent':'NeverFolia-pale-source-audit/1.0'})
    with urllib.request.urlopen(request, timeout=60) as response:
        source_raw = response.read(60000000)
    need(hashlib.sha256(source_raw).hexdigest() == dat['sha256'], 'Pinned D&T source hash changed')
    source = builder.flatten_zip(source_raw)
    source_pool = 'data/nova_structures/worldgen/template_pool/pale_residence/decor_inside.json'
    source_candidates = sorted(name for name in source if 'pale_residence' in name and (
        'decor_inside' in name or '/decor/' in name or name.endswith('/pale_house_2.nbt')))
    print('PALE_SOURCE_POOL', source_pool,
          source.get(source_pool, b'<absent>').decode('utf-8', errors='replace'), flush=True)
    print('PALE_SOURCE_CANDIDATES', json.dumps(source_candidates, ensure_ascii=False), flush=True)
    for name in source_candidates:
        if name.endswith('.nbt'):
            try:
                obj = inspect_template(source[name], reader)
                print('PALE_SOURCE_TEMPLATE', json.dumps({'path':name, **obj}, ensure_ascii=False), flush=True)
            except Exception as error:
                print('PALE_SOURCE_TEMPLATE_ERROR', name, repr(error), flush=True)
    report = {'input_pack_sha256':PACK_SHA, 'pack_unchanged':True, 'source_dat_sha256':dat['sha256'],
              'source_decor_pool_present':source_pool in source, 'source_candidates':source_candidates,
              'templates':{}, 'pools':{}, 'matching_joints':[], 'missing':[]}
    def retain():
        (OUT/'resource-inspection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    try:
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
        retain()
        # Literal ASCII ID must occur in decompressed NBT bytes if present in a
        # named string tag. This only filters candidates; typed parsing below
        # still verifies each actual connector, not a regex reconstruction.
        for path, data in sorted(files.items()):
            if '/structure/' not in path or not path.endswith('.nbt'):
                continue
            decoded = gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data
            if b'pale_residence/decor_inside' not in decoded:
                continue
            root = reader._nbt_parse(data)[2]
            for block in root.get('blocks',(9,(10,[])))[1][1]:
                nbt = block.get('nbt')
                if not nbt or nbt[0] != 10:
                    continue
                texts = {k:x[1] for k,x in nbt[1].items() if x[0] == 8}
                if any('pale_residence/decor_inside' in str(x) for x in texts.values()):
                    item={'path':path,'pos':block.get('pos'), 'nbt':texts}
                    report['matching_joints'].append(item)
                    print('DECOR_REFERENCE',json.dumps(item,ensure_ascii=False),flush=True)
        audits = list((ROOT/'combined-input').rglob('combined-resource-after.json'))
        need(len(audits) == 1, 'Missing executed resource report')
        audit = json.loads(audits[0].read_text())
        report['audit_counts'] = audit['counts']
        families = collections.defaultdict(list)
        for path in files:
            if '/structure/' in path and path.endswith('.nbt'):
                families[path.rsplit('/',1)[0]].append(path)
        for entry in audit['missing']:
            entry=dict(entry)
            if entry['kind']=='template':
                namespace, name = entry['id'].split(':',1)
                target=f'data/{namespace}/structure/{name}.nbt'
                family=families[target.rsplit('/',1)[0]]
                entry['similar_same_directory_paths']=difflib.get_close_matches(target,family,n=4,cutoff=0.72)
            report['missing'].append(entry)
            print('MISSING_RESOURCE',json.dumps(entry,ensure_ascii=False),flush=True)
        need(hashlib.sha256(candidates[0].read_bytes()).hexdigest()==PACK_SHA, 'Input changed')
        report['inspection_complete']=True
        print('INSPECTION_DONE',json.dumps({'templates':len(report['templates']),'pools':len(report['pools']),'matching_joints':len(report['matching_joints']),'audit_counts':audit['counts'],'worldgen_changed':False}),flush=True)
    finally:
        retain()

if __name__=='__main__':
    main()
