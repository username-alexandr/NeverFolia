#!/usr/bin/env python3
"""Combined-kernel bounded safety test. Full generation-order acceptance remains
separate and visible; no user world or deployed server is touched by this runner.
"""
from pathlib import Path
import collections,contextlib,hashlib,importlib.util,json,os,subprocess,threading,time,uuid
from witness import verify,need
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts'
BASE='c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67'
CENTERS=((7,1),(1,-4),(-197,-217),(-169,-250),(-189,-223),(-1699,-769))
TARGETS={(cx+dx,cz+dz) for cx,cz in CENTERS for dx in (-1,0,1) for dz in (-1,0,1)}
SEED=-4651369264513492755

def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def fresh_observation(data,reverse):
    need(data.get('pass') is True and data.get('seed')==SEED and data.get('reverse_order') is reverse,'Wrong current report identity')
    rows=data.get('chunks',[]);need(len(rows)==54 and data.get('completed_chunks')==54,'Incomplete chunk report')
    got=[(r['chunk_x'],r['chunk_z']) for r in rows]
    ordered=sorted(TARGETS,key=lambda p:f'{p[0]},{p[1]}',reverse=reverse)
    need(got==ordered,'Wrong, duplicate or unordered target chunks')

def read_volume(legacy,folder,rows,name):
    observer=legacy.load('r40_observer_'+name,ROOT/'scripts/probe-never-overworld-trees-villages-r1.py')
    paired=legacy.load('r40_paired_'+name,ROOT/'scripts/probe-never-overworld-paired-r12.py')
    return paired.saved_volume(observer,observer.load_nbt(ROOT),folder/'world/dimensions/minecraft/overworld/region',[(r['chunk_x'],r['chunk_z']) for r in rows],{'normal_stop':True,'exit_code':0})

def run_fixture(legacy):
    folder=legacy.setup('fixture',ROOT/'.work/r395-build/R40Fixture.jar')
    nonce=uuid.uuid4().hex;proof=OUT/'proof-fixture';proof.mkdir(exist_ok=False)
    cmd=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G','-Dneverfolia.r395OceanClosure=true',
         f'-Dneverfolia.r395ReportDirectory={proof}',f'-Dneverfolia.qaNonce={nonce}','-jar',str(ROOT/'candidate/server.jar'),'--nogui']
    result={'pass':False,'nonce':nonce};proc=None;reader=None;lines=[]
    try:
        proc=subprocess.Popen(cmd,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (OUT/'fixture.log').open('w') as out:
                for line in proc.stdout:lines.append(line);out.write(line);out.flush()
        reader=threading.Thread(target=pump,daemon=True);reader.start();deadline=time.monotonic()+420
        marker='R40 FIXTURE '
        while not any(marker in line for line in lines):
            need(time.monotonic()<deadline and proc.poll() is None,'Fixture did not complete');time.sleep(.2)
        markers=[line for line in lines if marker in line]
        need(len(markers)==1 and 'R40 FIXTURE PASS '+nonce in markers[0],'Current fixture failed')
        data=json.loads((folder/'plugins/R40Fixture/result.json').read_text())
        need(data.get('pass') is True and data.get('nonce')==nonce and data.get('seed')==SEED,'Invalid fixture identity')
        need(len(data.get('cases',[]))==17 and all(r.get('pass') is True for r in data['cases']),'Incomplete fixture cases')
        proc.stdin.write('stop\n');proc.stdin.flush();code=proc.wait(timeout=120);reader.join(timeout=10)
        need(code==0 and not reader.is_alive() and any('Done (' in line for line in lines),'Unclean fixture startup/shutdown')
        paths=[p for p in proof.glob('*.json') if json.loads(p.read_text())['missing_cache_chunks']==8]
        need(len(paths)==1,'No unique synthetic owner witness')
        verified,_=verify(paths[0]);result.update({'pass':True,'exit_code':code,'fixture':data,'independent_witness':verified})
    except Exception as error:result['error']=repr(error)
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=45)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if reader is not None:reader.join(timeout=10)
        legacy.save(OUT/'fixture.json',result)
    print('R40_FIXTURE '+json.dumps({k:v for k,v in result.items() if k!='fixture'}),flush=True)
    return result

