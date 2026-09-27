package cc.neverland.client;

import net.minecraft.core.Holder;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.tags.TagKey;
import net.minecraft.world.item.enchantment.Enchantment;

/** Display policy only. No registry, effect, item or loot mutation. */
public final class EnchantmentVisibility {
    private static final TagKey<Enchantment> TECHNICAL=TagKey.create(Registries.ENCHANTMENT,
        Identifier.fromNamespaceAndPath("nova_structures","non_survival_enchants"));
    // The exact R39.3 source omitted this otherwise identical controller from its tag.
    private static final ResourceKey<Enchantment> RAVAGER=ResourceKey.create(Registries.ENCHANTMENT,
        Identifier.fromNamespaceAndPath("nova_structures","jockey/spawn_ravager_jockey"));
    private EnchantmentVisibility() {}
    public static boolean show(Holder<Enchantment> enchantment) {
        return !enchantment.is(TECHNICAL)&&!enchantment.is(RAVAGER);
    }
}
