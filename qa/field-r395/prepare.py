#!/usr/bin/env python3
"""Compile CI-only observer instrumentation. No gameplay JAR/datapack writes."""
from __future__ import annotations
import argparse
import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    'server.jar': '411f628603ae531216c173fde1dbd8c702effb170889f72e5f2c0f1af81b6a32',
    'NeverOverworld.zip': 'a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be',
    'NeverNether.zip': '5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10',
}
SOURCE = 'native/overworld-r38/NeverOverworldWaterAuditR38.java'
SOURCE_BLOB = 'b8c42a16cc247c9922a4030d0c019736058abf81'
CLASS = 'net/minecraft/world/level/chunk/NeverOverworldWaterAuditR38.class'
OLD_SELECTION = '            || (cx >= 11 && cx <= 13 && cz >= 3 && cz <= 5);'
NEW_SELECTION = ('            || (cx >= 11 && cx <= 13 && cz >= 3 && cz <= 5)\n'
                 '            || (cx >= -207 && cx <= -197 && cz >= -218 && cz <= -208);')
MASK_WRITE = '''            // R395 read-only evidence: original/final masks and per-column floors.
            String stem=chunk.getPos().x()+"_"+chunk.getPos().z();
            Path masks=dir.resolve(stem+".water.gz");
            try (var stream=new java.io.DataOutputStream(new java.util.zip.GZIPOutputStream(Files.newOutputStream(masks)))) {
                stream.writeInt(0x57415431);
                stream.writeInt(snapshot.minY);stream.writeInt(snapshot.maxY);
                for(int floor:snapshot.floors) stream.writeInt(floor);
                stream.writeInt(beforeMask.length);stream.write(beforeMask);stream.write(afterMask);
            }
            report.addProperty("audit_revision","R395");
            report.addProperty("run_id",System.getProperty("neverfolia.waterAuditRunId",""));
            report.addProperty("mask_file",masks.getFileName().toString());
            report.addProperty("mask_sha256",digest(Files.readAllBytes(masks)));
'''


def need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def blob(raw: bytes) -> str:
    return hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()


def once(text: str, old: str, new: str) -> str:
    need(text.count(old) == 1, 'Unexpected/ambiguous observer source anchor')
    return text.replace(old, new, 1)


def transform(text: str) -> str:
    updated = once(text, OLD_SELECTION, NEW_SELECTION)
    anchor = '            Path dir=Path.of(DIRECTORY);Files.createDirectories(dir);\n'
    return once(updated, anchor, anchor + MASK_WRITE)


def extract_one(archive: zipfile.ZipFile, suffix: str, destination: Path) -> None:
    matches = [n for n in archive.namelist() if n.endswith(suffix)]
    need(len(matches) == 1, 'Missing/ambiguous exact debug member: ' + suffix)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(archive.read(matches[0]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'debug', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    candidate, debug, out = (p.resolve() for p in (args.candidate, args.debug, args.output))
    out.mkdir(parents=True, exist_ok=True)
    work = ROOT / '.work/r395-build'
    work.mkdir(parents=True, exist_ok=False)
    for name, expected in EXPECTED.items():
        need(sha(candidate / name) == expected, 'Wrong candidate: ' + name)
    raw = (ROOT / SOURCE).read_bytes()
    need(blob(raw) == SOURCE_BLOB, 'Observer source changed; refusing an approximate edit')
    updated = transform(raw.decode('utf-8'))
    source_dir = out / 'observer-source'
    source_dir.mkdir()
    source = source_dir / 'NeverOverworldWaterAuditR38.java'
    source.write_text(updated)
    (source_dir / 'observer.patch').write_text(''.join(difflib.unified_diff(
        raw.decode().splitlines(True), updated.splitlines(True),
        fromfile='a/' + SOURCE, tofile='b/' + SOURCE)))
    libs = work / 'libs'
    libs.mkdir()
    original_class = None
    with zipfile.ZipFile(candidate / 'server.jar') as archive:
        need(len(archive.namelist()) == len(set(archive.namelist())), 'Duplicate JAR members')
        for i, name in enumerate(archive.namelist()):
            if name.endswith('.jar') and name.startswith(('META-INF/libraries/', 'META-INF/versions/')):
                payload = archive.read(name)
                (libs / (str(i) + '-' + name.rsplit('/', 1)[-1])).write_bytes(payload)
                if name.endswith('/folia-26.2.jar'):
                    need(original_class is None, 'Ambiguous bundled engine')
                    with zipfile.ZipFile(io.BytesIO(payload)) as engine:
                        original_class = engine.read(CLASS)
    need(original_class is not None, 'Actual bundled observer class missing')
    with zipfile.ZipFile(debug / 'diagnostics.zip') as archive:
        for suffix, target in (
            ('qa/field-r37/R37DungeonQa.jar', ROOT / '.work/r395-plugins/R37DungeonQa.jar'),
            ('qa/field-r38/R38TrialQa.jar', ROOT / '.work/r395-plugins/R38TrialQa.jar'),
            ('materialized/folia-server/src/minecraft/java/net/minecraft/network/protocol/game/GameProtocols.java', ROOT / '.work/Folia/folia-server/src/minecraft/java/net/minecraft/network/protocol/game/GameProtocols.java'),
            ('folia-api/build/libs/folia-api-26.2-R0.1-SNAPSHOT.jar', libs / 'folia-api.jar'),
        ):
            extract_one(archive, suffix, target)
    classes = work / 'classes'
    classes.mkdir()
    command = ['javac', '--release', '25', '-classpath', os.pathsep.join(map(str, sorted(libs.glob('*.jar')))),
               '-d', str(classes), str(source), str(ROOT / 'qa/field-r395/AuditAgent.java')]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (out / 'javac.log').write_text(result.stdout)
    print(result.stdout, flush=True)
    need(result.returncode == 0, 'Actual-core observer compilation failed')
    agent = out / 'NeverFolia-R395-Observer-CI-ONLY.jar'
    with zipfile.ZipFile(agent, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\nPremain-Class: neverfolia.qa.r395.AuditAgent\n\n')
        for path in (classes / 'neverfolia').rglob('*.class'):
            archive.write(path, path.relative_to(classes).as_posix())
        archive.writestr('r395/audit.class', (classes / CLASS).read_bytes())
        archive.writestr('r395/expected.sha256', hashlib.sha256(original_class).hexdigest())
    proof = {'pass': True, 'gameplay_files_unchanged': {n: sha(candidate / n) == v for n, v in EXPECTED.items()},
             'inputs': EXPECTED, 'observer_source_blob': SOURCE_BLOB, 'instrumented_class': CLASS,
             'original_class_sha256': hashlib.sha256(original_class).hexdigest(),
             'diagnostic_class_sha256': sha(classes / CLASS), 'agent_sha256': sha(agent),
             'compiler': subprocess.run(['javac', '-version'], text=True, capture_output=True, check=True).stdout,
             'scope': 'Only observer coverage and read-only mask export changed; not a rebuilt gameplay engine'}
    need(all(proof['gameplay_files_unchanged'].values()), 'Candidate changed during build')
    (out / 'observer-build.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof, indent=2), flush=True)


if __name__ == '__main__':
    main()