def main():
    legacy=load(ROOT/'qa/field-r395/run_runtime.py','r40_legacy')
    build=json.loads((OUT/'build.json').read_text())
    need(legacy.sha(ROOT/'baseline/server.jar')==BASE and build['base_core_sha256']==BASE,'Wrong combined baseline')
    need(legacy.sha(ROOT/'candidate/server.jar')==build['candidate_core_sha256'],'Wrong combined candidate')
    need(legacy.sha(ROOT/'candidate/NeverOverworld.zip')==legacy.PACK and legacy.sha(ROOT/'candidate/NeverNether.zip')==legacy.NETHER,'Wrong paired packs')
    # An opt-in diagnostic property; no endpoint or untrusted command is supplied.
    os.environ['JAVA_TOOL_OPTIONS']=(os.environ.get('JAVA_TOOL_OPTIONS','')+' -Dneverfolia.r40ExportWitness=true').strip()
    report={'schema':1,'build':build,'production_accepted':False,'global_closure_proven':False,'phases':{},'bounded_integration_pass':False}
    original_persisted=legacy.persisted
    def persisted(folder,rows,name):
        saved=original_persisted(folder,rows,name);volume=read_volume(legacy,folder,rows,name)
        hashes={};counts_by_chunk={};encoded={}
        for cx,cz in sorted(TARGETS):
            h=hashlib.sha256();counts=collections.Counter()
            for sy in range(-32,32):
                states=volume.section((cx,sy,cz));need(len(states)==4096,'Incomplete section')
                for i,state in enumerate(states):
                    key=(state['Name'],tuple(sorted(state.get('Properties',{}).items())))
                    if key not in encoded:
                        data=json.dumps(key,separators=(',',':')).encode();encoded[key]=len(data).to_bytes(4,'big')+data
                    h.update(encoded[key]);y=sy*16+(i>>8)
                    if -511<=y<=128:counts[state['Name']]+=1
            hashes[f'{cx},{cz}']=h.hexdigest();counts_by_chunk[f'{cx},{cz}']=dict(counts)
        saved.update({'full_state_hashes':hashes,'chunk_block_counts':counts_by_chunk})
        legacy.save(OUT/(name+'-saved.json'),saved);return saved
    legacy.persisted=persisted
    locations={}
    def phase(name,folder,jar,enabled,reverse=False):
        locations[name]=folder;previous=folder/'plugins/R395Qa/result.json'
        if previous.exists():previous.rename(OUT/(name+'-previous-result.json'))
        with (OUT/(name+'-runner.log')).open('w') as log,contextlib.redirect_stdout(log):
            result=legacy.phase(name,folder,jar,enabled,reverse)
        try:
            need(previous.is_file() and not previous.is_symlink(),'Fresh current report missing')
            fresh=json.loads(previous.read_text());fresh_observation(fresh,reverse)
            need(fresh==result.get('observed'),'Current report mismatch')
            markers=[line for line in (OUT/(name+'.log')).read_text().splitlines() if 'R395 NATURAL QA' in line]
            need(len(markers)==1 and 'R395 NATURAL QA PASS' in markers[0],'No unique current PASS')
            need(result.get('pass') is True and result.get('exit_code')==0,'Failed real server phase')
            for row in fresh['chunks']:
                key=f"{row['chunk_x']},{row['chunk_z']}"
                need(row['water_sha256']==result['saved']['water_hashes'][key],'Live/saved water mismatch')
                need(collections.Counter(row['block_counts'])==collections.Counter(result['saved']['chunk_block_counts'][key]),'Live/saved census mismatch')
            result['fresh_verified']=True
        except Exception as error:result['pass']=False;result['freshness_error']=repr(error)
        legacy.save(OUT/(name+'-phase.json'),result)
        print('R40_PHASE '+json.dumps({'name':name,'pass':result.get('pass'),'error':result.get('error'),'freshness_error':result.get('freshness_error')}),flush=True)
        return result
    try:
        report['synthetic']=run_fixture(legacy)
        need(report['synthetic']['pass'],'Synthetic scene failed; natural acceptance stopped')
        plugin=legacy.prepare_plugin()
        for name,binary,enabled,reverse in (
            ('baseline',ROOT/'baseline/server.jar',False,False),
            ('baseline_repeat',ROOT/'baseline/server.jar',False,False),
            ('baseline_reverse',ROOT/'baseline/server.jar',False,True),
            ('candidate_off',ROOT/'candidate/server.jar',False,False),
            ('candidate',ROOT/'candidate/server.jar',True,False),
            ('reverse',ROOT/'candidate/server.jar',True,True)):
            folder=legacy.setup(name,plugin);report['phases'][name]=phase(name,folder,binary,enabled,reverse)
            if name=='candidate' and report['phases'][name]['pass']:
                report['phases']['restart']=phase('restart',folder,binary,True,False)
            legacy.save(OUT/'runtime.json',report)
        required={'baseline','baseline_repeat','baseline_reverse','candidate_off','candidate','restart','reverse'}
        need(set(report['phases'])==required and all(p['pass'] for p in report['phases'].values()),'A required natural phase failed')
        def equal(a,b):return report['phases'][a]['saved']['full_state_hashes']==report['phases'][b]['saved']['full_state_hashes']
        report['baseline_repeat_equal']=equal('baseline','baseline_repeat')
        report['disabled_equal']=equal('baseline','candidate_off');report['restart_equal']=equal('candidate','restart')
        report['strict_generation_order_equal']={'baseline':equal('baseline','baseline_reverse'),'candidate':equal('candidate','reverse')}
        report['witnesses']={};write_sets={}
        for name in ('candidate','reverse'):
            indexed={}
            for path in (OUT/('proof-'+name)).glob('*.json'):
                d=json.loads(path.read_text());key=(d['chunk_x'],d['chunk_z'])
                if key in TARGETS:
                    need(key not in indexed,'Duplicate target proof');indexed[key]=path
            need(set(indexed)==TARGETS,'Missing target proof')
            rows=[];writes={}
            for key,path in sorted(indexed.items()):
                row,positions=verify(path);rows.append(row);writes[key]=positions
            report['witnesses'][name]=rows;write_sets[name]=writes
            print('R40_WITNESSES '+name+' '+str(len(rows))+' verified',flush=True)
        effects={}
        for left,right in [('baseline','candidate'),('baseline_reverse','reverse')]:
            a=read_volume(legacy,locations[left],report['phases'][left]['observed']['chunks'],'effect_'+left)
            b=read_volume(legacy,locations[right],report['phases'][right]['observed']['chunks'],'effect_'+right)
            changes=0;chunks=0;unexpected=[]
            for cx,cz in sorted(TARGETS):
                actual=set()
                for sy in range(-32,32):
                    old=a.section((cx,sy,cz));new=b.section((cx,sy,cz))
                    for i,(before,after) in enumerate(zip(old,new)):
                        if before==after:continue
                        y=sy*16+(i>>8)
                        good=(-511<=y<=128 and before['Name'] in ('minecraft:air','minecraft:cave_air','minecraft:void_air') and after['Name']=='minecraft:water' and after.get('Properties',{}).get('level')=='0')
                        if not good:
                            if len(unexpected)<32:unexpected.append({'pos':[cx*16+(i&15),y,cz*16+((i>>4)&15)],'before':before,'after':after})
                            continue
                        actual.add(((y+511)<<8)|(i&255))
                need(actual==write_sets[right][(cx,cz)],'Saved changes differ from actual witness writes at '+str((cx,cz)))
                changes+=len(actual);chunks+=bool(actual)
            effects[right]={'air_to_water':changes,'changed_chunks':chunks,'unexpected_examples':unexpected,'pass':not unexpected and changes>0}
        report['effects']=effects
        report['bounded_integration_pass']=(report['baseline_repeat_equal'] and report['disabled_equal'] and report['restart_equal'] and all(e['pass'] for e in effects.values()))
        need(report['bounded_integration_pass'],'Combined safety/integration acceptance failed')
    except Exception as error:report['error']=repr(error)
    finally:
        legacy.save(OUT/'runtime.json',report)
        summary={k:v for k,v in report.items() if k not in ('phases','witnesses','synthetic')}
        summary['phase_status']={k:p.get('pass') for k,p in report['phases'].items()}
        summary['fixture_pass']=report.get('synthetic',{}).get('pass')
        summary['witness_counts']={k:len(v) for k,v in report.get('witnesses',{}).items()}
        legacy.save(OUT/'summary.json',summary);print('R40_RESULT '+json.dumps(summary,separators=(',',':')),flush=True)
    return 0 if report['bounded_integration_pass'] else 2
if __name__=='__main__':raise SystemExit(main())
