#!/usr/bin/env python3
"""Package a NEW-world field-test candidate, not a production acceptance.

Only reads the completed run's binaries/reports. No world or lock is opened,
modified, adopted or deleted. The output is created exclusively after checks.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

SEED = -2996952393010080672
FORESTS = ('minecraft:forest', 'minecraft:birch_forest', 'minecraft:taiga')
VILLAGES = ('minecraft:village_plains', 'minecraft:village_desert')
TARGETS = {('forest', t) for t in FORESTS} | {('village', t) for t in VILLAGES}
SMOKES = ('TreePreservationSmoke', 'VillageFoundationSmoke', 'FloodBoundarySmoke',
          'DesertR1Smoke', 'SandstormR1Smoke')


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def read_json(path: Path) -> tuple[dict, bytes]:
    with path.open('rb') as stream:
        raw = stream.read(2_000_001)
    require(len(raw) <= 2_000_000, f'oversized evidence: {path.name}')
    def object_pairs(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, f'duplicate JSON key: {key}')
            value[key] = item
        return value
    def invalid_constant(value):
        raise ValueError('non-finite JSON constant: ' + value)
    value = json.loads(raw, object_pairs_hook=object_pairs, parse_constant=invalid_constant)
    require(isinstance(value, dict), f'JSON object required: {path.name}')
    return value, raw


def coordinates(values) -> set[tuple[int, int]]:
    require(isinstance(values, list) and 1 <= len(values) <= 324, 'invalid chunk list')
    require(all(isinstance(p, list) and len(p) == 2 and all(type(v) is int for v in p)
                for p in values), 'invalid chunk coordinates')
    points = {tuple(p) for p in values}
    require(len(points) == len(values), 'duplicate chunks')
    return points


def bounds(boxes):
    require(isinstance(boxes, list) and 1 <= len(boxes) <= 1000, 'invalid piece list')
    for box in boxes:
        require(isinstance(box, list) and len(box) == 6 and all(type(v) is int for v in box)
                and all(box[i] <= box[i+3] for i in range(3)), 'invalid piece box')
    x0, z0 = min(b[0] for b in boxes), min(b[2] for b in boxes)
    x1, z1 = max(b[3] for b in boxes), max(b[5] for b in boxes)
    require(x1-x0+2 <= 256 and z1-z0+2 <= 256, 'unbounded village coverage')
    return x0, z0, x1, z1


def area_index(areas):
    require(isinstance(areas, list) and len(areas) == 5, 'five observed areas required')
    result = {(a['kind'], a['target']): a for a in areas}
    require(len(result) == 5 and set(result) == TARGETS, 'incomplete/duplicate area targets')
    return result


def validate_csv(raw: bytes, boxes, observed: dict) -> None:
    x0, z0, x1, z1 = bounds(boxes)
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8')))
    require(reader.fieldnames == ['x', 'z', 'y128_block', 'within_piece_xz_bbox'], 'CSV header changed')
    seen = set(); counts = Counter()
    for row in reader:
        require(None not in row and all(value is not None for value in row.values()), 'incomplete CSV row')
        x, z = int(row['x']), int(row['z'])
        require(x0 <= x <= x1 and z0 <= z <= z1 and (x, z) not in seen, 'CSV coverage/duplicate error')
        seen.add((x, z))
        inside = any(b[0] <= x <= b[3] and b[2] <= z <= b[5] for b in boxes)
        require(row['within_piece_xz_bbox'] == str(int(inside)), 'CSV piece membership differs')
        name = row['y128_block']
        require(re.fullmatch(r'[a-z0-9_.-]+:[a-z0-9_./-]+', name) is not None, 'invalid block ID')
        counts['columns'] += 1
        if not inside:
            counts['outside_piece_bbox_columns'] += 1
            counts['outside_piece_bbox_water' if name == 'minecraft:water' else 'outside_piece_bbox_nonwater'] += 1
    require(len(seen) == (x1-x0+1)*(z1-z0+1), 'village CSV is truncated')
    reported = observed['counts']
    require(isinstance(reported, dict) and all(type(v) is int and v >= 0 for v in reported.values()), 'invalid CSV counters')
    require(set(reported) <= {'columns', 'outside_piece_bbox_columns', 'outside_piece_bbox_water',
                              'outside_piece_bbox_nonwater'}, 'unknown CSV counter')
    require(dict(counts) == {k: v for k, v in reported.items() if v}, 'CSV/report counters disagree')
    require(observed['piece_count'] == len(boxes) and observed['xz_bounds'] == [x0, z0, x1, z1],
            'village geometry/report differs')
    require(observed.get('visual_shape_accepted') is False, 'visual acceptance must remain separate')


def collect(artifacts: Path, source_sha: str, run_id: int) -> dict[str, bytes]:
    require(re.fullmatch('[0-9a-f]{40}', source_sha) is not None, 'full source SHA required')
    require(type(run_id) is int and run_id > 0, 'positive workflow run ID required')
    plan, plan_raw = read_json(artifacts/'tree-village-plan.json')
    report, report_raw = read_json(artifacts/'tree-village-natural.json')
    for document in (plan, report):
        require(type(document.get('schema')) is int and document['schema'] == 2, 'unsupported evidence schema')
        require(type(document.get('seed')) is int and document['seed'] == SEED, 'unexpected seed')
        require(document.get('source_sha') == source_sha, 'stale source SHA')
    require(plan.get('normal_stop') is True and type(plan.get('process_exit_code')) is int
            and plan['process_exit_code'] == 0, 'final stop not successful')
    phases = plan.get('phases', [])
    require(len(phases) == 2 and [p.get('name') for p in phases] ==
            ['locate-and-initial-chunks', 'complete-village-footprints'], 'missing lifecycle phases')
    require(all(p.get('normal_stop') is True and type(p.get('process_exit_code')) is int
                and p['process_exit_code'] == 0 for p in phases), 'phase did not stop normally')
    require(phases[0].get('saved_initial_full_verified') is True
            and phases[1].get('saved_all_full_verified') is True, 'saved FULL verification missing')
    require(report.get('natural_observation_pass') is True
            and report.get('saved_evidence_after_normal_stops') is True, 'natural observation failed')
    require(report.get('production_ready') is False and report.get('village_visual_review_required') is True,
            'field candidate cannot claim production/visual acceptance')
    require(plan.get('final_village_geometry_verified') is True
            and report.get('final_village_geometry_verified') is True, 'final geometry verification missing')
    geometry, geometry_raw = read_json(artifacts/'tree-village-geometry.json')
    initial, initial_raw = read_json(artifacts/'tree-village-initial-plan.json')
    require(geometry.get('source_sha') == source_sha and initial.get('source_sha') == source_sha,
            'geometry/planning source SHA differs')
    require(geometry.get('final_saved_geometry_covered') is True and geometry.get('visual_shape_accepted') is False,
            'final geometry diagnostic incomplete')
    require(initial.get('normal_stop') is True and initial.get('phases') == plan.get('phases'),
            'initial and final lifecycle evidence differs')
    initial_areas = area_index(initial.get('areas'))
    geometry_areas = {v['target']: v for v in geometry.get('villages', [])}
    require(len(geometry.get('villages', [])) == 2 and set(geometry_areas) == set(VILLAGES),
            'geometry target coverage differs')
    source = area_index(plan.get('areas')); observed = area_index(report.get('areas'))
    all_chunks = set(); underwater = 0
    payload = {'evidence/tree-village-plan.json': plan_raw, 'evidence/tree-village-natural.json': report_raw,
               'evidence/tree-village-geometry.json': geometry_raw,
               'evidence/tree-village-initial-plan.json': initial_raw}
    for key, area in source.items():
        found = observed[key]; chunks = coordinates(area['chunks']); all_chunks.update(chunks)
        require(type(found.get('chunks_full')) is int and found['chunks_full'] == len(chunks), 'FULL count differs')
        if key[0] == 'forest':
            x, z = area['located_xz']; cx, cz = x//16, z//16
            require(chunks == {(a, b) for a in range(cx-2, cx+3) for b in range(cz-2, cz+3)}, 'forest sample changed')
            counts = found['counts']
            require(isinstance(counts, dict) and all(type(v) is int and v >= 0 for v in counts.values()), 'invalid forest counters')
            require(counts.get('wholly_submerged_components', 0) <= counts.get('wood_leaf_components', 0), 'impossible component counts')
            underwater += counts.get('wholly_submerged_components', 0)
        else:
            boxes = area['piece_boxes']; x0, z0, x1, z1 = bounds(boxes)
            previous = initial_areas[key]; item = geometry_areas[key[1]]
            require(area.get('planning_piece_boxes') == previous.get('piece_boxes')
                    and area.get('planning_chunks') == previous.get('chunks')
                    and item.get('initial_piece_boxes') == previous.get('piece_boxes')
                    and item.get('final_piece_boxes') == boxes, 'geometry snapshots disagree')
            old_chunks = coordinates(previous['chunks'])
            require(chunks <= old_chunks and coordinates(item['verified_chunks']) == old_chunks
                    and coordinates(item['final_required_chunks']) == chunks
                    and item.get('unverified_required_chunks') == [], 'unverified final geometry coverage')
            expected = {(x, z) for x in range((x0-1)//16, (x1+1)//16+1)
                              for z in range((z0-1)//16, (z1+1)//16+1)}
            require(chunks == expected and tuple(area['start_chunk']) in chunks, 'village coverage changed')
            filename = key[1].split(':')[1] + '-y128.csv'
            require(found.get('plane_csv') == filename, 'unexpected CSV path')
            raw = (artifacts/filename).read_bytes(); validate_csv(raw, boxes, found)
            payload['evidence/'+filename] = raw
    require(type(report.get('unique_full_chunks')) is int and report['unique_full_chunks'] == len(all_chunks), 'unique FULL count differs')
    require(type(report.get('underwater_wood_leaf_components')) is int
            and report['underwater_wood_leaf_components'] == underwater and underwater > 0, 'no verified submerged component')
    log = (artifacts/'build-smoke.log').read_text(encoding='utf-8')
    require('BUILD SUCCESSFUL' in log, 'successful build marker missing')
    for smoke in SMOKES:
        require(re.search(r'\bPASS '+smoke+r' checks=[1-9][0-9]*\b', log) is not None, 'native smoke missing: '+smoke)
    payload['evidence/build-smoke.log'] = log.encode('utf-8')
    for filename, target, hash_key in [('server.jar', 'server.jar', 'jar_sha256'),
            ('NeverOverworld.zip', 'datapacks/NeverOverworld.zip', 'pack_sha256')]:
        raw = (artifacts/filename).read_bytes()
        require(all(document.get(hash_key) == digest(raw) for document in (plan, report, initial)), 'binary/evidence mismatch: '+filename)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            require(bool(archive.namelist()) and archive.testzip() is None, 'corrupt/empty archive: '+filename)
        payload[target] = raw
    info = {'schema': 1, 'source_sha': source_sha, 'workflow_run': run_id,
            'purpose': 'new-world manual field test; NOT production acceptance',
            'java_version': 25, 'seed': SEED, 'native_tree_fixtures_pass': True,
            'natural_observation_pass': True, 'unique_full_chunks': len(all_chunks),
            'underwater_wood_leaf_components': underwater, 'production_ready': False,
            'village_visual_review_required': True, 'existing_world_migration_supported': False,
            'included_datapacks': ['NeverOverworld.zip'],
            'excluded_datapacks': ['NeverNether.zip', 'NeverEnd.zip']}
    payload['BUILD-INFO.json'] = json_bytes(info)
    payload['README-RU.txt'] = ('''NeverFolia TREE-R1 + VILLAGE-NOFILL-R1 — ТЕСТОВЫЙ КОМПЛЕКТ

Только НОВАЯ отдельная папка сервера и НОВЫЙ тестовый мир. Не заменять
действующий сервер и не копировать сюда старые регионы или lock-файлы.
Деревья защищены от обрезки затоплением. Дополнительная подсыпка
деревень к Y=128 отключена; обычное размещение структур сохранено.
Ранее удалённые деревья и старые квадратные насыпи не восстанавливаются.

1. Установите Java 25 и распакуйте комплект в пустую папку.
2. ДО первого запуска создайте world/datapacks и скопируйте туда
   datapacks/NeverOverworld.zip. Не оставляйте датапак только возле JAR.
3. Создайте server.properties с параметрами:
   level-name=world
   level-seed=-2996952393010080672
   initial-enabled-packs=vanilla,file/NeverOverworld.zip
4. Запустите: java -Xms1G -Xmx4G -jar server.jar --nogui
5. Ознакомьтесь с EULA; подтвердите её только при согласии и повторите запуск.
Не удаляйте файлы совместимости для обхода отказа запуска.

Сохранённые наблюдения находятся в evidence/. Это одна выборка на одном seed,
а не доказательство всех вариантов генерации. Компонент древесины/листвы
не равен отдельному дереву; горизонтальное бревно не доказывает поваленное
дерево. Точные сценарии отдельно покрыты нативными тестами.

ПРОВЕРИТЬ В ИГРЕ: целые подводные стволы/кроны, поваленные деревья,
деревья с 2–3 погружёнными блоками, естественный рельеф между домами,
отсутствие квадратной подсыпки и висящих/подмытых береговых зданий.
Координаты деревень и области проверки указаны в tree-village-plan.json.
Наличие воды между домами само по себе не является ошибкой.

ВИЗУАЛЬНАЯ ПРИЁМКА ДЕРЕВЕНЬ НЕ ЗАВЕРШЕНА. production_ready=false.
Включён только датапак NeverOverworld. NeverNether и NeverEnd отсутствуют.
Это не полный релиз экосистемы и не миграция существующего мира.

''' + f'Исходники: {source_sha}\nGitHub Actions run: {run_id}\n').encode('utf-8')
    payload['SHA256SUMS.txt'] = ''.join(f'{digest(raw)}  {name}\n' for name, raw in sorted(payload.items())).encode('ascii')
    return payload


def build(artifacts: Path, output: Path, source_sha: str, run_id: int) -> dict:
    require(not output.exists() and not output.is_symlink(), 'refusing to overwrite output')
    payload = collect(artifacts, source_sha, run_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Same-directory temporary ZIP + exclusive link prevents replacement races.
    fd, temporary = tempfile.mkstemp(prefix='.tree-village-', suffix='.zip', dir=output.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, raw in sorted(payload.items()):
                archive.writestr(name, raw)
        with zipfile.ZipFile(temporary) as archive:
            require(archive.testzip() is None, 'output integrity check failed')
        os.link(temporary, output)
    finally:
        Path(temporary).unlink()
    return {'output': str(output), 'sha256': digest(output.read_bytes()), 'source_sha': source_sha,
            'workflow_run': run_id, 'production_ready': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--run-id', type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.artifacts, args.output, args.source_sha, args.run_id), indent=2))


if __name__ == '__main__':
    main()
