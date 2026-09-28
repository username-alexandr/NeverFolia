#!/usr/bin/env python3
"""Recover exact historical authored NBT models, never approximate aliases.
The old data version is retained for Minecraft's own forward data fixer.
Only absent reviewed IDs are added. Current pools/weights/roots stay unchanged,
except the separately verified two mansion identifier corrections.
"""
from pathlib import Path
from urllib.parse import urlparse
import json,urllib.request
import mansion_reference as fix
s=fix.s;ROOT=fix.ROOT
AUTHOR_URL='https://cdn.modrinth.com/data/tpehi7ww/versions/8o3mS993/Dungeons%20and%20Taverns%20v4.5.zip'
AUTHOR_SHA='c48fd3ddf4999cdaa7513e8ea676b5c8f527ae1f28a0e4a72ad0272502c69979'
AUTHOR_SIZE=14032193
PREFIX='data/nova_structures/structure/stray_fort/'
MODELS=tuple(sorted('stray_fort_wall_'+part+str(i) for part in ('','back_','back_left_','back_right_','front_','front_left_','front_right_','gate_','gate_back_','gate_front_','gate_short_','short_') for i in (1,2,3)))

def author_bytes():
    req=urllib.request.Request(AUTHOR_URL,headers={'User-Agent':'NeverFolia-resource-recovery/1.0'})
    with urllib.request.urlopen(req,timeout=60) as r:
        s.need(urlparse(r.url).scheme=='https' and urlparse(r.url).hostname=='cdn.modrinth.com','Unexpected author redirect')
        raw=r.read(AUTHOR_SIZE+1)
    s.need(len(raw)==AUTHOR_SIZE and s.sha(raw)==AUTHOR_SHA,'Wrong exact historical author archive')
    return raw

def build(base,author,before):
    s.need(s.sha(base)==fix.BASE and s.sha(author)==AUTHOR_SHA,'Wrong pinned inputs')
    s.need(before['inputs']['pack_sha256']==fix.BASE,'Wrong reference audit')
    missing={(x['kind'],x['id']) for x in before['missing']}
    corrected,mansion=fix.build(base);files=s.read_zip(corrected);original=s.read_zip(base);source=s.read_zip(author)
    ext=s.load('r3918_authored_walls',ROOT/'scripts/build-never-overworld-external-structures-r19.py');rows=[]
    for model in MODELS:
        path=PREFIX+model+'.nbt';ident='nova_structures:stray_fort/'+model
        s.need(('template',ident) in missing and path not in files and path in source,'Unexpected restoration target '+ident)
        raw=source[path];root=ext._nbt_parse(raw)[2]
        version=root.get('DataVersion');s.need(version and version[0]==3 and version[1] in (3578,3688),'Unreviewed authored version')
        size=root['size'][1][1];s.need(len(size)==3 and all(type(x) is int and 0<x<=32 for x in size),'Unexpected wall bounds')
        s.need('palettes' not in root,'Multiple palettes need a separate review')
        palette=root['palette'][1][1];blocks=root['blocks'][1][1];s.need(bool(blocks) and bool(palette),'Empty wall')
        joints=[];nonair=0
        for b in blocks:
            pos=b['pos'][1][1];idx=b['state'][1]
            s.need(len(pos)==3 and all(type(x) is int and 0<=x<d for x,d in zip(pos,size)),'Out-of-bounds source block')
            s.need(type(idx) is int and 0<=idx<len(palette),'Invalid source palette')
            name=palette[idx]['Name'][1]
            if name not in ('minecraft:air','minecraft:cave_air','minecraft:void_air','minecraft:structure_void'):nonair+=1
            if name=='minecraft:jigsaw':joints.append({'pos':pos,'nbt':b.get('nbt')})
        s.need(nonair>100 and joints,'Wall lacks geometry/connectors')
        # This existing sanitizer removes only known foreign PortingLib attributes.
        # No blanket entity removal, no manual DataVersion relabel, no loot edit.
        def foreign_ids(value):
            if isinstance(value,dict):
                return sum(foreign_ids(v) for v in value.values())
            if isinstance(value,(tuple,list)):
                return sum(foreign_ids(v) for v in value)
            return int(isinstance(value,str) and value.startswith('porting_lib:'))
        before_foreign=foreign_ids(root)
        installed=ext.sanitize_dat_structure_nbt(raw,ident)
        afterroot=ext._nbt_parse(installed)[2]
        after_foreign=foreign_ids(afterroot)
        s.need(after_foreign==0 and before_foreign>=after_foreign,'Foreign attribute sanitizer contract changed')
        removed=before_foreign-after_foreign
        s.need(afterroot['size']==root['size'] and afterroot['DataVersion']==version and afterroot['palette']==root['palette'] and afterroot['blocks']==root['blocks'],'Authored wall geometry changed')
        files[path]=installed
        rows.append({'id':ident,'path':path,'source_sha256':s.sha(raw),'installed_sha256':s.sha(installed),'data_version':version[1],'size':size,'blocks':len(blocks),'nonair':nonair,'jigsaw_count':len(joints),'jigsaws':joints,'foreign_attributes_removed':removed,'byte_identical_to_author':raw==installed})
    s.need(len(rows)==36 and len({r['id'] for r in rows})==36,'Incomplete exact model family')
    fp=s.load('r3918_wall_fingerprint',ROOT/'scripts/fingerprint-never-overworld-pack.py')
    encoded=(json.dumps(fp.fingerprint_document(files),ensure_ascii=False,indent=2)+'\n').encode()
    for p in s.FP:files[p]=encoded
    s.need(set(files)-set(original)=={r['path'] for r in rows} and not set(original)-set(files),'Unexpected entry delta')
    s.need(all(files[p]==v for p,v in original.items() if p not in (*fix.POOLS,*s.FP)),'Unrelated original content changed')
    output=s.write_zip(files);s.need(s.read_zip(output)==files and output==s.write_zip(files),'Nonrepeatable output')
    return output,{'pass':True,'base_sha256':fix.BASE,'source_url':AUTHOR_URL,'source_archive_sha256':AUTHOR_SHA,'output_sha256':s.sha(output),'mansion_repair':mansion,'models':rows,'restored_templates':36,'existing_entries_preserved':sum(files[p]==v for p,v in original.items()),'old_pack_installed':False,'all_reported_bugs_fixed':False,'production_accepted':False}
