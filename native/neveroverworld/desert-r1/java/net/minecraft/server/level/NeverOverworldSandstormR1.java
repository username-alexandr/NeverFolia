package net.minecraft.server.level;

import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.biome.Biomes;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.phys.Vec3;

/**
 * DESERT-R1 deterministic sandstorms. No overheating mechanic.
 *
 * <p>Storms are derived from world seed + time, require open sky in the desert,
 * add a small wind impulse and spawn local dust/ash only for the affected
 * player. Riding, swimming, spectator, creative-flight and elytra movement are
 * not modified.</p>
 */
public final class NeverOverworldSandstormR1 {
    static final long CYCLE_TICKS = 12_000L;
    static final int STORM_CHANCE_PERCENT = 35;
    static final int STORM_DURATION = 2_400;
    static final int MIN_DRY_SURFACE_Y = 129;
    private static final long SALT = 0x53414E4453544F52L;

    private NeverOverworldSandstormR1() {}

    public static void tick(final ServerPlayer player) {
        final ServerLevel level = player.level();
        if (!level.dimension().equals(Level.OVERWORLD) || player.isSpectator()) return;

        final long gameTime = level.getGameTime();
        final Storm storm = storm(level.getSeed(), gameTime);
        if (!storm.active()) return;

        final BlockPos pos = player.blockPosition();
        if (!level.getBiome(pos).is(Biomes.DESERT)
            || !level.canSeeSky(pos)
            || !isDryDesertSurface(level.getHeight(Heightmap.Types.OCEAN_FLOOR, pos.getX(), pos.getZ()))) {
            return;
        }

        if ((gameTime & 1L) == 0L
            && !player.isPassenger()
            && !player.isInWater()
            && !player.isFallFlying()
            && !player.getAbilities().flying) {
            final Vec3 velocity = player.getDeltaMovement();
            final double impulse = windImpulse(velocity.x, velocity.z, storm.windX(), storm.windZ());
            player.push(storm.windX() * impulse, 0.0D, storm.windZ() * impulse);
        }

        if ((gameTime & 3L) == 0L) {
            final double sourceX = player.getX() - storm.windX() * 5.0D;
            final double sourceZ = player.getZ() - storm.windZ() * 5.0D;
            level.sendParticles(
                player, ParticleTypes.DUST_PLUME, false, false,
                sourceX, player.getEyeY(), sourceZ,
                42, 5.5D, 2.4D, 5.5D, 0.08D
            );
            level.sendParticles(
                player, ParticleTypes.ASH, false, false,
                player.getX(), player.getEyeY() + 0.5D, player.getZ(),
                22, 6.5D, 3.0D, 6.5D, 0.02D
            );
        }
    }

    static boolean isDryDesertSurface(final int firstAvailableOceanFloorY) {
        return firstAvailableOceanFloorY >= MIN_DRY_SURFACE_Y;
    }

    static double windImpulse(
        final double velocityX,
        final double velocityZ,
        final double windX,
        final double windZ
    ) {
        final double dot = velocityX * windX + velocityZ * windZ;
        return dot < -0.02D ? 0.0060D : (dot > 0.02D ? 0.0032D : 0.0044D);
    }

    static Storm storm(final long seed, final long gameTime) {
        final long cycle = Math.floorDiv(gameTime, CYCLE_TICKS);
        final long phase = Math.floorMod(gameTime, CYCLE_TICKS);
        final long h = mix(seed ^ SALT ^ cycle * 0x9E3779B97F4A7C15L);
        final boolean enabled = Math.floorMod(h, 100L) < STORM_CHANCE_PERCENT;
        final int start = 800 + (int)Math.floorMod(mix(h ^ 0xC2B2AE3D27D4EB4FL), 2_800L);
        final boolean active = enabled && phase >= start && phase < start + STORM_DURATION;

        final long directionHash = mix(h ^ 0xD6E8FEB86659FD93L);
        final double angle = Math.floorMod(directionHash, 4096L) * (Math.PI * 2.0D / 4096.0D);
        return new Storm(active, Math.cos(angle), Math.sin(angle), cycle, start);
    }

    static long mix(long n) {
        n = (n ^ (n >>> 30)) * 0xBF58476D1CE4E5B9L;
        n = (n ^ (n >>> 27)) * 0x94D049BB133111EBL;
        return n ^ (n >>> 31);
    }

    record Storm(boolean active, double windX, double windZ, long cycle, int startTick) {}
}
