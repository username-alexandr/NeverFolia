#!/usr/bin/env python3
"""Integrate the tested R3915 Swift Soar owned-lifecycle hook at source level.

Equivalent to the previous Java 25 ClassFile transform: call
NeverFoliaSwiftLifecycleR3915.tick(entity) at the start of
EnchantmentHelper.tickEffects(ServerLevel, LivingEntity).
"""
from __future__ import annotations
import argparse,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path("folia-server/src/minecraft/java")
TARGET=JAVA/"net/minecraft/world/item/enchantment/EnchantmentHelper.java"
HELPER=JAVA/"net/minecraft/world/item/enchantment/NeverFoliaSwiftLifecycleR3915.java"
CALL_PREFIX="NeverFoliaSwiftLifecycleR3915.tick("

def fail(msg:str)->None:
    raise ValueError("[R3915-SWIFT-INTEGRATION] "+msg)

def patch(text:str)->str:
    if CALL_PREFIX in text:
        if text.count(CALL_PREFIX)!=1: fail("duplicate lifecycle hook")
        return text
    # Materialized Mojang/Paper sources may add final/annotations to parameters.
    # Match the method shape first, then derive the second parameter identifier
    # without assuming exact source formatting.
    pat=re.compile(r'(?P<head>\bstatic\s+void\s+tickEffects\s*\((?P<params>[^)]*)\)\s*\{)')
    matches=list(pat.finditer(text))
    if len(matches)!=1: fail("tickEffects source anchor missing/ambiguous: "+str(len(matches)))
    m=matches[0]
    params=[p.strip() for p in m.group("params").split(",")]
    if len(params)!=2 or "ServerLevel" not in params[0] or "LivingEntity" not in params[1]:
        fail("unexpected tickEffects parameters: "+m.group("params"))
    ident=re.search(r'([A-Za-z_$][A-Za-z0-9_$]*)\s*$',params[1])
    if not ident: fail("cannot derive LivingEntity parameter name")
    entity=ident.group(1)
    call="\n        NeverFoliaSwiftLifecycleR3915.tick("+entity+"); // R3915_SWIFT_OWNED_LIFECYCLE"
    return text[:m.end()]+call+text[m.end():]

def prepare(folia:Path)->dict[Path,str]:
    target=folia/TARGET
    if not target.is_file(): fail("materialized EnchantmentHelper.java missing")
    helper_src=ROOT/"qa/field-r3915/NeverFoliaSwiftLifecycleR3915.java"
    if not helper_src.is_file(): fail("tested lifecycle helper source missing")
    return {
        target:patch(target.read_text(encoding="utf-8")),
        folia/HELPER:helper_src.read_text(encoding="utf-8"),
    }

def verify(folia:Path,staged:dict[Path,str])->None:
    target=folia/TARGET
    text=staged.get(target,target.read_text(encoding="utf-8"))
    if text.count(CALL_PREFIX)!=1: fail("lifecycle call invariant failed")
    helper=folia/HELPER
    expected=(ROOT/"qa/field-r3915/NeverFoliaSwiftLifecycleR3915.java").read_text(encoding="utf-8")
    actual=staged.get(helper,helper.read_text(encoding="utf-8") if helper.is_file() else "")
    if actual!=expected: fail("lifecycle helper differs from tested R3915 source")

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia",type=Path)
    p.add_argument("--check-only",action="store_true")
    a=p.parse_args();folia=a.folia.resolve()
    staged=prepare(folia);verify(folia,staged)
    if not a.check_only:
        for path,text in staged.items():
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text,encoding="utf-8")
    print("[R3915-SWIFT-INTEGRATION] owned lifecycle hook integrated at tickEffects entry")

if __name__=="__main__":
    main()
