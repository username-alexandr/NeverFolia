#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import re
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")
MOONRISE_REL = Path(
    "folia-server/src/minecraft/java/ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask.java"
)
LEGACY_HELPER_SCRIPT = Path(__file__).with_name("apply-never-overworld-flood-hook.py")
MARKER = "// NEVERFOLIA: Moonrise LIGHT flood hook"
CALL = "net.minecraft.world.level.chunk.NeverOverworldFlood.apply(task.world, task.fromChunk);"
PACKAGE = "package ca.spottedleaf.moonrise.patches.chunk_system.scheduling.task;"
CLASS = "public final class ChunkLightTask extends ChunkProgressionTask"
ANCHOR_RE = re.compile(
    r"(?P<indent>[ \t]*)final\s+Boolean\[\]\s+emptySections\s*=\s*"
    r"StarLightEngine\.getEmptySectionsForChunk\(task\.fromChunk\);"
)


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld Moonrise flood] {message}")


def load_helper_source() -> str:
    if not LEGACY_HELPER_SCRIPT.is_file():
        fail(f"legacy flood helper source provider not found: {LEGACY_HELPER_SCRIPT}")
    spec = importlib.util.spec_from_file_location("never_overworld_legacy_flood", LEGACY_HELPER_SCRIPT)
    if spec is None or spec.loader is None:
        fail("could not load legacy flood helper source provider")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    helper_source = getattr(module, "helper_source", None)
    if helper_source is None:
        fail("legacy flood script does not expose helper_source()")
    return helper_source()


def patch_chunk_light_task(source: str) -> str:
    if MARKER in source or CALL in source:
        fail("ChunkLightTask is already patched")
    if PACKAGE not in source:
        fail("ChunkLightTask package does not match Moonrise scheduling task")
    if CLASS not in source:
        fail("ChunkLightTask class declaration not found")
    if "private static final class LightTask implements BooleanSupplier" not in source:
        fail("Moonrise LightTask runtime class not found")

    matches = list(ANCHOR_RE.finditer(source))
    if len(matches) != 1:
        fail(f"expected exactly one Starlight empty-section anchor, got {len(matches)}")

    match = matches[0]
    indent = match.group("indent")
    insertion = (
        f"{indent}{MARKER}\n"
        f"{indent}// Moonrise owns the actual Folia LIGHT runtime path. Run the chunk-owned\n"
        f"{indent}// NeverOverworld flood after FEATURES/parent status and before Starlight reads\n"
        f"{indent}// section emptiness or mutates lighting state.\n"
        f"{indent}{CALL}\n\n"
    )
    return source[: match.start()] + insertion + source[match.start() :]


def is_runtime_source(path: Path) -> bool:
    return ".gradle" not in path.parts and "taskCache" not in path.parts


def validate_target(path: Path) -> Path:
    if not path.is_file():
        fail(f"Moonrise ChunkLightTask source not found: {path}")
    source = path.read_text(encoding="utf-8")
    if PACKAGE not in source or CLASS not in source:
        fail(f"Moonrise ChunkLightTask source has unexpected package/class: {path}")
    return path


def find_chunk_light_task(folia: Path) -> Path:
    # Paperweight materializes the compilable Moonrise sources here. Prefer the
    # exact source-tree path so cached setup inputs under .gradle/taskCache can
    # never be mistaken for the Java file that Gradle actually compiles.
    exact = folia / MOONRISE_REL
    if exact.is_file():
        return validate_target(exact)

    server = folia / "folia-server"
    if not server.is_dir():
        fail(f"Folia server source directory not found: {server}")

    candidates: list[Path] = []
    for path in server.rglob("ChunkLightTask.java"):
        if not is_runtime_source(path):
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if PACKAGE in source and CLASS in source:
            candidates.append(path)

    if len(candidates) != 1:
        rendered = ", ".join(str(path) for path in candidates) or "none"
        fail(f"expected exactly one compilable Moonrise ChunkLightTask.java, got {len(candidates)}: {rendered}")
    return candidates[0]


def self_test() -> None:
    fixture = '''package ca.spottedleaf.moonrise.patches.chunk_system.scheduling.task;

import java.util.function.BooleanSupplier;

public final class ChunkLightTask extends ChunkProgressionTask {
    private static final class LightTask implements BooleanSupplier {
        @Override
        public boolean getAsBoolean() {
            final ChunkLightTask task = this.task;
            if (!task.priorityHolder.markExecuting()) {
                return false;
            }
            try {
                final Boolean[] emptySections = StarLightEngine.getEmptySectionsForChunk(task.fromChunk);
                this.lightEngine.lightChunk(task.fromChunk, emptySections);
            } catch (final Throwable thr) {
                return true;
            }
            return true;
        }
    }
}
'''
    patched = patch_chunk_light_task(fixture)
    if patched.count(MARKER) != 1:
        fail("SELF-TEST: Moonrise marker count is not exactly one")
    if patched.count(CALL) != 1:
        fail("SELF-TEST: flood call count is not exactly one")
    if patched.index(CALL) > patched.index("StarLightEngine.getEmptySectionsForChunk"):
        fail("SELF-TEST: flood call must execute before Starlight reads empty sections")
    if patched.index(CALL) < patched.index("markExecuting()"):
        fail("SELF-TEST: flood call must execute only after the task owns execution")

    # Regression guard for Heavy #108: recursive source discovery also found a
    # paperweight task-cache copy of ChunkLightTask.java. Only materialized source
    # files are eligible for patching.
    if is_runtime_source(Path("folia-server/.gradle/caches/paperweight/taskCache/runFoliaSetup/ChunkLightTask.java")):
        fail("SELF-TEST: .gradle task-cache source must never be eligible")
    if not is_runtime_source(Path("folia-server/src/minecraft/java/ca/spottedleaf/moonrise/ChunkLightTask.java")):
        fail("SELF-TEST: materialized source must be eligible")

    helper = load_helper_source()
    for required in (
        "public final class NeverOverworldFlood",
        "public static void apply(final WorldGenLevel level, final ChunkAccess chunk)",
        "EXPECTED_MIN_Y = -512",
        "EXPECTED_HEIGHT = 1024",
        "FLOOD_LEVEL = 128",
    ):
        if required not in helper:
            fail(f"SELF-TEST: flood helper source missing {required!r}")

    print("[NeverFolia][NeverOverworld Moonrise flood] RUNTIME LIGHT HOOK SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply NeverOverworld flood to Moonrise's actual LIGHT runtime task")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required unless --self-test is used")

    folia = args.folia.resolve()
    task = find_chunk_light_task(folia)
    helper = folia / HELPER_REL

    task.write_text(patch_chunk_light_task(task.read_text(encoding="utf-8")), encoding="utf-8")
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text(load_helper_source(), encoding="utf-8")

    print("[NeverFolia][NeverOverworld Moonrise flood] runtime LIGHT hook applied")
    print(f"  task: {task}")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
