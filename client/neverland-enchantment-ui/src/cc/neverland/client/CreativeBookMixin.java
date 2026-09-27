package cc.neverland.client;

import java.util.stream.Stream;
import net.minecraft.core.Holder;
import net.minecraft.core.HolderLookup;
import net.minecraft.world.item.CreativeModeTabs;
import net.minecraft.world.item.enchantment.Enchantment;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

/** Vanilla 26.2 builds creative books client-side from every registry entry.
 * Filtering server-side CreativeModeTabs would not fix a remote client's menu.
 */
@Mixin(value=CreativeModeTabs.class,remap=false)
public abstract class CreativeBookMixin {
    @Redirect(method="generateEnchantmentBookTypesOnlyMaxLevel",at=@At(value="INVOKE",
        target="Lnet/minecraft/core/HolderLookup;listElements()Ljava/util/stream/Stream;"),require=1,allow=1,remap=false)
    private static Stream<Holder.Reference<Enchantment>> neverland$maxBooks(HolderLookup<Enchantment> lookup) {
        return lookup.listElements().filter(EnchantmentVisibility::show);
    }
    @Redirect(method="generateEnchantmentBookTypesAllLevels",at=@At(value="INVOKE",
        target="Lnet/minecraft/core/HolderLookup;listElements()Ljava/util/stream/Stream;"),require=1,allow=1,remap=false)
    private static Stream<Holder.Reference<Enchantment>> neverland$searchBooks(HolderLookup<Enchantment> lookup) {
        return lookup.listElements().filter(EnchantmentVisibility::show);
    }
}
