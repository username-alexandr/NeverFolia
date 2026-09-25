#!/usr/bin/env python3
"""Fail-closed acceptance of the fixed R15 Nether field sample; optional test ZIP.

Reads a stopped disposable world and reports only. Never edits locks or regions.
A passing 50-chunk sample is not whole-world or production-release acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any
import zipfile

SEED = -2996952393010080672
NATIVE = 'NN-R15-FIELD-CLEANUP-1'
HEIGHT = 'NN-R14-SUBSTRATE-1-ROOF512'
EXPECTED = {(x, z) for cx, cz in ((-4, 0), (-195, -393))
            for x in range(cx-2, cx+3) for z in range(cz-2, cz+3)}
MARKER = 'data/neverfolia/nevernether/native_profile.json'


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def integer(value: Any, label: str, minimum: int = 0) -> int:
    require(type(value) is int and value >= minimum, 'invalid integer: '+label)
    return value


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: '+key)
        result[key] = value
    return result


def json_bytes(raw: bytes) -> dict[str, Any]:
    require(len(raw) <= 8*1024*1024, 'oversized evidence document')
    result = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object)
    require(isinstance(result, dict), 'evidence must be a JSON object')
    return result


def read_json(path: Path) -> dict[str, Any]:
    with path.open('rb') as stream:
        return json_bytes(stream.read(8*1024*1024+1))


def chunks(value: Any) -> set[tuple[int, int]]:
    require(isinstance(value, list), 'chunk list missing')
    require(all(isinstance(p, list) and len(p) == 2
                and all(type(n) is int for n in p) for p in value), 'invalid chunk coordinates')
    result = {tuple(p) for p in value}
    require(len(result) == len(value), 'duplicate chunks')
    return result


def evaluate(plan: dict, audit: dict, summary: dict) -> dict:
    """Validate complete evidence, then apply R15 field gates without changing it."""
    for name, document in (('plan', plan), ('audit', audit), ('summary', summary)):
        require(type(document.get('schema')) is int and document['schema'] == 1,
                'unsupported schema: '+name)
        require(integer(document.get('chunk_count'), name+'.chunk_count') == 50,
                'expected exactly 50 chunks: '+name)
    for name, document in (('plan', plan), ('summary', summary)):
        require(type(document.get('seed')) is int and document['seed'] == SEED,
                'wrong seed: '+name)
    require(chunks(plan.get('chunks')) == EXPECTED, 'plan differs from fixed two-area sample')
    require(chunks(audit.get('chunks')) == EXPECTED, 'audit coverage differs from plan')
    require(plan.get('normal_stop') is True, 'world was not stopped normally')
    require(type(plan.get('process_exit_code')) is int and plan['process_exit_code'] == 0,
            'server exit was not zero')
    require(audit.get('read_only') is True and audit.get('audit') == 'nevernether-field-integrity-r1',
            'unexpected audit identity')
    require(audit.get('range_y') == [-128, 511], 'incomplete audit height range')
    require(integer(audit.get('pocket_limit'), 'pocket_limit') == 64, 'incomplete cavity range')
    require(summary.get('natural_integrity_runtime_pass') is True, 'runtime gate did not pass')
    require(integer(summary.get('full_chunks'), 'full_chunks') == 50, 'not all chunks FULL')
    require(summary.get('roof512_pass') is True and summary.get('roof_failures') == [],
            'roof/padding gate did not pass')
    require(integer(summary.get('roof_y'), 'roof_y') == 512, 'wrong roof Y')
    require(integer(summary.get('roof_cells_checked'), 'roof_cells_checked') == 12800,
            'roof coverage incomplete')
    require(summary.get('padding_y') == [513, 527]
            and integer(summary.get('padding_non_air'), 'padding_non_air') == 0,
            'technical padding is not empty')
    counts = audit.get('counts')
    require(isinstance(counts, dict), 'audit counts missing')
    samples = audit.get('enclosed_air_samples')
    require(isinstance(samples, list), 'cavity samples missing')
    truncated = audit.get('samples_truncated')
    require(isinstance(truncated, dict)
            and all(truncated.get(k) is False for k in ('enclosed_air', 'lava_air_below', 'hanging_lava_shelf')),
            'truncated or unknown evidence cannot pass')
    require(len(samples) == integer(counts.get('enclosed_small_air_components'), 'cavity count'),
            'cavity samples/count mismatch')
    for key, sample_key in (('source_lava_with_air_below', 'source_lava_air_below_samples'),
                            ('hanging_source_lava_shelf_candidates', 'hanging_lava_shelf_samples')):
        n = integer(counts.get(key), key)
        require(type(summary.get(key)) is int and summary[key] == n, 'summary/count mismatch: '+key)
        require(isinstance(audit.get(sample_key), list) and len(audit[sample_key]) == n,
                'lava samples/count mismatch: '+key)
    body = roof = edge = unknown_body = original_owner = original_blocks = total_blocks = 0
    seen: set[tuple[int, int, int]] = set()
    for sample in samples:
        require(isinstance(sample, dict), 'invalid cavity sample')
        size = integer(sample.get('size'), 'cavity size', 1)
        require(size <= 64, 'cavity larger than reporting limit')
        box, point = sample.get('bbox'), sample.get('sample')
        require(isinstance(box, list) and len(box) == 6 and all(type(n) is int for n in box),
                'invalid cavity bbox')
        require(all(box[i] <= box[i+3] for i in range(3)) and -128 <= box[1] <= box[4] <= 511,
                'invalid cavity bounds')
        require(all(box[i+3]-box[i]+1 <= size for i in range(3)), 'unbounded cavity bbox')
        require(isinstance(point, list) and len(point) == 3 and all(type(n) is int for n in point)
                and all(box[i] <= point[i] <= box[i+3] for i in range(3)), 'invalid sample position')
        require(tuple(point) not in seen, 'duplicate cavity sample')
        seen.add(tuple(point))
        require(all((x, z) in EXPECTED for x in range(box[0]//16, box[3]//16+1)
                    for z in range(box[2]//16, box[5]//16+1)), 'cavity outside audited chunks')
        provenance = sample.get('provenance_counts')
        require(isinstance(provenance, dict) and sum(integer(v, 'provenance') for v in provenance.values()) == size,
                'incomplete cavity provenance')
        original = provenance == {'original': size}
        touches = any(box[i]//16 != box[i+3]//16 or box[i] % 16 == 0 or box[i+3] % 16 == 15
                      for i in (0, 2))
        require(sample.get('original_only') is original
                and sample.get('touches_owner_chunk_boundary') is touches, 'cavity classification mismatch')
        total_blocks += size
        if size > 4:
            continue
        if touches:
            edge += 1
            continue
        if original:
            original_owner += 1
            original_blocks += size
            if box[1] >= 507:
                roof += 1
            else:  # Includes components crossing from the body into the roof envelope.
                body += 1
        elif box[1] < 507 and set(provenance) - {'original', 'external', 'proposal'}:
            unknown_body += 1
    require(total_blocks == integer(counts.get('enclosed_small_air_blocks'), 'cavity blocks'),
            'cavity block count mismatch')
    require(original_owner == integer(counts.get('r15_original_owner_micro_components'), 'owner count')
            and original_blocks == integer(counts.get('r15_original_owner_micro_blocks'), 'owner blocks'),
            'original-owner samples/count mismatch')
    errors = []
    if counts['hanging_source_lava_shelf_candidates']:
        errors.append('hanging source-lava shelf remains in the fixed sample')
    if body:
        errors.append(f'{body} original owner-contained micro-cavities intersect Y=-128..506')
    if unknown_body:
        errors.append(f'{unknown_body} body micro-cavities have unknown/unrecorded provenance')
    return {'schema': 1, 'seed': SEED, 'chunk_count': 50, 'nether_field_acceptance_pass': not errors,
            'original_owner_body_micro_components': body, 'roof_envelope_micro_components': roof,
            'chunk_edge_micro_components': edge, 'hanging_lava_shelf_candidates': counts['hanging_source_lava_shelf_candidates'],
            'errors': errors, 'production_ready': False,
            'scope': 'Fixed 50-chunk Nether sample; chunk-edge and Y=507..511 cavities are diagnostic. Not whole-world acceptance.'}


def verify_locks(world: Path) -> None:
    for name, expected in (('.neverfolia-nevernether-height.lock', HEIGHT),
                           ('.neverfolia-nevernether-native.lock', NATIVE)):
        path = world / name
        require(stat.S_ISREG(path.lstat().st_mode), 'non-regular saved lock: '+name)
        with path.open('rb') as stream:
            require(stream.read(257) == (expected+'\n').encode(), 'saved lock mismatch: '+name)


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def package(artifacts: Path, accepted: dict, source_sha: str) -> Path:
    require(accepted.get('nether_field_acceptance_pass') is True, 'cannot package failed acceptance')
    require(re.fullmatch(r'[0-9a-f]{40}', source_sha) is not None, 'full source SHA required')
    jar, pack = artifacts/'server.jar', artifacts/'NeverNether-R15-FieldR1.zip'
    for file in (jar, pack):
        require(file.is_file(), 'candidate input missing: '+str(file))
        with zipfile.ZipFile(file) as archive:
            require(archive.testzip() is None, 'corrupt candidate input: '+str(file))
    with zipfile.ZipFile(pack) as archive:
        require(len(archive.namelist()) == len(set(archive.namelist())), 'duplicate datapack entries')
        with archive.open(MARKER) as stream:
            payload = stream.read(65537)
            require(len(payload) <= 65536, 'oversized native marker')
            marker = json_bytes(payload)
        require(type(marker.get('schema')) is int and marker['schema'] == 1
                and marker.get('profile') == NATIVE and marker.get('requires_height_profile') == HEIGHT
                and marker.get('new_world_required') is True, 'incorrect candidate native profile')
        fingerprint = json_bytes(archive.read('nevernether-worldgen-fingerprint.json'))
        digest = fingerprint.get('content_sha256')
        require(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest) is not None, 'missing content fingerprint')
        require(digest == read_json(artifacts/'r15-pack-build.json').get('content_sha256'),
                'pack build/fingerprint mismatch')
    info = {'schema': 1, 'source_sha': source_sha, 'run_id': os.environ.get('GITHUB_RUN_ID'),
            'native_profile': NATIVE, 'height_profile': HEIGHT, 'java_major': 25,
            'jar_sha256': sha256(jar), 'pack_sha256': sha256(pack), 'production_ready': False,
            'scope': 'Nether-only disposable test world; not an upgrade package for existing worlds.'}
    note = ('NeverFolia R15 — ТЕСТОВЫЙ КАНДИДАТ NETHER\n\n'
            'Только новый отдельный тестовый сервер. Java 25. Не заменяйте рабочий сервер этим архивом.\n'
            'Создайте world/datapacks и положите туда datapacks/NeverNether.zip ДО первого запуска.\n'
            f'В server.properties задайте level-name=world и level-seed={SEED}.\n'
            'Команда запуска: java -Xms1G -Xmx4G -jar server.jar --nogui\n'
            'Прочитайте EULA; подтверждайте её только при согласии с условиями.\n'
            'Не удаляйте .neverfolia-nevernether-*.lock и не переносите старые region-файлы.\n'
            'NeverOverworld и NeverEnd датапаки не включены. Это не полный дистрибутив проекта.\n'
            'Проверены 50 чанков одного seed. Полный мир, многопользовательская нагрузка и миграция не приняты.\n')
    memory = {'BUILD-INFO.json': (json.dumps(info, indent=2)+'\n').encode(),
              'ACCEPTANCE.json': (json.dumps(accepted, indent=2)+'\n').encode(),
              'README-RU.txt': note.encode('utf-8')}
    sums = {'server.jar': info['jar_sha256'], 'datapacks/NeverNether.zip': info['pack_sha256']}
    sums.update({name: hashlib.sha256(data).hexdigest() for name, data in memory.items()})
    memory['SHA256SUMS.txt'] = ''.join(f'{digest}  {name}\n' for name, digest in sorted(sums.items())).encode()
    target = artifacts/f'NeverFolia-R15-TEST-{source_sha[:7]}.zip'
    with tempfile.NamedTemporaryFile(dir=artifacts, suffix='.tmp', delete=False) as stream:
        temp = Path(stream.name)
    try:
        with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.write(jar, 'server.jar')
            archive.write(pack, 'datapacks/NeverNether.zip')
            for name, data in memory.items():
                archive.writestr(name, data)
        os.link(temp, target)  # Create-only: never overwrite an already published candidate.
    finally:
        temp.unlink(missing_ok=True)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--world', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--package', action='store_true')
    args = parser.parse_args()
    report: dict[str, Any] = {'schema': 1, 'source_sha': args.source_sha,
                              'nether_field_acceptance_pass': False, 'production_ready': False}
    try:
        require(re.fullmatch(r'[0-9a-f]{40}', args.source_sha) is not None, 'invalid source SHA')
        report.update(evaluate(read_json(args.artifacts/'natural-integrity-plan.json'),
                               read_json(args.artifacts/'nether-field-integrity.json'),
                               read_json(args.artifacts/'nevernether-natural-summary.json')))
        verify_locks(args.world)
        report['saved_native_locks_verified'] = True
        if args.package and report['nether_field_acceptance_pass']:
            target = package(args.artifacts, report, args.source_sha)
            report['test_bundle'] = target.name
            report['test_bundle_sha256'] = sha256(target)
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
        report['nether_field_acceptance_pass'] = False
        report['errors'] = [str(error)]
    args.artifacts.mkdir(parents=True, exist_ok=True)
    (args.artifacts/'r15-acceptance.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['nether_field_acceptance_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
