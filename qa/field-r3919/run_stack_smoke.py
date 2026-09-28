#!/usr/bin/env python3
"""Fresh loopback-only startup witness for the same ordered pack manifest.
No users, player clients, production folders or saved user worlds are accessed.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import never_resource_stack as s

OUT = ROOT / 'artifacts'
WORK = ROOT / '.work/r3919/stack-smoke'
BAD = ('Failed to load datapacks', 'Failed to load registries', 'Failed to load function',
       'Failed to parse', 'Unknown registry key', 'Exception in server tick loop',
       'Chunk system error', 'The server has not responded for', 'NoSuchMethodError',
       'NoClassDefFoundError', 'Empty or non-existent pool:', 'Exception loading structure')


def main():
    report = {'pass': False, 'runtime_order_verified': False, 'production_accepted': False,
              'all_reported_bugs_fixed': False, 'worldgen_acceptance': False,
              'scope': 'One isolated fresh-world startup, clean save and persisted enabled-pack order. The automatic Paper datapack is witnessed separately from the static two-file stack audit.'}
    proc = None
    reader = None
    lines = []
    started = time.monotonic()
    try:
        manifest = s.decode_json((OUT / 'stack-after-manifest.json').read_bytes())
        expected = ['vanilla'] + [p['id'] for p in manifest['packs']]
        automatic = ['paper']
        expected_runtime = expected + automatic
        report['expected_order'] = expected
        report['runtime_automatic_packs'] = automatic
        report['expected_runtime_order'] = expected_runtime
        s.need(expected == ['vanilla', 'file/NeverOverworld.zip', 'file/NeverNether.zip'], 'Unexpected QA input order')
        kernel = Path(manifest['server']['path'])
        s.pinned_bytes(manifest['server'], 'server')
        WORK.mkdir(parents=True, exist_ok=False)
        packs = WORK / 'world/datapacks'
        packs.mkdir(parents=True)
        for record in manifest['packs']:
            name = record['id'].removeprefix('file/')
            s.need(Path(name).name == name, 'Not a root pack filename')
            raw = s.pinned_bytes(record, 'pack')
            (packs / name).write_bytes(raw)
        (WORK / 'eula.txt').write_text('eula=true\n')
        (WORK / 'server.properties').write_text(
            'level-name=world\nlevel-seed=-4651369264513492755\n'
            'initial-enabled-packs=' + ','.join(expected) + '\n'
            'server-ip=127.0.0.1\nserver-port=25619\nonline-mode=true\n'
            'view-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\n'
            'enable-rcon=false\nenable-query=false\nenable-status=false\n')
        events = queue.Queue()
        argv = ['java', '-XX:ActiveProcessorCount=4', '-Xms512M', '-Xmx4G',
                '-Dneverfolia.r399OceanClosure=true', '-Dneverfolia.r3913IceFragments=true',
                '-jar', str(kernel), '--nogui']
        report['jvm_args'] = argv
        proc = subprocess.Popen(argv, cwd=WORK, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
        def pump():
            with (OUT / 'stack-smoke-server.log').open('x', encoding='utf-8') as log:
                for line in proc.stdout:
                    lines.append(line)
                    log.write(line)
                    log.flush()
                    events.put(line)
            events.put(None)
        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        deadline = time.monotonic() + 360
        done = False
        while time.monotonic() < deadline:
            try:
                line = events.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:
                    break
                continue
            if line is None:
                break
            if 'Done (' in line:
                done = True
                break
        report['startup_done'] = done
        s.need(done, 'Server did not reach Done within the startup budget')
        proc.stdin.write('datapack list enabled\nstop\n')
        proc.stdin.flush()
        report['exit_code'] = proc.wait(timeout=120)
        reader.join(timeout=15)
        s.need(report['exit_code'] == 0 and not reader.is_alive(), 'Server did not shut down cleanly')
        level = WORK / 'world/level.dat'
        s.need(level.is_file(), 'Saved level.dat missing')
        nbt = s.module(ROOT / 'scripts/build-never-overworld-external-structures-r19.py', 'stack_smoke_nbt')
        root = nbt._nbt_parse(level.read_bytes())[2]
        data = root['Data']
        s.need(data[0] == 10 and data[1]['DataPacks'][0] == 10, 'Missing typed DataPacks compound')
        enabled = data[1]['DataPacks'][1]['Enabled']
        s.need(enabled[0] == 9 and enabled[1][0] == 8, 'Invalid enabled-pack list')
        observed = enabled[1][1]
        report['observed_saved_order'] = observed
        report['level_dat_sha256'] = s.digest(level.read_bytes())
        shutil.copyfile(level, OUT / 'stack-smoke-level.dat')
        report['targeted_errors'] = [line.strip() for line in lines if any(b in line for b in BAD)]
        report['datapack_console_lines'] = [line.strip() for line in lines if 'data pack' in line.lower() or 'datapack' in line.lower()]
        s.need(observed == expected_runtime, 'Runtime enabled stack differs from audited packs plus the reviewed automatic Paper pack')
        s.need(any('Found new data pack paper, loading it automatically' in line for line in report['datapack_console_lines']),
               'Automatic Paper datapack was not explicitly witnessed in the server log')
        report['runtime_order_verified'] = True
        report['static_audit_excludes_runtime_automatic_packs'] = True
        for record in manifest['packs']:
            s.need(s.digest((packs / record['id'].removeprefix('file/')).read_bytes()) == record['sha256'], 'Runtime datapack changed')
        for record in [manifest['server'], *manifest['packs']]:
            with Path(record['path']).open('rb') as stream:
                s.need(hashlib.file_digest(stream, 'sha256').hexdigest() == record['sha256'], 'Original input changed')
        report['inputs_unchanged'] = True
        report['input_hashes'] = {'server': manifest['server']['sha256'], 'packs': {p['id']: p['sha256'] for p in manifest['packs']}}
        s.need(not report['targeted_errors'], 'Targeted errors occurred during the fresh startup')
        report['pass'] = True
    except Exception as error:
        report['error'] = repr(error)
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.stdin.write('stop\n')
                proc.stdin.flush()
                proc.wait(timeout=30)
            except Exception:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
        if reader is not None:
            reader.join(timeout=15)
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        with (OUT / 'stack-smoke.json').open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        print('STACK_SMOKE', json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
