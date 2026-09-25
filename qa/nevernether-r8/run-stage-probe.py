#!/usr/bin/env python3
"""New loopback-only frozen-simulation diagnostic world, never an existing world.

The explicit EULA acknowledgement is required. Full runtime byte hashes, inputs,
normal stop and unchanged runtime are recorded. This is not release acceptance.
"""
from __future__ import annotations
import argparse
import importlib.util
import sys
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


_SPEC = importlib.util.spec_from_file_location('nn_probe_supervisor', Path(__file__).with_name('probe_supervisor.py'))
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError('Probe supervisor is missing')
SUPERVISOR = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(SUPERVISOR)


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_plan(path: Path, seed: int, reverse: bool) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or type(value.get('seed')) is not int or value['seed'] != seed:
        raise ValueError('Plan seed mismatch')
    chunks = value.get('chunks')
    if not isinstance(chunks, list) or not 1 <= len(chunks) <= 512:
        raise ValueError('Expected 1..512 selected chunks')
    seen = set()
    for pair in chunks:
        if not isinstance(pair, list) or len(pair) != 2 or any(type(n) is not int for n in pair):
            raise ValueError('Chunk coordinates must be integer pairs')
        if not 64 <= max(abs(n) for n in pair) <= 100000 or tuple(pair) in seen:
            raise ValueError('Out-of-bounds, near-spawn or duplicate chunk')
        seen.add(tuple(pair))
    if reverse:
        value['chunks'] = list(reversed(chunks))
    return value


def runtime_inventory(runtime: Path) -> tuple[list[str], dict]:
    runtime = runtime.resolve()
    entries, rows = [], []
    for index, line in enumerate((runtime / 'classpath.txt').read_text().splitlines()):
        if not line or Path(line).is_absolute() or '..' in Path(line).parts:
            raise ValueError('Invalid relative runtime classpath')
        item = (runtime / line).resolve()
        if not item.is_relative_to(runtime) or not item.exists():
            raise ValueError(f'Missing/outside runtime entry: {line}')
        entries.append(str(item))
        files = [item] if item.is_file() else sorted(p for p in item.rglob('*') if p.is_file())
        if not files:
            raise ValueError('Empty runtime entry')
        for file in files:
            if not file.resolve().is_relative_to(runtime):
                raise ValueError('Runtime resource symlink outside root')
            name = file.name if item.is_file() else file.relative_to(item).as_posix()
            rows.append({'entry': index, 'file': name, 'sha256': sha(file)})
    if not entries:
        raise ValueError('Empty runtime classpath')
    encoded = json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()
    return entries, {'schema': 1, 'files': rows, 'payload_sha256': hashlib.sha256(encoded).hexdigest(),
                     'manifest_sha256': sha(runtime / 'classpath.txt')}


def finish(evidence: dict, directory: Path, runtime: Path, inventory: dict, pack: Path, plugin: Path) -> int:
    """Persist a failing result even if post-run input verification itself fails."""
    print('[NN-PROBE] rechecking runtime and input identity', file=sys.stderr, flush=True)
    errors = []
    try:
        _, after = runtime_inventory(runtime)
        evidence['runtime_unchanged'] = after == inventory
    except (OSError, ValueError, TypeError) as error:
        evidence['runtime_unchanged'] = False
        errors.append('runtime: ' + str(error))
    try:
        evidence['inputs_unchanged'] = sha(pack) == evidence['pack_sha256'] and sha(plugin) == evidence['qa_plugin_sha256']
    except OSError as error:
        evidence['inputs_unchanged'] = False
        errors.append('inputs: ' + str(error))
    if errors:
        evidence['verification_errors'] = errors
    SUPERVISOR.write_json(directory / 'run-evidence.json', evidence)
    print(json.dumps(evidence, indent=2))
    return 0 if (evidence['stage'] == 'completed' and evidence['process_exit_code'] == 0
                 and not evidence['forced_stop'] and evidence['runtime_unchanged']
                 and evidence['inputs_unchanged']) else 2


