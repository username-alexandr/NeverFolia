#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

ROOT_FINGERPRINT_ENTRY = "neveroverworld-worldgen-fingerprint.json"
RESOURCE_FINGERPRINT_ENTRY = "data/neverfolia/neveroverworld/worldgen_fingerprint.json"
FINGERPRINT_ENTRIES = frozenset((ROOT_FINGERPRINT_ENTRY, RESOURCE_FINGERPRINT_ENTRY))
ALGORITHM = "sha256-path-and-content-v1"
WORLDGEN_ID = "NR-DEV-1"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld fingerprint] {message}")


def read_entries(path: Path) -> dict[str, bytes]:
    if not path.is_file():
        fail(f"pack not found: {path}")
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in Path(name).parts:
                fail(f"unsafe ZIP path: {name}")
            if name in entries:
                fail(f"duplicate ZIP entry: {name}")
            entries[name] = zf.read(info)
    return entries


def content_digest(entries: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in sorted(entries):
        if name in FINGERPRINT_ENTRIES:
            continue
        name_bytes = name.encode("utf-8")
        payload = entries[name]
        digest.update(len(name_bytes).to_bytes(4, "big"))
        digest.update(name_bytes)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def fingerprint_document(entries: dict[str, bytes]) -> dict:
    return {
        "schema": 1,
        "worldgen_id": WORLDGEN_ID,
        "algorithm": ALGORITHM,
        "content_sha256": content_digest(entries),
        "entry_count_excluding_fingerprint": sum(1 for name in entries if name not in FINGERPRINT_ENTRIES),
    }


def write_zip(path: Path, entries: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_raw = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    os.close(fd)
    tmp = Path(tmp_raw)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for name in sorted(entries):
                zf.writestr(name, entries[name])
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def inject(path: Path) -> dict:
    entries = read_entries(path)
    for name in FINGERPRINT_ENTRIES:
        entries.pop(name, None)
    document = fingerprint_document(entries)
    encoded = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    entries[ROOT_FINGERPRINT_ENTRY] = encoded
    entries[RESOURCE_FINGERPRINT_ENTRY] = encoded
    write_zip(path, entries)
    verify(path)
    print("[NeverFolia][NeverOverworld fingerprint] INJECT OK")
    print(f"  pack: {path}")
    print(f"  content_sha256: {document['content_sha256']}")
    return document


def verify(path: Path) -> dict:
    entries = read_entries(path)
    root_raw = entries.get(ROOT_FINGERPRINT_ENTRY)
    resource_raw = entries.get(RESOURCE_FINGERPRINT_ENTRY)
    if root_raw is None:
        fail(f"{ROOT_FINGERPRINT_ENTRY} is missing")
    if resource_raw is None:
        fail(f"{RESOURCE_FINGERPRINT_ENTRY} is missing")
    if root_raw != resource_raw:
        fail("root and datapack-resource fingerprints differ")
    try:
        document = json.loads(root_raw.decode("utf-8"))
    except Exception as exc:
        fail(f"invalid fingerprint JSON: {exc}")
    if document.get("worldgen_id") != WORLDGEN_ID:
        fail(f"worldgen_id mismatch: {document.get('worldgen_id')!r}")
    if document.get("algorithm") != ALGORITHM:
        fail(f"algorithm mismatch: {document.get('algorithm')!r}")
    actual = content_digest(entries)
    expected = document.get("content_sha256")
    if actual != expected:
        fail(f"content fingerprint mismatch: expected {expected}, got {actual}")
    expected_count = sum(1 for name in entries if name not in FINGERPRINT_ENTRIES)
    if document.get("entry_count_excluding_fingerprint") != expected_count:
        fail("entry count mismatch")
    print("[NeverFolia][NeverOverworld fingerprint] VERIFY OK")
    print(f"  pack: {path}")
    print(f"  content_sha256: {actual}")
    return document


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="neveroverworld-fingerprint-") as tmp_raw:
        tmp = Path(tmp_raw)
        pack = tmp / "test.zip"
        with zipfile.ZipFile(pack, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("b.txt", b"two")
            zf.writestr("a.txt", b"one")
        first = inject(pack)["content_sha256"]
        second = verify(pack)["content_sha256"]
        if first != second:
            fail("SELF-TEST: injected and verified digests differ")
        entries = read_entries(pack)
        if entries[ROOT_FINGERPRINT_ENTRY] != entries[RESOURCE_FINGERPRINT_ENTRY]:
            fail("SELF-TEST: dual fingerprint entries differ")
        repacked = tmp / "repacked.zip"
        with zipfile.ZipFile(repacked, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("a.txt", b"one")
            zf.writestr("b.txt", b"two")
        if inject(repacked)["content_sha256"] != first:
            fail("SELF-TEST: fingerprint depends on ZIP order/compression")
        entries = read_entries(pack)
        entries["a.txt"] = b"changed"
        write_zip(pack, entries)
        try:
            verify(pack)
        except SystemExit:
            pass
        else:
            fail("SELF-TEST: mutated pack was accepted")
    print("[NeverFolia][NeverOverworld fingerprint] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject or verify deterministic NeverOverworld datapack fingerprints")
    parser.add_argument("--input", type=Path, help="NeverOverworld datapack ZIP")
    parser.add_argument("--inject", action="store_true", help="Inject/replace fingerprint in-place")
    parser.add_argument("--verify", action="store_true", help="Verify an existing fingerprint")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.input is None:
        parser.error("--input is required unless --self-test is used")
    if args.inject == args.verify:
        parser.error("choose exactly one of --inject or --verify")
    if args.inject:
        inject(args.input)
    else:
        verify(args.input)


if __name__ == "__main__":
    main()
