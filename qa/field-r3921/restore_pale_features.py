#!/usr/bin/env python3
"""Restore the exact authored D&T v4.5 Pale Residence feature pool and dependencies."""
from pathlib import Path
import argparse, hashlib, json, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'field-r3918'))
import restore_stray_walls as walls

ROOT=Path(__file__).resolve().parents[2];s=walls.s
BASE='9daf27e23300d6687e8cc93cf82c7e6db91f69e4fe605382c6947521f0855590'
POOL='data/nova_structures/worldgen/template_pool/pale_residence/decor_inside.json'
EMPTY={'fallback':'minecraft:empty','elements':[{'element':{'element_type':'minecraft:empty_pool_element'},'weight':1}]}
SOURCE_POOL={'elements':[
    {'element':{'element_type':'minecraft:feature_pool_element','feature':'nova_structures:pale_moss_small','projection':'rigid'},'weight':6},
    {'element':{'element_type':'minecraft:feature_pool_element','feature':'nova_structures:pale_moss_floor','projection':'rigid'},'weight':3},
    {'element':{'element_type':'minecraft:empty_pool_element'},'weight':1}],
    'fallback':'minecraft:empty'}
FILES={
'data/nova_structures/worldgen/configured_feature/pale_hanging_leaves.json':'6724f06e907b2f7d3b069c6e60f7b09ebbce79f1d87e621945f403688dfa4eaf',
'data/nova_structures/worldgen/configured_feature/pale_hanging_moss.json':'58f0fa01ddd387bcdd988f400946401c8255b9ec2f98ac135bb9b7ebfc2f7355',
'data/nova_structures/worldgen/configured_feature/pale_moss_floor.json':'97c2c141baa02170c15c2dface8e1b78faf3893e263a47b9e6d8c9098d7b973a',
'data/nova_structures/worldgen/configured_feature/pale_moss_small.json':'d11d3009a3737bfbc270f6dbb9ec2c302ca19be84ab8bed4cdafe8f1c249168c',
'data/nova_structures/worldgen/configured_feature/pale_moss_vegetation.json':'423fae5c1acb1a41a1133afdabce567761be573ad08f9b1e4c5a9d49bac9eeca',
'data/nova_structures/worldgen/placed_feature/pale_hanging_leaves.json':'c03195c2e5622c8484ae07dc203a3e49851a4e084ed1b9be2a97a4742aa4341f',
'data/nova_structures/worldgen/placed_feature/pale_hanging_moss.json':'d09ca6ac02ae26a3524af346af2f36d0a61d9942d6495ab83c120cfcdb6036db',
'data/nova_structures/worldgen/placed_feature/pale_moss_floor.json':'97679ba756d1acb6da50376b3f9acdcd3af24db975ff8d95f429d40cefc9226b',
'data/nova_structures/worldgen/placed_feature/pale_moss_foliage.json':'b3451df74e0e1a6fb90c3b5a3376a54c4106fc0bd89e3c480748346039713d2d',
'data/nova_structures/worldgen/placed_feature/pale_moss_placer.json':'0d24000eecc9124a766bd330d66e1db71b8911b32bc39fcfc3a23f5955fb55b1',
'data/nova_structures/worldgen/placed_feature/pale_moss_placer_floor.json':'36db50cb6823291989f09656eece2e2bd0e3efcf8e113b2161ab2bc99aa55eca',
'data/nova_structures/worldgen/placed_feature/pale_moss_small.json':'d233991d697e94bbf47e41aa8fbf4b8c5577daba231974e2bd47e2a64a3e6e93',
'data/nova_structures/worldgen/placed_feature/pale_moss_vegetation.json':'bafd0b918637fa2d49df7241ba359b3fc60a600999c1aa76d32ca3fcf7f8324b',
}
TAGS={
'data/nova_structures/tags/block/moss_spreads_over.json':'2c1e9917846046f6cb923d9d29567d3769cab272fa03b89d7fabbcbc8c681af2',
'data/nova_structures/tags/block/pale_moss_grows_on.json':'f5254965de7f9a2307134b78acb209533fd80decabeaacf13eb41d596c37f92b',
}

def need(ok,msg):
    if not ok:raise ValueError(msg)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def build(base_raw):
    need(sha(base_raw)==BASE,'Wrong R39.20 base candidate')
    base=s.read_zip(base_raw);out=base.copy();author=s.read_zip(walls.author_bytes())
    need(json.loads(base[POOL])==EMPTY,'R39.20 Pale compatibility pool changed')
    need(json.loads(author[POOL])==SOURCE_POOL,'Pinned D&T v4.5 Pale pool changed')
    for path,expected in TAGS.items():
        need(path in base and path in author,'Required Pale tag missing: '+path)
        need(sha(author[path])==expected and sha(base[path])==expected,'Pale tag is not exact v4.5 bytes: '+path)
    copied=[]
    for path,expected in FILES.items():
        need(path not in base,'R39.20 unexpectedly already contains '+path)
        need(path in author and sha(author[path])==expected,'Pinned author dependency changed: '+path)
        out[path]=author[path];copied.append({'path':path,'sha256':expected})
    out[POOL]=author[POOL]
    fp=s.load('r3921_pale_fingerprint',ROOT/'scripts/fingerprint-never-overworld-pack.py')
    encoded=(json.dumps(fp.fingerprint_document(out),ensure_ascii=False,indent=2)+'\n').encode()
    for path in s.FP:out[path]=encoded
    additions=set(FILES)
    need(set(out)-set(base)==additions,'Unexpected Pale dependency additions')
    allowed={POOL,*s.FP}
    need(all(out[p]==v for p,v in base.items() if p not in allowed),'Unrelated R39.20 bytes changed')
    payload=s.write_zip(out)
    need(s.read_zip(payload)==out and payload==s.write_zip(out),'Nonrepeatable Pale pack')
    return payload,{'pass':True,'base_sha256':BASE,'author_sha256':walls.AUTHOR_SHA,
                    'output_sha256':sha(payload),'restored_pool':SOURCE_POOL,
                    'copied_dependencies':copied,'copied_count':len(copied),
                    'tags_verified_unchanged':TAGS,'synthetic_templates_added':0}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    payload,report=build(a.input.read_bytes())
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(payload)
    (a.output.parent/'pale-feature-build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('R3921_PALE_BUILD',json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