def main(plan_validator=checked_plan) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java', type=Path, required=True)
    parser.add_argument('--runtime-dir', type=Path, required=True)
    parser.add_argument('--pack', type=Path, required=True)
    parser.add_argument('--qa-plugin', type=Path, required=True)
    parser.add_argument('--new-directory', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=7270913)
    parser.add_argument('--port', type=int, default=25589)
    parser.add_argument('--reverse', action='store_true')
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--accept-eula', action='store_true')
    parser.add_argument('--check-only', action='store_true', help='Validate inputs without creating a world or starting Java')
    parser.add_argument('--heartbeat-seconds', type=int, default=15)
    parser.add_argument('--stall-timeout', type=int, default=180)
    args = parser.parse_args()
    if not args.accept_eula:
        parser.error('Review the Minecraft EULA and explicitly pass --accept-eula')
    if not 1 <= args.port <= 65535 or not 60 <= args.timeout <= 3600:
        parser.error('Invalid port or timeout outside 60..3600 seconds')
    if not 1 <= args.heartbeat_seconds <= 300 or not 10 <= args.stall_timeout <= 3600:
        parser.error('Invalid heartbeat or no-progress timeout')
    try:
        env = SUPERVISOR.checked_environment()
        print('[NN-PROBE] checking inputs and runtime inventory', file=sys.stderr, flush=True)
        for path in (args.java, args.pack, args.qa_plugin):
            if not path.is_file():
                raise ValueError(f'Missing required input: {path}')
        plan = plan_validator(args.plan, args.seed, args.reverse)
        runtime = args.runtime_dir.resolve()
        entries, inventory = runtime_inventory(runtime)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    directory = args.new_directory.resolve()
    if directory.exists():
        parser.error('New probe directory already exists; no overwrite or implicit resume')
    if args.check_only:
        print(json.dumps({'preflight': 'PASS', 'runtime_payload_sha256': inventory['payload_sha256'],
                          'chunks': len(plan['chunks']), 'world_created': False, 'process_started': False}))
        return 0
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'world/datapacks').mkdir(parents=True)
    (directory / 'plugins').mkdir()
    (directory / '.nevernether-r8-isolated').write_text('NEW disposable R8 stage test\n')
    (directory / 'stage-plan.json').write_text(json.dumps(plan))
    (directory / 'runtime-inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
    shutil.copy2(args.pack, directory / 'world/datapacks/NeverNether.zip')
    shutil.copy2(args.qa_plugin, directory / 'plugins/survey-qa.jar')
    (directory / 'eula.txt').write_text('eula=true\n')
    (directory / 'server.properties').write_text(f'''level-name=world
level-seed={args.seed}
level-type=minecraft:normal
initial-enabled-packs=vanilla,file/NeverNether.zip
online-mode=false
enforce-secure-profile=false
server-ip=127.0.0.1
server-port={args.port}
view-distance=2
simulation-distance=2
spawn-protection=0
max-tick-time=-1
enable-status=false
pause-when-empty-seconds=-1
''')
    evidence = {'schema': 2, 'seed': args.seed, 'pack_sha256': sha(args.pack),
                'qa_plugin_sha256': sha(args.qa_plugin), 'java_executable_sha256': sha(args.java),
                'runtime_payload_sha256': inventory['payload_sha256'],
                'classpath_manifest_sha256': inventory['manifest_sha256'],
                'order': 'reverse' if args.reverse else 'forward', 'release_ready': False}
    command = [str(args.java.resolve()), *SUPERVISOR.JVM_FLAGS,
               '-cp', os.pathsep.join(entries), 'org.bukkit.craftbukkit.Main', '--nogui']
    evidence['jvm_flags'] = list(SUPERVISOR.JVM_FLAGS)
    result = SUPERVISOR.execute(command, directory, args.timeout, env=env,
                                heartbeat=args.heartbeat_seconds, stall_timeout=args.stall_timeout)
    evidence.update(result)
    return finish(evidence, directory, runtime, inventory, args.pack, args.qa_plugin)


if __name__ == '__main__':
    raise SystemExit(main())
