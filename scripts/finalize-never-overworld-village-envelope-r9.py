#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

FAST_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
FAST_SIG = "    private static boolean passesNeverOverworldPolicy("
POLICY_SIG = "    static boolean allows("
MARKER_PREFIX = "// NeverFolia R9-final: shared hardcoded village envelope profile="

PROFILES = {
    "reach48": [
        (dx, dz) for dx in (-48, -24, 0, 24, 48) for dz in (-48, -24, 0, 24, 48) if (dx, dz) != (0, 0)
    ],
    "cardinal64diag32": [
        (-64, 0), (64, 0), (0, -64), (0, 64),
        (-32, -32), (-32, 32), (32, -32), (32, 32),
    ],
    "cardinal64inner3": [
        (-64, 0), (64, 0), (0, -64), (0, 64),
        (-32, -32), (-32, 0), (-32, 32), (0, -32), (0, 32), (32, -32), (32, 0), (32, 32),
    ],
}

OLD_FAST = '''            final int villageReach = 64;
            final int[] villageOffsets = {-64, -32, 0, 32, 64};
            for (final int dx : villageOffsets) {
                for (final int dz : villageOffsets) {
                    if (dx == 0 && dz == 0) {
                        continue;
                    }
                    final int surfaceY = preliminarySurfaceY(state, centerX + dx, centerZ + dz);
                    if (surfaceY < MIN_DRY_BASE_HEIGHT) {
                        debugVillage(
                            id,
                            "R9V5_ENVELOPE_REJECT",
                            chunkPos,
                            centerSurfaceY,
                            "sample=" + dx + "," + dz + ",surface=" + surfaceY + ",reach=" + villageReach
                        );
                        return false;
                    }
                }
            }
            debugVillage(id, "R9V5_ACCEPT", chunkPos, centerSurfaceY, "5x5-calibrated-reach=" + villageReach);
            return true;
'''

OLD_GENERATION = '''            final int villageReach = 64;
            final int[] villageOffsets = {-64, -32, 0, 32, 64};
            for (final int dx : villageOffsets) {
                for (final int dz : villageOffsets) {
                    if (dx == 0 && dz == 0) {
                        continue;
                    }
                    if (preliminarySurfaceY(randomState, centerX + dx, centerZ + dz) < MIN_DRY_BASE_HEIGHT) {
                        return false;
                    }
                }
            }
            return villageReach == 64;
'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 final village envelope] {message}")


def find_method_end(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0: fail(f"method not found: {signature.strip()}")
    opening = text.find("{", start)
    if opening < 0: fail("opening brace missing")
    depth = 0; in_string = in_char = in_line = in_block = escaped = False; i = opening
    while i < len(text):
        ch=text[i]; nxt=text[i+1] if i+1<len(text) else ""
        if in_line:
            if ch=="\n": in_line=False
            i+=1; continue
        if in_block:
            if ch=="*" and nxt=="/": in_block=False; i+=2
            else: i+=1
            continue
        if in_string:
            if escaped: escaped=False
            elif ch=="\\": escaped=True
            elif ch=='"': in_string=False
            i+=1; continue
        if in_char:
            if escaped: escaped=False
            elif ch=="\\": escaped=True
            elif ch=="'": in_char=False
            i+=1; continue
        if ch=="/" and nxt=="/": in_line=True; i+=2; continue
        if ch=="/" and nxt=="*": in_block=True; i+=2; continue
        if ch=='"': in_string=True; i+=1; continue
        if ch=="'": in_char=True; i+=1; continue
        if ch=="{": depth+=1
        elif ch=="}":
            depth-=1
            if depth==0:
                end=i+1
                if end<len(text) and text[end]=="\n": end+=1
                return start,end
        i+=1
    fail("unterminated method")


def java_points(points: list[tuple[int,int]]) -> str:
    return "{" + ", ".join("{" + f"{x}, {z}" + "}" for x,z in points) + "}"


def fast_code(profile: str) -> str:
    points=PROFILES[profile]
    return f'''            {MARKER_PREFIX}{profile}
            final int[][] villageProbes = new int[][] {java_points(points)};
            for (final int[] probeOffset : villageProbes) {{
                final int dx = probeOffset[0];
                final int dz = probeOffset[1];
                final int surfaceY = preliminarySurfaceY(state, centerX + dx, centerZ + dz);
                if (surfaceY < MIN_DRY_BASE_HEIGHT) {{
                    debugVillage(id, "R9FINAL_ENVELOPE_REJECT", chunkPos, centerSurfaceY,
                        "profile={profile},sample=" + dx + "," + dz + ",surface=" + surfaceY);
                    return false;
                }}
            }}
            debugVillage(id, "R9FINAL_ACCEPT", chunkPos, centerSurfaceY, "profile={profile},probes=" + villageProbes.length);
            return true;
