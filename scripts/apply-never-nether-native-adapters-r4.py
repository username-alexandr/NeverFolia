#!/usr/bin/env python3
"""Install narrowly scoped native 26.2 quota and void-filter adapters.

No third-party processors/templates are embedded; no source importer is unblocked.
All hook contracts are validated before writing any generated source file.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
JAVA = 'folia-server/src/minecraft/java'
POOLS = 'net/minecraft/world/level/levelgen/structure/pools/'
REGISTRY = 'net/minecraft/core/registries/BuiltInRegistries.java'
MARKER = '// NeverFolia NN-NATIVE-R4'

HOOKS = {
    POOLS + 'StructurePoolElementType.java': (
        '    MapCodec<P> codec();',
        '    ' + MARKER + '\n'
        '    StructurePoolElementType<NeverNetherLimitedPoolElement> NEVERFOLIA_LIMITED_SINGLE = register(\n'
        '        "neverfolia:limited_single_pool_element", NeverNetherLimitedPoolElement.CODEC);\n\n'
        '    MapCodec<P> codec();'
    ),
    POOLS + 'ListPoolElement.java': (
        '    @Override\n    public Vec3i getSize(',
        '    ' + MARKER + '\n'
        '    List<StructurePoolElement> neverfoliaQuotaChildren() { return List.copyOf(this.elements); }\n\n'
        '    @Override\n    public Vec3i getSize('
    ),
    REGISTRY: (
        '        Registries.STRUCTURE_PROCESSOR, StructureProcessorTypes::bootstrap',
        '        ' + MARKER + '\n'
        '        Registries.STRUCTURE_PROCESSOR, registry -> {\n'
        '            var vanilla = StructureProcessorTypes.bootstrap(registry);\n'
        '            net.minecraft.world.level.levelgen.structure.templatesystem.NeverNetherNativeProcessors.register(registry);\n'
        '            return vanilla;\n'
        '        }'
    ),
}
PLACEMENT_HOOKS = (
    (
        '        if (centerElement == EmptyPoolElement.INSTANCE) {',
        '        ' + MARKER + ' root quota\n'
        '        if (centerElement == EmptyPoolElement.INSTANCE || !NeverNetherLimitedPoolElement.canAppend(centerElement, List.of())) {'
    ),
    (
        '                                for (Rotation targetRotation : Rotation.getShuffled(this.random)) {',
        '                                ' + MARKER + ' accepted pieces only, before geometry attempts\n'
        '                                if (!NeverNetherLimitedPoolElement.canAppend(targetElement, this.pieces)) continue;\n\n'
        '                                for (Rotation targetRotation : Rotation.getShuffled(this.random)) {'
    ),
)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        if text.count(new) != 1: raise ValueError(f'Duplicate native hook: {label}')
        return text
    if text.count(old) != 1:
        raise ValueError(f'Expected exactly one native API anchor: {label}; found {text.count(old)}')
    return text.replace(old, new, 1)


def prepare(root: Path, include_smoke: bool = False) -> dict[Path, str]:
    target = root / JAVA
    if not target.is_dir(): raise ValueError(f'Folia generated sources missing: {target}')
    staged = {}
    for rel, (old, new) in HOOKS.items():
        path = target / rel
        staged[path] = replace_once(path.read_text(), old, new, rel)
    placement = target / POOLS / 'JigsawPlacement.java'
    text = placement.read_text()
    for index, (old, new) in enumerate(PLACEMENT_HOOKS):
        text = replace_once(text, old, new, f'JigsawPlacement hook {index}')
    staged[placement] = text
    source = ROOT / 'native/nevernether/java'
    expected = {
        POOLS + 'NeverNetherPieceBudget.java',
        POOLS + 'NeverNetherLimitedPoolElement.java',
        'net/minecraft/world/level/levelgen/structure/templatesystem/NeverNetherNativeProcessors.java',
        'net/minecraft/world/level/levelgen/structure/templatesystem/NeverNetherPillarPlan.java',
        'net/minecraft/world/level/levelgen/structure/templatesystem/NeverNetherNoise.java',
    }
    found = {str(p.relative_to(source)) for p in source.rglob('*.java')}
    if found != expected: raise ValueError(f'Unexpected native source set: {sorted(found)}')
    for rel in sorted(expected): staged[target / rel] = (source / rel).read_text()
    if include_smoke:
        staged[target / POOLS / 'NeverNetherNativeSmoke.java'] = (ROOT / 'native/nevernether/test/NeverNetherNativeSmoke.java').read_text()
    return staged


def apply(root: Path, include_smoke: bool = False) -> None:
    staged = prepare(root, include_smoke)
    for path, content in staged.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    print(f'[NeverFolia][NN-NATIVE-R4] Installed {len(staged)} native files/hooks; R5 property/vertical-support processors installed; runtime QA required')


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp); target = root / JAVA
        for rel, (old, _) in HOOKS.items():
            p = target / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('prefix\n' + old + '\nsuffix\n')
        placement = target / POOLS / 'JigsawPlacement.java'
        placement.write_text('\n'.join(old for old, _ in PLACEMENT_HOOKS))
        staged = prepare(root)
        assert len(staged) == 9
        for p, text in staged.items(): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
        assert prepare(root) == staged
        placement.write_text('missing anchor')
        before = {p: p.read_bytes() for p in target.rglob('*.java')}
        try: apply(root)
        except ValueError: pass
        else: raise AssertionError('A changed upstream API must reject the hook')
        assert before == {p: p.read_bytes() for p in target.rglob('*.java')}
        print('[NeverFolia][NN-NATIVE-R4] Patch contract SELF-TEST OK (not a compiler test)')


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folia', nargs='?', type=Path)
    p.add_argument('--include-smoke-test', action='store_true')
    p.add_argument('--self-test', action='store_true')
    args = p.parse_args()
    if args.self_test: self_test(); return
    if args.folia is None: p.error('Folia source directory required')
    apply(args.folia, args.include_smoke_test)

if __name__ == '__main__': main()
