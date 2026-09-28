#!/usr/bin/env python3
"""R41 cart reconstruction accepts block-state property recipes only after the
existing every-voxel comparison against all reference variants. Item/entity/NBT
recipes remain forbidden. This corrects the old assumption that biome changes
contain only block names; e.g. a reference campfire changes its lit property.
"""
import importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'qa/field-r41/repair_pack.py';s=importlib.util.spec_from_file_location('r41_repair',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
original=m.load
def load(path,name):
    result=original(path,name)
    if name=='r41carts':
        previous=result.allowed
        def reviewed(path):
            return previous(path) or (len(path)==7 and path[0]=='blocks' and isinstance(path[1],tuple)
                and path[2:5]==('state','Properties',1) and isinstance(path[5],str) and path[6]==1)
        assert not reviewed(('entities',1,1,0,'id',1))
        assert not reviewed(('blocks',(0,0,0),'nbt',1,'Items',1))
        assert reviewed(('blocks',(3,2,1),'state','Properties',1,'lit',1))
        result.allowed=reviewed
    return result
m.load=load
m.main()
