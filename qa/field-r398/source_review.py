#!/usr/bin/env python3
"""Read-only analysis; full source names are discovered, never inferred."""
from pathlib import Path
from collections import Counter
import hashlib,json,zipfile

def main():
    out=Path('artifacts');out.mkdir(exist_ok=True)
    results=list(Path('evidence').rglob('difference-review.json'))
    if len(results)!=1:raise ValueError('Need one exact saved comparison')
    path=results[0];d=json.loads(path.read_text());rows=d['differences']
    if d.get('truncated') is not False or len(rows)!=d['total_differences']:raise ValueError('Incomplete saved differences')
    same=[];other=[];types=Counter()
    for r in rows:
        if r['forward']==r['baseline_forward'] and r['reverse']==r.get('baseline_reverse'):same.append(r)
        else:other.append(r)
        types[(r['forward']['Name'],r['reverse']['Name'])]+=1
    report={'source_run':d['source_run'],'source_core_sha256':d['source_core_sha256'],'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'inspected_difference_rows':len(rows),'identical_to_corresponding_baseline':len(same),'not_identical_to_baseline':len(other),'other_rows':other,'scope':'Only the complete difference list of four selected saved chunks, not all world cells; inherited does not mean correct','production_accepted':False}
    (out/'inherited-difference-review.json').write_text(json.dumps(report,indent=2)+'\n')
    print('INHERITED_DIFFERENCE_REVIEW',json.dumps(report),flush=True)
    print('STATE_PAIR_COUNTS',json.dumps({a+' => '+b:n for (a,b),n in types.items()}),flush=True)
    for p in Path('evidence').rglob('witness-review.json'):
        w=json.loads(p.read_text())
        compact=[{k:v for k,v in r.items() if k not in ('examples','owner_reachability_examples')} for r in w['rows']]
        print('PRE_WRITE_WITNESS_ROWS',json.dumps(compact),flush=True)
    with zipfile.ZipFile('debug/diagnostics.zip') as z:
        names=[n for n in z.namelist() if '/src/minecraft/java/' in n and n.endswith('.java')]
        available=sorted(n for n in names if 'NeverOverworld' in Path(n).name)
        print('AVAILABLE_GENERATOR_SOURCES',json.dumps(available),flush=True)
        wanted={'NeverOverworldFlood.java','NeverOverworldFloodConnectivityR15.java','ChunkPyramid.java','ChunkStatusTasks.java'}
        found=set()
        for n in names:
            base=Path(n).name
            if base not in wanted:continue
            if base in found:raise ValueError('Ambiguous source')
            found.add(base);raw=z.read(n);(out/base).write_bytes(raw)
            lines=raw.decode().splitlines();selected=set()
            for i,line in enumerate(lines):
                if base=='ChunkPyramid.java' or any(k in line for k in ('reweather','SubmergedRemnants','getChunkIfPresent','FEATURES','LIGHT','carvers','applyBiomeDecoration','setBlockState','GRASS_BLOCK','DRIPSTONE')):selected.update(range(max(0,i-12),min(len(lines),i+15)))
            print('\nMATERIALIZED_SOURCE',n,'SHA256',hashlib.sha256(raw).hexdigest(),flush=True)
            previous=-2
            for i in sorted(selected):
                if i!=previous+1:print('...')
                print(f'{i+1}: {lines[i]}');previous=i
        if not {'NeverOverworldFlood.java','ChunkStatusTasks.java'}<=found:raise ValueError('Required actual source missing')
    print('SOURCE_REVIEW_DONE')
if __name__=='__main__':main()
