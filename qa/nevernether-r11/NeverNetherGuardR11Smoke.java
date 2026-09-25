import net.minecraft.world.level.levelgen.placement.NeverNetherLoadGuardR11;
/** Typed-error classifier, not an end-to-end chunk I/O failure test. */
public final class NeverNetherGuardR11Smoke {
    public static void main(String[] args) {
        if(!NeverNetherLoadGuardR11.persistenceFailure(new NeverNetherLoadGuardR11.InvalidSubstrate("test")))throw new AssertionError("direct");
        if(!NeverNetherLoadGuardR11.persistenceFailure(new RuntimeException(new NeverNetherLoadGuardR11.InvalidSubstrate("wrapped"))))throw new AssertionError("wrapped");
        if(NeverNetherLoadGuardR11.persistenceFailure(new java.io.IOException("ordinary")))throw new AssertionError("unrelated");
        if(NeverNetherLoadGuardR11.persistenceFailure(null))throw new AssertionError("null");
        System.out.println("NN-R11 load guard: 4 classifier checks passed; not a server failure test");
    }
}
