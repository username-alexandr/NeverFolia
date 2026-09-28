#!/usr/bin/env python3
"""Keep the full resource audit negative while separately proving the intended delta."""
from pathlib import Path
import importlib.util,json
import combine_content as c
import run_combined as r

def main():
    report={'pass':False,'full_resource_acceptance':False,'production_accepted':False}
    try:
        build=json.loads((r.OUT/'combined-content.json').read_text());r.need(build['pass'],'Combined pack not built')
        core=r.exact_file(r.ROOT/'swift-input','server-r3915.jar',c.CORE)
        base=r.exact_file(r.ROOT/'inputs','NeverOverworld.zip',c.BASE)
        fixed=r.exact_file(r.OUT,'NeverOverworld-R3915-Combined.zip',build['output_sha256'])
        spec=importlib.util.spec_from_file_location('combined_resource_audit',r.ROOT/'scripts/audit-neveroverworld-r39-resources.py')
        audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
        before=audit.audit_files(core,base);after=audit.audit_files(core,fixed)
        r.save('combined-resource-before.json',before);r.save('combined-resource-after.json',after)
        r.need(not before['errors'] and not after['errors'],'Resource decoding error')
        a={(x['kind'],x['id']) for x in before['missing']};b={(x['kind'],x['id']) for x in after['missing']}
        expected={('template','nova_structures:tavern/tavern_event_trader_car_'+role+'_'+biome) for role in ('cartographer','cleric') for biome in c.BIOMES}
        r.need(a-b==expected,'Unexpected removed resource gaps')
        r.need(not b-a,'New missing resource introduced')
        r.need(after['counts']['roots']==before['counts']['roots'],'Root coverage changed')
        r.need(set(after['roots'][i]['id'] for i in range(len(after['roots'])))==set(before['roots'][i]['id'] for i in range(len(before['roots']))),'Root identities changed')
        report.update({'pass':True,'before':before['counts'],'after':after['counts'],'removed':sorted(a-b),'introduced':sorted(b-a),'full_resource_acceptance':after['pass'],'core_sha256':c.CORE,'pack_sha256':build['output_sha256']})
        print('COMBINED_RESOURCE_DELTA',json.dumps(report),flush=True)
        for issue in after['missing']:print('STILL_MISSING',issue['kind'],issue['id'],flush=True)
    except Exception as e:report['error']=repr(e);raise
    finally:r.save('combined-resource-delta.json',report)
if __name__=='__main__':main()
