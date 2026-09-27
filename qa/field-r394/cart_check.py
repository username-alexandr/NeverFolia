#!/usr/bin/env python3
"""Compile and run the isolated full-model cart fixture; no production worlds."""
from pathlib import Path
import argparse,json,os,subprocess,zipfile
import run_checks
from water_regression import ROOT,dependencies,sha,EXPECTED

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','debug','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.candidate=a.candidate.resolve();a.debug=a.debug.resolve();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
    build=json.loads((a.output/'r394-build.json').read_text())
    expected={**EXPECTED,'NeverOverworld.zip':build['output_sha256']}
    actual={n:sha(a.candidate/n) for n in expected}
    if actual!=expected:raise ValueError('Unexpected candidate bytes')
    (a.output/'r394-inputs.json').write_text(json.dumps(actual,indent=2)+'\n')
    dependencies(a.candidate,a.debug,a.output)
    libs=ROOT/'.work/r394-runtime-libs';classes=ROOT/'.work/r394-cart-classes';classes.mkdir(parents=True,exist_ok=True)
    run=subprocess.run(['javac','--release','25','-cp',os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar'))),'-d',str(classes),str(ROOT/'qa/field-r394/R394CartQaPlugin.java')],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (a.output/'cart-javac.log').write_text(run.stdout);print(run.stdout,flush=True)
    if run.returncode:raise ValueError('Cart fixture compilation failed against real engine')
    dest=ROOT/'.work/r394-plugins';dest.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest/'R394CartQa.jar','w',zipfile.ZIP_DEFLATED) as z:
        for p in classes.rglob('*.class'):z.write(p,str(p.relative_to(classes)))
        z.writestr('plugin.yml',"name: R394CartQa\nversion: '1'\nmain: R394CartQaPlugin\napi-version: '26.2'\nfolia-supported: true\n")
    (a.output/'cart-java-build.json').write_text(json.dumps({'pass':True,'core_sha256':actual['server.jar'],'fixture_sha256':sha(dest/'R394CartQa.jar')},indent=2)+'\n')
    run_checks.carts(a.candidate,a.output)
if __name__=='__main__':main()
