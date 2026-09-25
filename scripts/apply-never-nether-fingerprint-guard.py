#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SERVER_REL = Path("folia-server/src/minecraft/java/net/minecraft/server/MinecraftServer.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/server/NeverNetherFingerprintGuard.java")


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverNether fingerprint guard] {message}")


def helper_source() -> str:
    return r'''package net.minecraft.server;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Properties;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/**
 * NeverFolia-owned worldgen lock for NeverNether.
 *
 * <p>The active datapack is re-hashed from its actual file contents on every server
 * start. A world lock is created on the first fingerprinted NeverNether startup.
 * A different valid pack, a modified pack with a stale embedded fingerprint, or a
 * missing pack while a lock exists aborts startup before worlds are created.</p>
 */
final class NeverNetherFingerprintGuard {
    private static final String WORLDGEN_ID = "NN-DEV-1";
    private static final String ALGORITHM = "sha256-path-and-content-v1";
    private static final String ROOT_FINGERPRINT = "nevernether-worldgen-fingerprint.json";
    private static final String RESOURCE_FINGERPRINT = "data/neverfolia/nevernether/worldgen_fingerprint.json";
    private static final String LOCK_FILE = ".neverfolia-nevernether-worldgen.lock";
    private static final Pattern STRING_FIELD = Pattern.compile("\\\"([a-zA-Z0-9_]+)\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"");

    private record Fingerprint(String source, String declaredHash, String computedHash) {}

    private NeverNetherFingerprintGuard() {}

    static void verify(Path worldRoot, Path datapackDir) {
        try {
            verify0(worldRoot, datapackDir);
        } catch (IOException ex) {
            throw new IllegalStateException("NeverNether fingerprint guard could not verify worldgen inputs", ex);
        }
    }

    private static void verify0(Path worldRoot, Path datapackDir) throws IOException {
        Files.createDirectories(worldRoot);
        final Path lockPath = worldRoot.resolve(LOCK_FILE);
        final List<Fingerprint> fingerprints = discover(datapackDir);

        if (fingerprints.isEmpty()) {
            if (Files.exists(lockPath)) {
                throw new IllegalStateException(
                    "NeverNether worldgen fingerprint mismatch: world lock exists but no fingerprinted NeverNether datapack is installed"
                );
            }
            return;
        }

        final Set<String> hashes = new HashSet<>();
        for (Fingerprint fingerprint : fingerprints) {
            if (!fingerprint.declaredHash.equals(fingerprint.computedHash)) {
                throw new IllegalStateException(
                    "NeverNether datapack content fingerprint is invalid for " + fingerprint.source
                        + ": declared=" + fingerprint.declaredHash
                        + " computed=" + fingerprint.computedHash
                );
            }
            hashes.add(fingerprint.computedHash);
        }
        if (hashes.size() != 1) {
            throw new IllegalStateException(
                "Multiple different fingerprinted NeverNether datapacks are installed: " + hashes
            );
        }

        final String activeHash = hashes.iterator().next();
        if (!Files.exists(lockPath)) {
            writeLock(lockPath, activeHash);
            MinecraftServer.LOGGER.info(
                "[NeverFolia][NeverNether] Created worldgen fingerprint lock {} ({})",
                activeHash,
                fingerprints.getFirst().source
            );
            return;
        }

        final Properties lock = new Properties();
        try (InputStream in = Files.newInputStream(lockPath)) {
            lock.load(in);
        }
        final String lockedWorldgen = lock.getProperty("worldgen_id", "");
        final String lockedAlgorithm = lock.getProperty("algorithm", "");
        final String lockedHash = lock.getProperty("content_sha256", "");
        if (!WORLDGEN_ID.equals(lockedWorldgen) || !ALGORITHM.equals(lockedAlgorithm) || !activeHash.equals(lockedHash)) {
            throw new IllegalStateException(
                "NeverNether worldgen fingerprint mismatch: locked=" + lockedHash + " active=" + activeHash
                    + " worldgen=" + lockedWorldgen + " algorithm=" + lockedAlgorithm
            );
        }

        if (fingerprints.size() > 1) {
            MinecraftServer.LOGGER.warn(
                "[NeverFolia][NeverNether] {} identical fingerprinted datapacks are installed; remove duplicates before production",
                fingerprints.size()
            );
        }
        MinecraftServer.LOGGER.info("[NeverFolia][NeverNether] Worldgen fingerprint verified: {}", activeHash);
    }

    private static void writeLock(Path lockPath, String hash) throws IOException {
        final String value = "schema=1\n"
            + "worldgen_id=" + WORLDGEN_ID + "\n"
            + "algorithm=" + ALGORITHM + "\n"
            + "content_sha256=" + hash + "\n";
        final Path tmp = Files.createTempFile(lockPath.getParent(), LOCK_FILE + ".", ".tmp");
        Files.writeString(tmp, value, StandardCharsets.UTF_8);
        try {
            Files.move(tmp, lockPath, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException ex) {
            Files.move(tmp, lockPath, StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(tmp);
        }
    }

    private static List<Fingerprint> discover(Path datapackDir) throws IOException {
        final List<Fingerprint> result = new ArrayList<>();
        if (!Files.isDirectory(datapackDir)) {
            return result;
        }
        try (Stream<Path> stream = Files.list(datapackDir)) {
            final List<Path> packs = stream.sorted(Comparator.comparing(path -> path.getFileName().toString())).toList();
            for (Path pack : packs) {
                if (Files.isDirectory(pack)) {
                    final Fingerprint fingerprint = fingerprintDirectory(pack);
                    if (fingerprint != null) {
                        result.add(fingerprint);
                    }
                } else if (Files.isRegularFile(pack) && pack.getFileName().toString().toLowerCase(java.util.Locale.ROOT).endsWith(".zip")) {
                    final Fingerprint fingerprint = fingerprintZip(pack);
                    if (fingerprint != null) {
                        result.add(fingerprint);
                    }
                }
            }
        }
        return result;
    }

    private static Fingerprint fingerprintZip(Path pack) throws IOException {
        try (ZipFile zip = new ZipFile(pack.toFile())) {
            final ZipEntry rootEntry = zip.getEntry(ROOT_FINGERPRINT);
            final ZipEntry resourceEntry = zip.getEntry(RESOURCE_FINGERPRINT);
            if (rootEntry == null && resourceEntry == null) {
                return null;
            }
            if (rootEntry == null || resourceEntry == null) {
                throw new IllegalStateException("Incomplete NeverNether fingerprint markers in " + pack);
            }
            final String rootJson = new String(zip.getInputStream(rootEntry).readAllBytes(), StandardCharsets.UTF_8);
            final String resourceJson = new String(zip.getInputStream(resourceEntry).readAllBytes(), StandardCharsets.UTF_8);
            if (!rootJson.equals(resourceJson)) {
                throw new IllegalStateException("NeverNether root/resource fingerprint documents differ in " + pack);
            }
            final String declared = parseAndValidateDocument(rootJson, pack.toString());
            final MessageDigest digest = newDigest();
            final List<? extends ZipEntry> entries = zip.stream()
                .filter(entry -> !entry.isDirectory())
                .filter(entry -> !isFingerprintPath(entry.getName()))
                .sorted(Comparator.comparing(ZipEntry::getName))
                .toList();
            for (ZipEntry entry : entries) {
                final String name = entry.getName().replace('\\', '/');
                final byte[] nameBytes = name.getBytes(StandardCharsets.UTF_8);
                final byte[] payload = zip.getInputStream(entry).readAllBytes();
                updateInt(digest, nameBytes.length);
                digest.update(nameBytes);
                updateLong(digest, payload.length);
                digest.update(payload);
            }
            return new Fingerprint(pack.getFileName().toString(), declared, hex(digest.digest()));
        }
    }

    private static Fingerprint fingerprintDirectory(Path pack) throws IOException {
        final Path rootMarker = pack.resolve(ROOT_FINGERPRINT);
        final Path resourceMarker = pack.resolve(RESOURCE_FINGERPRINT.replace('/', java.io.File.separatorChar));
        final boolean hasRoot = Files.isRegularFile(rootMarker);
        final boolean hasResource = Files.isRegularFile(resourceMarker);
        if (!hasRoot && !hasResource) {
            return null;
        }
        if (!hasRoot || !hasResource) {
            throw new IllegalStateException("Incomplete NeverNether fingerprint markers in " + pack);
        }
        final String rootJson = Files.readString(rootMarker, StandardCharsets.UTF_8);
        final String resourceJson = Files.readString(resourceMarker, StandardCharsets.UTF_8);
        if (!rootJson.equals(resourceJson)) {
            throw new IllegalStateException("NeverNether root/resource fingerprint documents differ in " + pack);
        }
        final String declared = parseAndValidateDocument(rootJson, pack.toString());
        final MessageDigest digest = newDigest();
        try (Stream<Path> stream = Files.walk(pack)) {
            final List<Path> entries = stream
                .filter(Files::isRegularFile)
                .filter(path -> !isFingerprintPath(pack.relativize(path).toString().replace('\\', '/')))
                .sorted(Comparator.comparing(path -> pack.relativize(path).toString().replace('\\', '/')))
                .toList();
            for (Path entry : entries) {
                final String name = pack.relativize(entry).toString().replace('\\', '/');
                final byte[] nameBytes = name.getBytes(StandardCharsets.UTF_8);
                updateInt(digest, nameBytes.length);
                digest.update(nameBytes);
                updateLong(digest, Files.size(entry));
                try (InputStream in = Files.newInputStream(entry)) {
                    final byte[] buffer = new byte[8192];
                    int read;
                    while ((read = in.read(buffer)) >= 0) {
                        if (read > 0) {
                            digest.update(buffer, 0, read);
                        }
                    }
                }
            }
        }
        return new Fingerprint(pack.getFileName().toString(), declared, hex(digest.digest()));
    }

    private static String parseAndValidateDocument(String json, String source) {
        String worldgen = null;
        String algorithm = null;
        String hash = null;
        final Matcher matcher = STRING_FIELD.matcher(json);
        while (matcher.find()) {
            switch (matcher.group(1)) {
                case "worldgen_id" -> worldgen = matcher.group(2);
                case "algorithm" -> algorithm = matcher.group(2);
                case "content_sha256" -> hash = matcher.group(2);
                default -> { }
            }
        }
        if (!WORLDGEN_ID.equals(worldgen) || !ALGORITHM.equals(algorithm) || hash == null || !hash.matches("[0-9a-f]{64}")) {
            throw new IllegalStateException("Invalid NeverNether fingerprint document in " + source);
        }
        return hash;
    }

    private static boolean isFingerprintPath(String name) {
        return ROOT_FINGERPRINT.equals(name) || RESOURCE_FINGERPRINT.equals(name);
    }

    private static MessageDigest newDigest() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 is unavailable", ex);
        }
    }

    private static void updateInt(MessageDigest digest, int value) {
        digest.update((byte)(value >>> 24));
        digest.update((byte)(value >>> 16));
        digest.update((byte)(value >>> 8));
        digest.update((byte)value);
    }

    private static void updateLong(MessageDigest digest, long value) {
        digest.update((byte)(value >>> 56));
        digest.update((byte)(value >>> 48));
        digest.update((byte)(value >>> 40));
        digest.update((byte)(value >>> 32));
        digest.update((byte)(value >>> 24));
        digest.update((byte)(value >>> 16));
        digest.update((byte)(value >>> 8));
        digest.update((byte)value);
    }

    private static String hex(byte[] bytes) {
        final StringBuilder builder = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) {
            builder.append(Character.forDigit((value >>> 4) & 0xF, 16));
            builder.append(Character.forDigit(value & 0xF, 16));
        }
        return builder.toString();
    }
}
'''


