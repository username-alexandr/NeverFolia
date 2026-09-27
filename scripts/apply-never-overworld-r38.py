#!/usr/bin/env python3
"""R38 generated-source patch: ecology write barrier, exact mount, complete read-only audit."""
from pathlib import Path
import argparse
ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('folia-server/src/minecraft/java')
CHUNK=JAVA/'net/minecraft/world/level/chunk'
METHOD = '''    /** R38: target the mount we created, never a nearest-entity selector. */
    private static int mountDrowned(CommandSourceStack source, Entity self) throws CommandSyntaxException {
        if (!(self instanceof net.minecraft.world.entity.monster.zombie.Drowned drowned)) throw UNSAFE.create();
        if (!drowned.isAlive() || drowned.isPassenger()) return 0;
        var level = source.getLevel();
        if (!TickThread.isTickThreadFor(level, drowned.position())) throw UNSAFE.create();
        var type = BuiltInRegistries.ENTITY_TYPE.getOptional(
            Identifier.fromNamespaceAndPath("minecraft", "zombie_nautilus")).orElseThrow(MISSING::create);
        if (!(type.create(level, EntitySpawnReason.COMMAND) instanceof net.minecraft.world.entity.Mob mount)) throw MISSING.create();
        mount.snapTo(drowned.position());
        mount.setPersistenceRequired();
        if (!level.addFreshEntity(mount, org.bukkit.event.entity.CreatureSpawnEvent.SpawnReason.CUSTOM)) return 0;
        // Preserve the source /ride contract, including cancellable mount events.
        // If attachment is denied, remove only our own newly created mount.
        if (!drowned.startRiding(mount, true, true)) {
            mount.discard(org.bukkit.event.entity.EntityRemoveEvent.Cause.TRANSFORMATION);
            return 0;
        }
        // The controller is consumed only after a successful mount.
        drowned.setItemSlot(EquipmentSlot.SADDLE, ItemStack.EMPTY);
        return 1;
    }
'''

def replace(text,old,new):
    if new in text:
        if text.count(new)!=1: raise ValueError('duplicate R38 hook')
        return text
    if text.count(old)!=1:raise ValueError('R38 source drift: '+old[:120])
    return text.replace(old,new,1)

def prepare(folia):
    staged={}
    for name in ('NeverOverworldWaterAuditR38.java','NeverOverworldWaterPolicyR38.java'):
        staged[folia/CHUNK/name]=(ROOT/'native/overworld-r38'/name).read_text()
    path=folia/CHUNK/'NeverOverworldEcologyR13.java';text=path.read_text()
    old='                        final BlockState replacement =\n                            y <= OCEAN_Y && waterContact\n                                ? Blocks.WATER.defaultBlockState()\n                                : Blocks.AIR.defaultBlockState();'
    new='                        // R38: vegetation cleanup must obey the same ocean floor barrier.\n                        final BlockState replacement = NeverOverworldWaterPolicyR38.afterPlantRemoval(chunk, pos, state, y <= OCEAN_Y && waterContact);'
    staged[path]=replace(text,old,new)
    path=folia/CHUNK/'NeverOverworldEcologyR15.java'
    staged[path]=replace(path.read_text(),'chunk.setBlockState(pos,replacementAfterRemoval(waterContact),0);++changed;','chunk.setBlockState(pos,NeverOverworldWaterPolicyR38.afterPlantRemoval(chunk,pos,s,waterContact),0);++changed; // R38_ECOLOGY_BARRIER')
    path=folia/CHUNK/'NeverOverworldSubmergedRemnants.java';text=path.read_text()
    text=replace(text,'                            chunk.setBlockState(pos, Blocks.WATER.defaultBlockState(), 0);',
        '                            chunk.setBlockState(pos, NeverOverworldWaterPolicyR38.afterPlantRemoval(chunk, pos, state, true), 0); // R38_REMNANT_BARRIER')
    text=replace(text,'        if (touchesWater(chunk, pos, minX, minZ)) return Blocks.WATER.defaultBlockState();',
        '        if (touchesWater(chunk, pos, minX, minZ)) return NeverOverworldWaterPolicyR38.afterPlantRemoval(chunk, pos, chunk.getBlockState(pos), true); // R38_FROZEN_BARRIER')
    staged[path]=text
    path=folia/JAVA/'ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask.java';text=path.read_text()
    anchor='            net.minecraft.world.level.chunk.NeverOverworldFlood.apply(task.world, task.fromChunk);'
    anchor=next(line for line in text.splitlines() if line.strip()==anchor.strip())
    indent=anchor[:len(anchor)-len(anchor.lstrip())]
    text=replace(text,anchor,indent+'final var waterAuditR38 = net.minecraft.world.level.chunk.NeverOverworldWaterAuditR38.begin(task.world, task.fromChunk);\n'+anchor)
    anchor=next(line for line in text.splitlines() if line.strip()=='net.minecraft.world.level.chunk.NeverOverworldEcologyR15.cleanup(task.world, task.fromChunk);')
    text=replace(text,anchor,anchor+'\n'+indent+'net.minecraft.world.level.chunk.NeverOverworldWaterAuditR38.end(task.world, task.fromChunk, waterAuditR38);')
    staged[path]=text
    path=folia/JAVA/'net/minecraft/server/commands/NeverNetherDntCommands.java';text=path.read_text()
    text=replace(text,'"clear_saddle", "sprint_on"','"clear_saddle", "drowned_mount", "sprint_on"')
    text=replace(text,'            case "clear_fireball_owner" -> clearOwner(source, self);','            case "drowned_mount" -> mountDrowned(source, self);\n            case "clear_fireball_owner" -> clearOwner(source, self);')
    text=replace(text,'    private static void requireTrader(',METHOD+'    private static void requireTrader(')
    staged[path]=text
    return staged

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folia',type=Path);p.add_argument('--check-only',action='store_true');a=p.parse_args()
    staged=prepare(a.folia)
    if a.check_only:
        if any(not path.exists() or path.read_text()!=value for path,value in staged.items()):raise ValueError('R38 final source differs')
    else:
        for path,value in staged.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)
    print('[FIELD-R38] ecology, exact drowned mount and opt-in complete-chain water audit OK')
if __name__=='__main__':main()
