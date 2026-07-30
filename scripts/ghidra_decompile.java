// ghidra_decompile.java — Ghidra headless post-script (Java GhidraScript): dump C
// pseudocode for the most interesting functions to a text file, so ctf-file / ctf-eval /
// ctf-writeup can read a native binary's logic without opening the GUI.
//
// Java is used (not Python) because Ghidra 12.x ships no bundled Jython — Python scripts
// require PyGhidra; a Java GhidraScript is compiled on the fly and always available.
//
// Invoked by:  analyzeHeadless <proj> tmp -import <bin> \
//                 -scriptPath scripts -postScript ghidra_decompile.java <outfile>
//@category CTF
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Program;
import ghidra.util.task.ConsoleTaskMonitor;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.List;

public class ghidra_decompile extends GhidraScript {
    private int score(Function f) {
        String n = f.getName();
        if (n.equals("main") || n.equals("entry") || n.equals("_start")) return 0;
        if (f.isThunk()) return 5;
        if (n.startsWith("FUN_")) return 3;
        return 2;
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outpath = (args.length > 0) ? args[0] : "decompiled.txt";
        Program prog = getCurrentProgram();
        DecompInterface ifc = new DecompInterface();
        ifc.openProgram(prog);
        FunctionManager fm = prog.getFunctionManager();
        List<Function> funcs = new ArrayList<>();
        for (Function f : fm.getFunctions(true)) funcs.add(f);
        funcs.sort((a, b) -> Integer.compare(score(a), score(b)));

        StringBuilder out = new StringBuilder();
        out.append("// Ghidra decompilation of " + prog.getName()
                   + " (" + fm.getFunctionCount() + " functions)\n");
        int count = 0, MAX = 40;
        ConsoleTaskMonitor mon = new ConsoleTaskMonitor();
        for (Function f : funcs) {
            if (count >= MAX) break;
            if (f.isExternal()) continue;
            try {
                DecompileResults res = ifc.decompileFunction(f, 60, mon);
                if (res != null && res.decompileCompleted()) {
                    String code = res.getDecompiledFunction().getC();
                    out.append("\n// ==== " + f.getName() + " @ " + f.getEntryPoint()
                               + " ====\n" + code);
                    count++;
                }
            } catch (Exception e) {
                // skip a function that won't decompile
            }
        }
        FileWriter fw = new FileWriter(outpath);
        fw.write(out.toString());
        fw.close();
        println("[ghidra_decompile] wrote " + count + " functions to " + outpath);
    }
}
