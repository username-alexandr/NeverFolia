#!/usr/bin/env python3
from pathlib import Path
import argparse,hashlib,io,json,zipfile

TARGET='data/minecraft/worldgen/noise_settings/overworld.json'

def sha(raw):return hashlib.sha256(raw).hexdigest()

def patch(raw:bytes)->bytes:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist()
        if TARGET not in names:raise ValueError('NeverOverworld noise settings missing')
        data=json.loads(z.read(TARGET))
        if data.get('sea_level')==128:
            return raw
        if data.get('sea_level')!=63:
            raise ValueError('Unexpected existing sea_level: '+repr(data.get('sea_level')))
        data['sea_level']=128
        replacement=(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode()
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as dst:
            for info in z.infolist():
                if info.is_dir():continue
                dst.writestr(info, replacement if info.filename==TARGET else z.read(info.filename))
        return out.getvalue()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('src',type=Path);ap.add_argument('dst',type=Path);a=ap.parse_args()
    raw=a.src.read_bytes();out=patch(raw);a.dst.parent.mkdir(parents=True,exist_ok=True);a.dst.write_bytes(out)
    with zipfile.ZipFile(io.BytesIO(out)) as z:
        data=json.loads(z.read(TARGET))
    assert data['sea_level']==128
    print('R3931_PACK',json.dumps({'input_sha256':sha(raw),'output_sha256':sha(out),'sea_level':data['sea_level']}))
if __name__=='__main__':main()