'''


def generation_code(profile: str) -> str:
    points=PROFILES[profile]
    return f'''            {MARKER_PREFIX}{profile}
            final int[][] villageProbes = new int[][] {java_points(points)};
            for (final int[] probeOffset : villageProbes) {{
                if (preliminarySurfaceY(randomState, centerX + probeOffset[0], centerZ + probeOffset[1]) < MIN_DRY_BASE_HEIGHT) {{
                    return false;
                }}
            }}
            return true;
'''


def replace(text: str, signature: str, old: str, new: str, label: str) -> str:
    start,end=find_method_end(text,signature); method=text[start:end]
    if MARKER_PREFIX in method:
        if new.strip() in method: return text
        fail(f"{label}: a different final envelope is already installed")
    if old not in method: fail(f"{label}: V5 reach64 anchor missing")
    method=method.replace(old,new,1)
    return text[:start]+method+text[end:]


def validate(fast: str, policy: str, profile: str) -> None:
    marker=MARKER_PREFIX+profile
    for label,text,sig in (("fast",fast,FAST_SIG),("generation",policy,POLICY_SIG)):
        start,end=find_method_end(text,sig); method=text[start:end]
        if marker not in method: fail(f"{label}: final profile marker missing")
        if "neverfolia.villageEnvelopeProfile" in method: fail(f"{label}: QA runtime selector leaked into production finalizer")
        for forbidden in ("Structure.generate(","NeverOverworldGeneratedVillageSafety.preview","getBaseHeight("):
            if forbidden in method: fail(f"{label}: watchdog-risk primitive leaked: {forbidden}")
    if "R9FINAL_ACCEPT" not in fast: fail("final accept diagnostic missing")


def self_test() -> None:
    for profile,points in PROFILES.items():
        if not points or len(set(points)) != len(points) or (0,0) in points:
            fail(f"SELF-TEST: invalid points for {profile}")
        fast_fixture='''class F {\n    private static boolean passesNeverOverworldPolicy(int x) {\n'''+OLD_FAST+'''    }\n}\n'''
        gen_fixture='''class P {\n    static boolean allows(int x) {\n'''+OLD_GENERATION+'''    }\n}\n'''
        fast=replace(fast_fixture,FAST_SIG,OLD_FAST,fast_code(profile),"fast")
        policy=replace(gen_fixture,POLICY_SIG,OLD_GENERATION,generation_code(profile),"generation")
        validate(fast,policy,profile)
    print("[NeverFolia][R9 final village envelope] SELF-TEST OK")
    for profile,points in PROFILES.items(): print(f"  {profile}: {len(points)} hardcoded shared probes")


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("folia",nargs="?",type=Path); parser.add_argument("--profile",choices=sorted(PROFILES)); parser.add_argument("--self-test",action="store_true"); args=parser.parse_args()
    if args.self_test: self_test(); return
    if args.folia is None or args.profile is None: parser.error("folia and --profile are required")
    self_test(); root=args.folia.resolve(); fast_path=root/FAST_REL; policy_path=root/POLICY_REL
    for path in (fast_path,policy_path):
        if not path.is_file(): fail(f"helper missing: {path}")
    fast=replace(fast_path.read_text(encoding="utf-8"),FAST_SIG,OLD_FAST,fast_code(args.profile),"fast")
    policy=replace(policy_path.read_text(encoding="utf-8"),POLICY_SIG,OLD_GENERATION,generation_code(args.profile),"generation")
    validate(fast,policy,args.profile)
    fast_path.write_text(fast,encoding="utf-8"); policy_path.write_text(policy,encoding="utf-8")
    print(f"[NeverFolia][R9 final village envelope] hardcoded profile applied: {args.profile}")

if __name__=="__main__": main()