def patch_server(source: str) -> str:
    if "NeverNetherFingerprintGuard.verify" in source:
        fail("MinecraftServer is already patched")
    pattern = re.compile(
        r"(?P<indent>^[ \t]*)this\.storageSource\s*=\s*(?P<rhs>[A-Za-z_$][A-Za-z0-9_$]*)\s*;",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        fail(f"expected exactly one MinecraftServer storageSource assignment, got {len(matches)}")
    match = matches[0]
    indent = match.group("indent")
    rhs = match.group("rhs")
    replacement = (
        match.group(0)
        + "\n"
        + indent
        + "NeverNetherFingerprintGuard.verify("
        + rhs
        + ".getLevelPath(net.minecraft.world.level.storage.LevelResource.ROOT), "
        + rhs
        + ".getLevelPath(net.minecraft.world.level.storage.LevelResource.DATAPACK_DIR));"
    )
    return source[: match.start()] + replacement + source[match.end() :]


def self_test() -> None:
    synthetic = """package net.minecraft.server;\nclass MinecraftServer {\n    void x(Object storageSource) {\n        this.storageSource = storageSource;\n    }\n}\n"""
    patched = patch_server(synthetic)
    if patched.count("NeverNetherFingerprintGuard.verify") != 1:
        fail("SELF-TEST: guard call was not injected exactly once")
    if "LevelResource.DATAPACK_DIR" not in patched or "LevelResource.ROOT" not in patched:
        fail("SELF-TEST: world/datapack paths missing from injected call")
    source = helper_source()
    for required in (
        "sha256-path-and-content-v1",
        "NeverNether worldgen fingerprint mismatch",
        "ZipFile",
        "content_sha256",
    ):
        if required not in source:
            fail(f"SELF-TEST: helper missing {required!r}")
    print("[NeverFolia][NeverNether fingerprint guard] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply the NeverNether startup fingerprint guard")
    parser.add_argument("folia", nargs="?", type=Path, help="Path to the prepared Folia worktree")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required unless --self-test is used")

    folia = args.folia.resolve()
    server = folia / SERVER_REL
    helper = folia / HELPER_REL
    if not server.is_file():
        fail(f"MinecraftServer source not found: {server}")
    source = server.read_text(encoding="utf-8")
    patched = patch_server(source)
    server.write_text(patched, encoding="utf-8")
    helper.write_text(helper_source(), encoding="utf-8")
    print("[NeverFolia][NeverNether fingerprint guard] applied")
    print(f"  server: {server}")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
