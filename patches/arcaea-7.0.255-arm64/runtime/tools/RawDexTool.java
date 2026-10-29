import java.io.File;
import com.android.tools.smali.baksmali.Baksmali;
import com.android.tools.smali.baksmali.BaksmaliOptions;
import com.android.tools.smali.dexlib2.DexFileFactory;
import com.android.tools.smali.dexlib2.Opcodes;
import com.android.tools.smali.smali.Smali;
import com.android.tools.smali.smali.SmaliOptions;

public class RawDexTool {
    public static void main(String[] args) throws Exception {
        if (args.length != 3) throw new IllegalArgumentException("disassemble|assemble input output");
        boolean ok;
        if (args[0].equals("disassemble")) {
            ok = Baksmali.disassembleDexFile(DexFileFactory.loadDexFile(args[1], Opcodes.getDefault()),
                    new File(args[2]), 1, new BaksmaliOptions());
        } else if (args[0].equals("assemble")) {
            SmaliOptions options = new SmaliOptions();
            options.jobs = 1;
            options.apiLevel = 24;
            options.outputDexFile = args[2];
            ok = Smali.assemble(options, args[1]);
        } else throw new IllegalArgumentException(args[0]);
        if (!ok) throw new IllegalStateException("DEX operation failed");
    }
}
