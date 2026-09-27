"""Compare full parsed block-entity compounds, indexed only by their world position.
Only the OUTER serialization order is non-semantic. No compound fields, inventory
entries, nested lists or unknown metadata are stripped, sorted or normalized.
"""
from __future__ import annotations
from typing import Any

def index_block_entities(values: Any, chunk_x: int, chunk_z: int) -> dict[tuple[int,int,int],dict[str,Any]]:
    if not isinstance(values,list):raise ValueError('Block entities must be a list')
    result={}
    for value in values:
        if not isinstance(value,dict):raise ValueError('Block entity is not a compound')
        if not isinstance(value.get('id'),str) or not value['id']:raise ValueError('Block entity ID missing')
        if any(type(value.get(k)) is not int for k in ('x','y','z')):raise ValueError('Invalid block-entity coordinates')
        position=(value['x'],value['y'],value['z'])
        if value['x']//16!=chunk_x or value['z']//16!=chunk_z or not -512<=value['y']<=511:raise ValueError('Block entity outside the actual owner envelope')
        if position in result:raise ValueError('Duplicate block-entity position')
        result[position]=value
    return result

def compare_block_entities(before: Any, after: Any, chunk_x: int, chunk_z: int) -> dict[str,Any]:
    left=index_block_entities(before,chunk_x,chunk_z)
    right=index_block_entities(after,chunk_x,chunk_z)
    differences=[{'position':list(p),'before':left.get(p),'after':right.get(p)} for p in sorted(set(left)|set(right)) if left.get(p)!=right.get(p)]
    return {'equal':not differences,'order_only':before!=after and not differences,'before_count':len(left),'after_count':len(right),'differences':differences}
