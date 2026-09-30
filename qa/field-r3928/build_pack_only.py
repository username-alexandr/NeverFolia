#!/usr/bin/env python3
from pathlib import Path
import argparse,hashlib,json,zipfile

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    with zipfile.ZipFile(a.input) as zin:
        names=zin.namelist()
        assert "data/minecraft/worldgen/noise_settings/overworld.json" in names
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(a.output,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as zout:
            for info in zin.infolist():
                raw=zin.read(info.filename)
                if info.filename=="data/minecraft/worldgen/noise_settings/overworld.json":
                    d=json.loads(raw)
                    assert d.get("sea_level")==63, d.get("sea_level")
                    d["sea_level"]=128
                    raw=(json.dumps(d,indent=2,ensure_ascii=False)+"\n").encode()
                zout.writestr(info,raw)
    with zipfile.ZipFile(a.output) as z:
        assert z.testzip() is None
        d=json.loads(z.read("data/minecraft/worldgen/noise_settings/overworld.json"))
        assert d["sea_level"]==128
    print(json.dumps({"pass":True,"sea_level":128,"sha256":hashlib.sha256(a.output.read_bytes()).hexdigest(),"size":a.output.stat().st_size}))

if __name__=="__main__":main()
