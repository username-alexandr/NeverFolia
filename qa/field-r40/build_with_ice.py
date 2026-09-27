#!/usr/bin/env python3
"""Checked late-stage expansion of the pinned R40 builder; no source artifact writes."""
from pathlib import Path
import hashlib,importlib.util
ROOT=Path(__file__).resolve().parents[2]
path=Path(__file__).with_name('build.py');raw=path.read_bytes()
blob=hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()
if blob!='b8112c1b05639132ca62dee503d4502da2bb6f01':raise ValueError('Unreviewed base builder')
text=raw.decode();anchor="    source_dir=WORK/'src';classes=WORK/'classes';classes.mkdir();paths=[]\n"
insertion="""    spec=importlib.util.spec_from_file_location('r40_ice_patch',ROOT/'qa/field-r40/ice_patch.py')
    ice=importlib.util.module_from_spec(spec);spec.loader.exec_module(ice)
    with zipfile.ZipFile(ROOT/'debug/diagnostics.zip') as archive:
        ice.patch_sources(archive,sources,source_hashes)
"""
if text.count(anchor)!=1:raise ValueError('Late-stage builder anchor drift')
text=text.replace(anchor,insertion+anchor,1)
output=ROOT/'artifacts';output.mkdir(exist_ok=True)
(output/'effective-build-with-ice.py').write_text(text)
exec(compile(text,str(path),'exec'),{'__name__':'__main__','__file__':str(path)})
