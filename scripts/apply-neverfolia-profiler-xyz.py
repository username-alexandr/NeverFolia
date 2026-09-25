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


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        fail(f"{label}: expected exactly one marker, got {count}")
    return source.replace(old, new, 1)


def patch_source(source: str) -> str:
    if "NeverFolia: accept XYZ profiler syntax" in source:
        fail("CommandProfiler already patched")

    source = replace_once(
        source,
        "if (args.length < 4 || args.length > 5) {",
        "// NeverFolia: accept XYZ profiler syntax used by in-game diagnostics.\n"
        "        // Folia regions are 2D, therefore Y is validated but intentionally ignored.\n"
        "        if (args.length < 4 || args.length > 6) {",
        "argument-count guard",
    )
    source = replace_once(source, OLD_USAGE, NEW_USAGE, "usage string")

    world_marker = "final World world = Bukkit.getWorld(args[0]);"
    prefix = '''final boolean neverFoliaXYZ = args.length == 6;
        final int neverFoliaBlockZArg = neverFoliaXYZ ? 3 : 2;
        final int neverFoliaTimeArg = neverFoliaXYZ ? 4 : 3;
        final int neverFoliaRadiusArg = neverFoliaXYZ ? 5 : 4;
        if (neverFoliaXYZ && !args[2].equals("~")) {
            try {
                Double.parseDouble(args[2]);
            } catch (final NumberFormatException ex) {
                sender.sendMessage(Component.text("Invalid input for block y: " + args[2], NamedTextColor.RED));
                return true;
            }
        }

        '''
    source = replace_once(source, world_marker, prefix + world_marker, "world lookup")

    # Folia 26.2 parses X/Z as doubles and supports '~' for entity senders.
    z_old = 'blockZ = (args[2].equals("~") && sender instanceof Entity entity) ? entity.getLocation().getZ() : Double.parseDouble(args[2]);'
    z_new = 'blockZ = (args[neverFoliaBlockZArg].equals("~") && sender instanceof Entity entity) ? entity.getLocation().getZ() : Double.parseDouble(args[neverFoliaBlockZArg]);'
    source = replace_once(source, z_old, z_new, "block-z parser")
    source = replace_once(
        source,
        'sender.sendMessage(Component.text("Invalid input for block z: " + args[2], NamedTextColor.RED));',
        'sender.sendMessage(Component.text("Invalid input for block z: " + args[neverFoliaBlockZArg], NamedTextColor.RED));',
        "block-z error",
    )

    source = replace_once(
        source,
        "time = Double.parseDouble(args[3]);",
        "time = Double.parseDouble(args[neverFoliaTimeArg]);",
        "time parser",
    )
    source = replace_once(
        source,
        'sender.sendMessage(Component.text("Invalid input for time: " + args[3], NamedTextColor.RED));',
        'sender.sendMessage(Component.text("Invalid input for time: " + args[neverFoliaTimeArg], NamedTextColor.RED));',
        "time error",
    )

    source = replace_once(
        source,
        "if (args.length > 4) {",
        "if (neverFoliaXYZ || args.length > 4) {",
        "radius guard",
    )
    source = replace_once(
        source,
        "radius = Double.parseDouble(args[4]);",
        "radius = Double.parseDouble(args[neverFoliaRadiusArg]);",
        "radius parser",
    )
    source = replace_once(
        source,
        'sender.sendMessage(Component.text("Invalid input for radius: " + args[4], NamedTextColor.RED));',
        'sender.sendMessage(Component.text("Invalid input for radius: " + args[neverFoliaRadiusArg], NamedTextColor.RED));',
        "radius error",
    )

    required = (
        "neverFoliaXYZ = args.length == 6",
        "neverFoliaBlockZArg = neverFoliaXYZ ? 3 : 2",
        "neverFoliaTimeArg = neverFoliaXYZ ? 4 : 3",
        "neverFoliaRadiusArg = neverFoliaXYZ ? 5 : 4",
        "Double.parseDouble(args[2]);",
        "args[neverFoliaBlockZArg]",
        "args[neverFoliaTimeArg]",
        "args[neverFoliaRadiusArg]",
        "Invalid input for block y",
    )
    for marker in required:
        if marker not in source:
            fail(f"patched source missing {marker!r}")
    return source


def self_test() -> None:
    fixture = '''public final class CommandProfiler extends Command {
    public boolean execute(final CommandSender sender, final String commandLabel, final String[] args) {
        if (args.length < 4 || args.length > 5) {
            sender.sendMessage(Component.text("Usage: /profiler <world> <block x> <block z> <time in s> [radius, default 100 blocks]", NamedTextColor.RED));
            return true;
        }
        final World world = Bukkit.getWorld(args[0]);
        final double blockX;
        final double blockZ;
        final double time;
        try {
            blockX = (args[1].equals("~") && sender instanceof Entity entity) ? entity.getLocation().getX() : Double.parseDouble(args[1]);
        } catch (final NumberFormatException ex) {
            sender.sendMessage(Component.text("Invalid input for block x: " + args[1], NamedTextColor.RED));
            return true;
        }
        try {
            blockZ = (args[2].equals("~") && sender instanceof Entity entity) ? entity.getLocation().getZ() : Double.parseDouble(args[2]);
        } catch (final NumberFormatException ex) {
            sender.sendMessage(Component.text("Invalid input for block z: " + args[2], NamedTextColor.RED));
            return true;
        }
        try {
            time = Double.parseDouble(args[3]);
        } catch (final NumberFormatException ex) {
            sender.sendMessage(Component.text("Invalid input for time: " + args[3], NamedTextColor.RED));
            return true;
        }
        final double radius;
        if (args.length > 4) {
            try {
                radius = Double.parseDouble(args[4]);
            } catch (final NumberFormatException ex) {
                sender.sendMessage(Component.text("Invalid input for radius: " + args[4], NamedTextColor.RED));
                return true;
            }
        } else {
            radius = 100.0;
        }
        return true;
    }
}
'''
    patched = patch_source(fixture)
    checks = (
        "args.length > 6",
        "Invalid input for block y",
        'blockZ = (args[neverFoliaBlockZArg].equals("~")',
        "time = Double.parseDouble(args[neverFoliaTimeArg]);",
        "radius = Double.parseDouble(args[neverFoliaRadiusArg]);",
        "OR /profiler",
    )
    for marker in checks:
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
    print("  accepted legacy: /profiler <world> <x> <z> <time> [radius]")
    print("  accepted XYZ:    /profiler <world> <x> <y> <z> <time> <radius>")
    print(f"  source: {path}")


if __name__ == "__main__":
    main()
