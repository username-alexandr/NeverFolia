"""Pure validation helpers for isolated NeverFolia QA reports."""
import re
SEED=-4651369264513492755
CENTERS=((7,1),(1,-4),(-197,-217),(-169,-250),(-189,-223),(-1699,-769))
TARGETS=frozenset((cx+dx,cz+dz) for cx,cz in CENTERS for dx in (-1,0,1) for dz in (-1,0,1))
DIGEST=re.compile(r'[a-f0-9]{64}\Z')

def require(ok,message):
    if not ok:raise ValueError(message)

def success_marker(line):
    if 'R395 NATURAL QA' not in line:return False
    require(line.rstrip().endswith('R395 NATURAL QA PASS'),'Current QA reported failure or unknown completion')
    return True

def validate_observation(doc,reverse):
    require(isinstance(doc,dict) and doc.get('pass') is True,'Current report failed')
    require(type(doc.get('seed')) is int and doc['seed']==SEED,'Wrong seed')
    require(doc.get('reverse_order') is reverse,'Wrong order')
    rows=doc.get('chunks')
    require(isinstance(rows,list) and len(rows)==54,'Incomplete target rows')
    require(type(doc.get('completed_chunks')) is int and doc['completed_chunks']==54,'Incomplete completion count')
    positions=[]
    for row in rows:
        require(isinstance(row,dict),'Invalid row')
        require(type(row.get('chunk_x')) is int and type(row.get('chunk_z')) is int,'Invalid coordinates')
        positions.append((row['chunk_x'],row['chunk_z']))
        require(row.get('min_y')==-511 and row.get('max_y')==128,'Wrong vertical scope')
        require(isinstance(row.get('water_sha256'),str) and DIGEST.fullmatch(row['water_sha256']),'Malformed hash')
        counts=row.get('block_counts')
        require(isinstance(counts,dict) and all(isinstance(k,str) and type(v) is int and v>=0 for k,v in counts.items()),'Malformed census')
        require(sum(counts.values())==640*256,'Incomplete cell census')
    expected=sorted(TARGETS,key=lambda p:str(p[0])+','+str(p[1]),reverse=reverse)
    require(positions==expected,'Missing, duplicate or incorrectly ordered target')
