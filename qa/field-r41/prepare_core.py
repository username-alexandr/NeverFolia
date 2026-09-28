#!/usr/bin/env python3
"""Apply the exact fixture repair in a disposable build checkout.
The returned reference map is intentionally read-only; use the public mutator.
No production class or fixture assertion is changed by this transformation.
"""
from pathlib import Path
import hashlib,json
p=Path('qa/field-r3913/R3913IceQa.java')
b=p.read_bytes();expected='c85e0dce16df689281e01c4a4feefb3a41ee0888'
if hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()!=expected:raise ValueError('Unexpected ice QA input')
a='c.getAllReferences().put(s,new it.unimi.dsi.fastutil.longs.LongOpenHashSet(new long[]{0L}));'
z='c.addReferenceForStructure(s,0L);'
t=b.decode()
if t.count(a)!=1:raise ValueError('Ambiguous fixture anchor')
t=t.replace(a,z)
if t.replace(z,a)!=b.decode():raise ValueError('Unexpected source change')
p.write_text(t)
out=Path('artifacts');out.mkdir(exist_ok=True)
(out/'fixture-repair.json').write_text(json.dumps({'source_blob':expected,'replacement':'ChunkAccess.addReferenceForStructure','assertions_removed':0,'production_changes':0},indent=2)+'\n')
