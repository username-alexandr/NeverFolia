package net.minecraft.world.level.levelgen.placement;

/** Do not turn an R11 metadata validation failure into a successful empty chunk.
 * Ordinary unrelated I/O failures keep the upstream behavior; this is not a new
 * global corruption recovery policy. The chunk scheduler receives the error.
 */
public final class NeverNetherLoadGuardR11 {
    private NeverNetherLoadGuardR11() { }
    public static final class InvalidSubstrate extends IllegalStateException {
        public InvalidSubstrate(String message) { super(message); }
    }
    public static boolean persistenceFailure(Throwable error) {
        for(int depth=0;error!=null&&depth<16;depth++) {
            if(error instanceof InvalidSubstrate)return true;
            Throwable cause=error.getCause();if(cause==error)break;error=cause;
        }
        return false;
    }
}
