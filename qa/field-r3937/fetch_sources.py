#!/usr/bin/env python3
from pathlib import Path
import hashlib,sys,urllib.request

SOURCES = {
    "hearths": {
        "filename": "Hearths v1.0.5.dp.zip",
        "url": "https://cdn.modrinth.com/data/XCIMrYn0/versions/qtY3MDWq/Hearths%20v1.0.5.dp.zip",
        "sha256": "cf6877c2ffbdfba29d49452a90fdf6ab06b7e7e564b808abd2361976cddd6420",
    },
    "dungeons_and_taverns": {
        "filename": "Dungeons and Taverns v5.3.2.zip",
        "url": "https://cdn.modrinth.com/data/tpehi7ww/versions/CS77UwHE/Dungeons%20and%20Taverns%20v5.3.2.zip",
        "sha256": "4096cd6372e0f244efa0e85c4d884bd85afe665a84a050280acd483b3222b4f9",
    },
    "explorify": {
        "filename": "Explorify v1.6.5.dp.zip",
        "url": "https://cdn.modrinth.com/data/HSfsxuTo/versions/BKKKBD2V/Explorify%20v1.6.5.dp.zip",
        "sha256": "09dea87923b8dc021a6694f7c6487725b1a666e255e122bce55fdd2dc3377d4f",
    },
    "structory_towers": {
        "filename": "Structory_Towers_v1.0.17.zip",
        "url": "https://cdn.modrinth.com/data/j3FONRYr/versions/uxUF2h4B/Structory_Towers_v1.0.17.zip",
        "sha256": "90af7fddea07973fef035b0c99213cc6b4c2baafeeb9c7f8a230b6e256687aa0",
    },
    "better_monuments": {
        "filename": "Repurposed_Structures-Better_Monuments_v7.zip",
        "url": "https://mediafilez.forgecdn.net/files/5809/259/Repurposed_Structures-Better_Monuments_v7.zip",
        "sha256": "c76cd5ab549974b051a352a633abd2f78a916acc40392bc53ba0581c3116a8c9",
    },
}

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: fetch_sources.py OUTPUT_DIR")
    out=Path(sys.argv[1])
    out.mkdir(parents=True,exist_ok=True)

    for key,row in SOURCES.items():
        path=out/row["filename"]
        req=urllib.request.Request(row["url"],headers={"User-Agent":"NeverFolia-R3937-CI"})
        with urllib.request.urlopen(req,timeout=120) as r, path.open("wb") as f:
            while True:
                chunk=r.read(1024*1024)
                if not chunk:break
                f.write(chunk)
        actual=sha256(path)
        if actual!=row["sha256"]:
            raise SystemExit(f"{key}: SHA256 mismatch {actual} != {row['sha256']}")
        print(f"R3937_SOURCE {key} {path.name} {actual} {path.stat().st_size}")

if __name__=="__main__":
    main()
