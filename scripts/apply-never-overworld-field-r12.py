#!/usr/bin/env python3
"""Install FIELD-R12 after exact TREE-R1/VILLAGE-NOFILL-R1 source chain.

Standing trees now use origin Y >= ocean-2, not a submerged-block census.
The 25% ore retention and persisted mine protection are unchanged. This script
never edits saved worlds, lock files or datapacks. Unexpected sources fail closed.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('folia-server/src/minecraft/java')
HELPERS=ROOT/'native/neveroverworld/field-r12/java'
CONTRACTS = {'net/minecraft/world/level/levelgen/feature/TreeFeature.java': {'before': 'c440597f3bb10fe8b71cf873f600e802ff8790ba7c1942028dbdfe24aa54cce5', 'after': 'ff5fac2e8f1bb49acd3060332e634e5bdedc39cb24f6a5779a2150c1978e7f66'}, 'net/minecraft/world/level/levelgen/feature/FallenTreeFeature.java': {'before': '5bb371cda260c9c13d085150662825db2a2ffe02f2ecd106167db2cca6f828d0', 'after': '342d4a2a56083d9f4af24980fb8e44c18a5ad26a078af86f9bc3ea5afff56ab6'}, 'net/minecraft/world/level/chunk/NeverOverworldOreScarcityFieldR10.java': {'before': 'f33020f4ab3d7b05ec07f71a12837085c9837ec8857957329a4c623add5f5267', 'after': '58fef2d8e8e71311883e82087c7e7487ceffb420297249077957fc23e1d54dc6'}, 'net/minecraft/world/level/chunk/ChunkGenerator.java': {'before': '2d210eb16e4ba1796c61cd2d40c0620421c7d0ae2db093a62547154b3febaa1e', 'after': '3df646c8711deed4fb8d78b6a35789289b4ed6f30b2d326cc773dea737cbaa7b'}, 'net/minecraft/world/level/levelgen/structure/StructureStart.java': {'before': 'ef818327aa2aca2a1feff490040085a087a8bdc40d3dfeec6813e6297aba133c', 'after': 'd36597f6df0c20de6afdaa8e916581b4113b20710f62c840c16fa8677d85d13e'}, 'net/minecraft/world/level/chunk/ChunkAccess.java': {'before': 'c0eaf986d07f73c56af3ac7e928280579b4e584cacc423d474199a86b360b05b', 'after': '2cdbd69013cae84bc0edd72bf72fcfb6e4ef63f1d9480df7915c9f94ed3a9cdc'}, 'net/minecraft/world/level/chunk/NeverOverworldFlood.java': {'before': '2622918f5c3054321d72b49e9770fd866490cdf17b4e9b99aba60e62e09d0913', 'after': 'ea62519b643b651b00f5ecbfa63fba85b9b184d8b07e979e54454962256d4532'}, 'net/minecraft/world/level/chunk/NeverOverworldFloodBoundaryR11.java': {'before': '30dfed0af792503d9f1f6ba6bf39899c096d726dd5b71e36fac25a475962d611', 'after': '33f4bf6a92b089a4c06b87e9bbece5490b38691ba4bf4d667844e5fee9540181'}}

RULES = {'net/minecraft/world/level/levelgen/feature/TreeFeature.java': [('        final WorldGenLevel level = context.level();', '        // FIELD-R12 height revision: origin is at most two blocks below the ocean.\n        final var neverTreeProposalR12 = net.minecraft.world.level.chunk.NeverOverworldTreePlacementR12.begin(context.level(), context.origin());\n        if (!neverTreeProposalR12.canStart()) return false;\n        final WorldGenLevel level = neverTreeProposalR12.view();', 1), ('        if (result && (!trunks.isEmpty() || !foliage.isEmpty())) {\n', '        if (result && (!trunks.isEmpty() || !foliage.isEmpty())) {\n            if (!neverTreeProposalR12.acceptAndCommit()) return false;\n', 1), ('return level.isStateAtPosition(pos, state -> state.isAir() || state.is(BlockTags.REPLACEABLE_BY_TREES));', 'return level.isStateAtPosition(pos, state -> state.isAir() || state.is(BlockTags.REPLACEABLE_BY_TREES)\n            || state.is(Blocks.WATER) && net.minecraft.world.level.chunk.NeverOverworldTreePlacementR12.allowsCandidateWater(level, pos));', 1)], 'net/minecraft/world/level/levelgen/feature/FallenTreeFeature.java': [('!TreeFeature.validTreePos(level, logStartPos)', '!net.minecraft.world.level.chunk.NeverOverworldTreePlacementR12.fallenPosition(level, logStartPos)', 1), ('return TreeFeature.validTreePos(level, blockPos) && this.isOverSolidGround(level, blockPos);', 'return net.minecraft.world.level.chunk.NeverOverworldTreePlacementR12.fallenPosition(level, blockPos) && this.isOverSolidGround(level, blockPos);', 1)], 'net/minecraft/world/level/chunk/NeverOverworldOreScarcityFieldR10.java': [('Additional field-requested 50% deterministic thinning over final generated', 'FIELD-R12: retain 25% instead of the previous 50%, with the SAME deterministic mask over final generated', 1), ('public static final int KEEP_PERCENT = 50;', 'public static final int KEEP_PERCENT = 25; // FIELD-R12: another ~50% below 32c6df3', 1)], 'net/minecraft/world/level/chunk/ChunkGenerator.java': [('start.getBoundingBox().intersects(targetBlockX, targetBlockZ, targetBlockX + 15, targetBlockZ + 15)', 'NeverOverworldDryMinesR12.referenceBox(level, start).intersects(targetBlockX, targetBlockZ, targetBlockX + 15, targetBlockZ + 15)', 1)], 'net/minecraft/world/level/levelgen/structure/StructureStart.java': [('            // VILLAGE-NOFILL-R1: keep vanilla placement; never reclaim the surrounding ocean to Y=128.', '            // VILLAGE-NOFILL-R1: keep vanilla placement; never reclaim the surrounding ocean to Y=128.\n            net.minecraft.world.level.chunk.NeverOverworldDryMinesR12.record(level, this, chunkPos);', 1)], 'net/minecraft/world/level/chunk/ChunkAccess.java': [('    protected final LevelChunkSection[] sections;', '    protected final LevelChunkSection[] sections;\n    // FIELD-R12 ephemeral LIGHT cache; authoritative geometry is in persisted chunk PDC.\n    public NeverOverworldDryMinesR12.Mask neverOverworldDryMineMaskR12;', 1)], 'net/minecraft/world/level/chunk/NeverOverworldFlood.java': [('        final FloodShorelineSnapshot shorelineFlora = captureFloodShorelineFlora(chunk);', '        NeverOverworldDryMinesR12.prepare(chunk);\n        final FloodShorelineSnapshot shorelineFlora = captureFloodShorelineFlora(chunk);', 1), ('if (!isFloodable(chunk.getBlockState(pos))) {', 'if (!isFloodable(chunk.getBlockState(pos)) || NeverOverworldDryMinesR12.protectedCell(chunk, pos)) {', 3), ('        NeverOverworldDesertR1.generate(level, chunk);', '        NeverOverworldDesertR1.generate(level, chunk);\n        chunk.neverOverworldDryMineMaskR12 = null;', 1)], 'net/minecraft/world/level/chunk/NeverOverworldFloodBoundaryR11.java': [('!isFloodable(chunk.getBlockState(pos)) || isProtected(protectedBoxes,', '!isFloodable(chunk.getBlockState(pos)) || NeverOverworldDryMinesR12.protectedCell(chunk, pos) || isProtected(protectedBoxes,', 2), ('if (isFloodable(state) && !state.is(Blocks.WATER)) {', 'if (isFloodable(state) && !state.is(Blocks.WATER) && !NeverOverworldDryMinesR12.protectedCell(chunk, pos)) {', 1)]}

def digest(text): return hashlib.sha256(text.encode('utf-8')).hexdigest()

def transform(path, text):
    for before, after, count in RULES[path]:
        if text.count(before) != count:
            raise ValueError(f'{path}: expected {count} exact anchors, got {text.count(before)}')
        text=text.replace(before, after)
    return text

def patch(path, text):
    contract=CONTRACTS[path]
    if digest(text)==contract['after']:return text
    if digest(text)!=contract['before']:raise ValueError('Uninspected FIELD-R12 input: '+path)
    out=transform(path,text)
    if digest(out)!=contract['after']:raise ValueError('FIELD-R12 output contract drift: '+path)
    return out

def prepare(folia):
    staged={}
    for rel in RULES:
        path=folia/JAVA/rel
        staged[path]=patch(rel,path.read_text(encoding='utf-8'))
    helpers=sorted(HELPERS.rglob('*.java'))
    if len(helpers)!=3:raise ValueError('Exactly three FIELD-R12 native helpers required')
    for source in helpers:
        dest=folia/JAVA/source.relative_to(HELPERS)
        content=source.read_text(encoding='utf-8')
        if dest.exists() and dest.read_text(encoding='utf-8')!=content:
            raise ValueError('Conflicting FIELD-R12 helper; materialize a clean upstream tree: '+str(dest))
        staged[dest]=content
    return staged

class InstallerTests(unittest.TestCase):
    def test_all_inspected_anchors_are_unique_or_explicitly_counted(self):
        for rel,rules in RULES.items():
            fixture='\n'.join(before*count for before,after,count in rules)
            out=transform(rel,fixture)
            for before,after,count in rules:self.assertIn(after,out)
    def test_changed_or_missing_inputs_fail_closed(self):
        for rel in RULES:
            with self.assertRaises(ValueError):patch(rel,'class Uninspected {}')
    def test_missing_anchor_never_passes(self):
        for rel,rules in RULES.items():
            for i,(before,after,count) in enumerate(rules):
                fixture='\n'.join(old*n for j,(old,new,n) in enumerate(rules) if i!=j)
                with self.assertRaises(ValueError):transform(rel,fixture)
    def test_no_ore_mask_reroll(self):
        rules=RULES['net/minecraft/world/level/chunk/NeverOverworldOreScarcityFieldR10.java']
        self.assertEqual(len(rules),2)
        self.assertTrue(all('SALT' not in old and 'mix(' not in old for old,new,n in rules))
        self.assertIn('KEEP_PERCENT = 25',rules[1][1])
    def test_tree_decision_precedes_decorators(self):
        self.assertIn('acceptAndCommit()',str(RULES['net/minecraft/world/level/levelgen/feature/TreeFeature.java']))
        self.assertNotIn('Fallen',str(RULES['net/minecraft/world/level/levelgen/feature/TreeFeature.java']))
    def test_origin_height_guard_precedes_vanilla_random_and_writes(self):
        rel='net/minecraft/world/level/levelgen/feature/TreeFeature.java'
        first=RULES[rel][0]
        fixture=first[0]+'\n        RandomSource random = context.random();\n'
        patched=fixture.replace(first[0],first[1])
        self.assertIn('begin(context.level(), context.origin())',patched)
        self.assertLess(patched.index('canStart()'),patched.index('context.random()'))
        self.assertIn('if (!neverTreeProposalR12.canStart()) return false;',patched)
    def test_fallen_tree_has_no_standing_height_gate(self):
        rules=RULES['net/minecraft/world/level/levelgen/feature/FallenTreeFeature.java']
        self.assertTrue(all('canStart' not in new and 'acceptStandingTree' not in new for old,new,n in rules))
        self.assertEqual(sum(new.count('fallenPosition') for old,new,n in rules),2)
    def test_both_flood_paths_exclude_the_persisted_mine_mask(self):
        for name in ['NeverOverworldFlood.java','NeverOverworldFloodBoundaryR11.java']:
            self.assertIn('protectedCell',str(RULES['net/minecraft/world/level/chunk/'+name]))
    def test_mine_recording_does_not_restore_village_reclamation(self):
        text=str(RULES['net/minecraft/world/level/levelgen/structure/StructureStart.java'])
        self.assertIn('VILLAGE-NOFILL-R1',text)
        self.assertNotIn('NeverOverworldVillageReclamation.apply',text)
    def test_missing_source_preflight_is_read_only(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            before=list(root.iterdir())
            with self.assertRaises(FileNotFoundError):prepare(root)
            self.assertEqual(list(root.iterdir()),before)

def self_test():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(InstallerTests))
    if not result.wasSuccessful():raise SystemExit(1)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folia',nargs='?',type=Path)
    p.add_argument('--self-test',action='store_true')
    p.add_argument('--check-only',action='store_true')
    a=p.parse_args()
    if a.self_test:self_test();return
    if a.folia is None:p.error('materialized Folia directory required')
    staged=prepare(a.folia.resolve())
    if a.check_only:
        print('[FIELD-R12] exact-source preflight OK; no writes');return
    for path,text in staged.items():
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
    print('[FIELD-R12] standing origin >= ocean-2 (Y126); 25% final ore retain; per-piece dry mines installed')

if __name__=='__main__':main()
