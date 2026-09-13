#!/usr/bin/env python3
"""Fail closed on content-loading errors, even when the server prints Done()."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import zipfile


def analyze(text: str, exit_code: int, pack_files: dict[str, bytes] | None = None) -> dict:
    ready = bool(re.search(r'Done \([^\r\n]+\)! For help', text))
    saved = 'All dimensions are saved' in text
    functions = sorted(set(re.findall(r'Failed to load function ([a-z0-9_.:/-]+)', text)))
    data_errors = sorted(set(re.findall(r"Couldn't parse data file '([^']+)'", text)))
    loot = sorted(set(re.findall(r'Missing element (\S+) of type (\S+)', text)))
    registry_failed = bool(re.search(r'Failed to load datapacks|Failed to load registries|Registry Loading', text))
    pool_warnings = sorted(set(re.findall(r'Empty or non-existent pool: ([a-z0-9_.:/-]+)', text)))
    known_empty, unresolved = [], []
    for ident in pool_warnings:
        ns, name = (ident.split(':', 1) if ':' in ident else ('minecraft', ident))
        path = f'data/{ns}/worldgen/template_pool/{name}.json'
        raw = (pack_files or {}).get(path)
        try:
            value = json.loads(raw) if raw is not None else None
            is_empty = isinstance(value, dict) and value.get('elements') == []
        except (ValueError, TypeError):
            is_empty = False
        (known_empty if is_empty else unresolved).append(ident)
    # Offline auth-key retrieval is recorded separately, not attributed to datapack
    # code. Every other ERROR line remains a content/runtime blocker.
    errors = [line for line in text.splitlines() if re.search(r'\bERROR\]', line)]
    offline_auth = [line for line in errors if 'Failed to request yggdrasil public key' in line]
    other_errors = [line for line in errors if line not in offline_auth]
    clean = not (functions or data_errors or loot or registry_failed or unresolved or other_errors)
    passed = ready and saved and exit_code == 0 and clean
    return {
        'schema': 1, 'gate': 'nevernether-startup-content-r5',
        'server_ready': ready, 'normal_save_observed': saved, 'process_exit_code': exit_code,
        'registry_loading_failed': registry_failed,
        'failed_functions': functions, 'failed_data_files': data_errors,
        'missing_loot_references': [list(x) for x in loot],
        'intentional_empty_pool_warnings': known_empty,
        'unresolved_pool_warnings': unresolved,
        'content_error_lines': other_errors, 'offline_auth_error_lines': offline_auth,
        'content_clean': clean, 'smoke_passed': passed, 'release_ready': False,
        'scope': 'Startup/loading plus observed stop only; no structure-placement, loot-balance or determinism acceptance.',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--exit-code', type=int, required=True)
    parser.add_argument('--pack', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() == args.log.resolve() or args.output.suffix.lower() != '.json':
        parser.error('Use a separate JSON output, never overwrite the input log')
    files = {}
    if args.pack:
        with zipfile.ZipFile(args.pack) as archive:
            files = {name: archive.read(name) for name in archive.namelist()
                     if '/worldgen/template_pool/' in name and name.endswith('.json')}
    result = analyze(args.log.read_text(encoding='utf-8-sig', errors='replace'), args.exit_code, files)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"Startup gate: {'PASS' if result['smoke_passed'] else 'BLOCKED'}; ready={result['server_ready']}, content_clean={result['content_clean']}")
    return 0 if result['smoke_passed'] else 2

if __name__ == '__main__':
    raise SystemExit(main())
