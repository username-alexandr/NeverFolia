#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

FAST_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaFastLocate.java")
POLICY_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldVanillaStructurePolicy.java")
FAST_SIG = "    private static boolean passesNeverOverworldPolicy("
POLICY_SIG = "    static boolean allows("
MARKER = "// NeverFolia R9-v11 QA: shared village dry-score contract."
NON_VILLAGE_ANCHOR = "// Unrelated dry-land structures retain their established exact 3x3"

PROBES = [
    (-64, 0), (64, 0), (0, -64), (0, 64),
    (-32, -32), (-32, 0), (-32, 32),
    (0, -32), (0, 32),
    (32, -32), (32, 0), (32, 32),
]
PROFILES = {"score10": 10, "score9": 9, "score8": 8}

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
    raise SystemExit(f"[NeverFolia][R9 village dry-score v11] {message}")


def find_method_end(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0: fail(f"method not found: {signature.strip()}")
    opening = text.find("{", start)
    if opening < 0: fail("opening brace missing")
    depth=0; in_s=in_c=in_line=in_block=escaped=False; i=opening
    while i < len(text):
        ch=text[i]; nxt=text[i+1] if i+1<len(text) else ""
        if in_line:
            if ch=="\n": in_line=False
            i+=1; continue
        if in_block:
            if ch=="*" and nxt=="/": in_block=False; i+=2
            else: i+=1
            continue
        if in_s:
            if escaped: escaped=False
            elif ch=="\\": escaped=True
            elif ch=='"': in_s=False
            i+=1; continue
        if in_c:
            if escaped: escaped=False
            elif ch=="\\": escaped=True
            elif ch=="'": in_c=False
            i+=1; continue
        if ch=="/" and nxt=="/": in_line=True; i+=2; continue
        if ch=="/" and nxt=="*": in_block=True; i+=2; continue
        if ch=='"': in_s=True; i+=1; continue
        if ch=="'": in_c=True; i+=1; continue
        if ch=="{": depth+=1
        elif ch=="}":
            depth-=1
            if depth==0:
                end=i+1
                if end<len(text) and text[end]=="\n": end+=1
                return start,end
        i+=1
    fail("unterminated method")


def java_points() -> str:
    return "{" + ", ".join("{"+f"{x}, {z}"+"}" for x,z in PROBES) + "}"


def switch_java() -> str:
    return "\n".join(f'                case "{name}" -> {threshold};' for name,threshold in PROFILES.items())


def fast_code() -> str:
    return f'''            {MARKER}
            final String dryScoreProfile = System.getProperty("neverfolia.villageDryScoreProfile", "score10");
            final int minDryProbes = switch (dryScoreProfile) {{
{switch_java()}
                default -> throw new IllegalArgumentException("Unknown NeverFolia village dry-score profile: " + dryScoreProfile);
            }};
            final int[][] villageProbes = new int[][] {java_points()};
            int dryProbes = 0;
            final StringBuilder wetProbes = new StringBuilder();
            for (final int[] probeOffset : villageProbes) {{
                final int dx = probeOffset[0];
                final int dz = probeOffset[1];
                final int surfaceY = preliminarySurfaceY(state, centerX + dx, centerZ + dz);
                if (surfaceY >= MIN_DRY_BASE_HEIGHT) {{
                    ++dryProbes;
                }} else {{
                    if (!wetProbes.isEmpty()) wetProbes.append(';');
                    wetProbes.append(dx).append(',').append(dz).append('=').append(surfaceY);
                }}
            }}
            if (dryProbes < minDryProbes) {{
                debugVillage(id, "R9V11_SCORE_REJECT", chunkPos, centerSurfaceY,
                    "profile=" + dryScoreProfile + ",dry=" + dryProbes + "/" + villageProbes.length + ",wet=" + wetProbes);
                return false;
            }}
            debugVillage(id, "R9V11_ACCEPT", chunkPos, centerSurfaceY,
                "profile=" + dryScoreProfile + ",dry=" + dryProbes + "/" + villageProbes.length + ",wet=" + wetProbes);
            return true;
'''


def generation_code() -> str:
    return f'''            {MARKER}
            final String dryScoreProfile = System.getProperty("neverfolia.villageDryScoreProfile", "score10");
            final int minDryProbes = switch (dryScoreProfile) {{
{switch_java()}
                default -> throw new IllegalArgumentException("Unknown NeverFolia village dry-score profile: " + dryScoreProfile);
            }};
            final int[][] villageProbes = new int[][] {java_points()};
            int dryProbes = 0;
            for (final int[] probeOffset : villageProbes) {{
                if (preliminarySurfaceY(randomState, centerX + probeOffset[0], centerZ + probeOffset[1]) >= MIN_DRY_BASE_HEIGHT) {{
                    ++dryProbes;
                }}
            }}
            return dryProbes >= minDryProbes;
'''


def patch(text: str, sig: str, old: str, new: str, label: str) -> str:
    start,end=find_method_end(text,sig); method=text[start:end]
    if MARKER in method: return text
    if old not in method: fail(f"{label}: corrected V5 anchor missing")
    method=method.replace(old,new,1)
    return text[:start]+method+text[end:]


def validate(fast: str, policy: str) -> None:
    for label,text,sig in (("fast",fast,FAST_SIG),("generation",policy,POLICY_SIG)):
        start,end=find_method_end(text,sig); method=text[start:end]
        if MARKER not in method: fail(f"{label}: V11 marker missing")
        if 'System.getProperty("neverfolia.villageDryScoreProfile", "score10")' not in method: fail(f"{label}: selector missing")
        for profile in PROFILES:
            if f'case "{profile}"' not in method: fail(f"{label}: profile missing {profile}")
        for forbidden in ("Structure.generate(","NeverOverworldGeneratedVillageSafety.preview"):
            if forbidden in method: fail(f"{label}: watchdog-risk primitive leaked: {forbidden}")
        if label=="fast" and "getBaseHeight(" in method: fail("fast: getBaseHeight leaked")
        if label=="generation":
            a=method.find(MARKER); b=method.find(NON_VILLAGE_ANCHOR,a)
            if b<0: fail("generation: non-village boundary missing")
            if "getBaseHeight(" in method[a:b]: fail("generation: getBaseHeight leaked into village score block")
    if "R9V11_SCORE_REJECT" not in fast or "R9V11_ACCEPT" not in fast: fail("fast diagnostics missing")


def self_test() -> None:
    if len(PROBES)!=12 or len(set(PROBES))!=12 or (0,0) in PROBES: fail("SELF-TEST: invalid probe set")
    if sorted(PROFILES.values()) != [8,9,10]: fail("SELF-TEST: thresholds drifted")
    ff='''class F {\n    private static boolean passesNeverOverworldPolicy(int x) {\n'''+OLD_FAST+'''    }\n}\n'''
    pf='''class P {\n    static boolean allows(int x) {\n'''+OLD_GENERATION+'''        // Unrelated dry-land structures retain their established exact 3x3 generation-side surface contract.\n        return generator.getBaseHeight(0,0,type,heightAccessor,randomState)>0;\n    }\n}\n'''
    f=patch(ff,FAST_SIG,OLD_FAST,fast_code(),"fast"); p=patch(pf,POLICY_SIG,OLD_GENERATION,generation_code(),"generation")
    validate(f,p)
    if patch(f,FAST_SIG,OLD_FAST,fast_code(),"fast")!=f: fail("SELF-TEST: fast not idempotent")
    if patch(p,POLICY_SIG,OLD_GENERATION,generation_code(),"generation")!=p: fail("SELF-TEST: generation not idempotent")
    print("[NeverFolia][R9 village dry-score v11] SELF-TEST OK")
    print("  probes: 12 = cardinal64 + inner3")
    print("  profiles: score10, score9, score8")
    print("  locate/generation share identical score calculation")


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("folia",nargs="?",type=Path); ap.add_argument("--self-test",action="store_true"); a=ap.parse_args()
    if a.self_test: self_test(); return
    if a.folia is None: ap.error("folia worktree required")
    self_test(); root=a.folia.resolve(); fp=root/FAST_REL; pp=root/POLICY_REL
    for path in (fp,pp):
        if not path.is_file(): fail(f"helper missing: {path}")
    f=patch(fp.read_text(encoding="utf-8"),FAST_SIG,OLD_FAST,fast_code(),"fast")
    p=patch(pp.read_text(encoding="utf-8"),POLICY_SIG,OLD_GENERATION,generation_code(),"generation")
    validate(f,p); fp.write_text(f,encoding="utf-8"); pp.write_text(p,encoding="utf-8")
    print("[NeverFolia][R9 village dry-score v11] shared dry-score matrix applied")

if __name__=="__main__": main()
