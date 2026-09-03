#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

CLASS_MARKER = "public class CommandProfiler"
ALT_CLASS_MARKER = "public final class CommandProfiler"
OLD_USAGE = "Usage: /profiler <world> <block x> <block z> <time in s> [radius, default 100 blocks]"
NEW_USAGE = "Usage: /profiler <world> <block x> <block z> <time in s> [radius] OR /profiler <world> <block x> <block y> <block z> <time in s> <radius>"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][profiler xyz] {message}")


def find_source(folia: Path) -> Path:
    candidates: list[Path] = []
    for path in (folia / "folia-server").rglob("CommandProfiler.java"):
        if ".gradle" in path.parts or "taskCache" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if CLASS_MARKER in text or ALT_CLASS_MARKER in text:
            candidates.append(path)
    if len(candidates) != 1:
        fail(f"expected one runtime CommandProfiler.java, got {len(candidates)}: {candidates}")
    return candidates[0]


def patch_source(source: str) -> str:
    if "NeverFolia: accept XYZ profiler syntax" in source:
        fail("CommandProfiler already patched")
    old_check = "if (args.length < 4 || args.length > 5) {"
    if old_check not in source:
        fail("argument-count guard not found")
    if OLD_USAGE not in source:
        fail("upstream usage marker not found")

    source = source.replace(
        old_check,
        "// NeverFolia: accept XYZ profiler syntax used by in-game diagnostics.\n"
        "        // Folia regions are 2D, therefore Y is validated but intentionally ignored.\n"
        "        if (args.length < 4 || args.length > 6) {",
        1,
    )
    source = source.replace(OLD_USAGE, NEW_USAGE, 1)

    # The six-argument form is unambiguous: world x y z time radius.
    old_x = "final int blockX;"
    if old_x not in source:
        fail("blockX declaration marker not found")
    source = source.replace(old_x, "final boolean neverFoliaXYZ = args.length == 6;\n        final int blockX;", 1)

    source = source.replace("Integer.parseInt(args[2])", "Integer.parseInt(args[neverFoliaXYZ ? 3 : 2])", 1)
    source = source.replace("Double.parseDouble(args[3])", "Double.parseDouble(args[neverFoliaXYZ ? 4 : 3])", 1)

    # Radius in the upstream command is optional arg[4]. In XYZ mode it is arg[5].
    old_radius_guard = "if (args.length > 4) {"
    if old_radius_guard not in source:
        fail("radius guard marker not found")
    source = source.replace(old_radius_guard, "if (neverFoliaXYZ || args.length > 4) {", 1)
    source = source.replace("Double.parseDouble(args[4])", "Double.parseDouble(args[neverFoliaXYZ ? 5 : 4])", 1)

    # Validate the user supplied Y so malformed XYZ input does not silently pass.
    world_marker = "final World world = Bukkit.getWorld(args[0]);"
    if world_marker not in source:
        fail("world lookup marker not found")
    validation = '''if (neverFoliaXYZ) {
            try {
                Integer.parseInt(args[2]);
            } catch (final NumberFormatException ex) {
                sender.sendMessage(Component.text("Invalid input for block y: " + args[2], NamedTextColor.RED));
                return true;
            }
        }

        '''
    source = source.replace(world_marker, validation + world_marker, 1)

    required = (
        "neverFoliaXYZ = args.length == 6",
        "args[neverFoliaXYZ ? 3 : 2]",
        "args[neverFoliaXYZ ? 4 : 3]",
        "args[neverFoliaXYZ ? 5 : 4]",
        "Invalid input for block y",
    )
    for marker in required:
        if marker not in source:
            fail(f"patched source missing {marker!r}")
    return source


def self_test() -> None:
    fixture = '''public final class CommandProfiler {
    public boolean execute(final CommandSender sender, final String commandLabel, final String[] args) {
        if (args.length < 4 || args.length > 5) {
            sender.sendMessage(Component.text("Usage: /profiler <world> <block x> <block z> <time in s> [radius, default 100 blocks]", NamedTextColor.RED));
            return true;
        }
        final World world = Bukkit.getWorld(args[0]);
        final int blockX;
        final int blockZ;
        try { blockX = Integer.parseInt(args[1]); blockZ = Integer.parseInt(args[2]); } catch (NumberFormatException ex) { return true; }
        final double time;
        try { time = Double.parseDouble(args[3]); } catch (NumberFormatException ex) { return true; }
        final double radius;
        if (args.length > 4) {
            try { radius = Double.parseDouble(args[4]); } catch (final NumberFormatException ex) { return true; }
        } else { radius = 100.0; }
        return true;
    }
}
'''
    patched = patch_source(fixture)
    for marker in ("args.length > 6", "neverFoliaXYZ", "Invalid input for block y", "OR /profiler"):
        if marker not in patched:
            fail(f"SELF-TEST missing {marker}")
    print("[NeverFolia][profiler xyz] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree is required unless --self-test is used")
    self_test()
    path = find_source(args.folia.resolve())
    path.write_text(patch_source(path.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][profiler xyz] XYZ-compatible profiler syntax applied")
    print(f"  source: {path}")


if __name__ == "__main__":
    main()
