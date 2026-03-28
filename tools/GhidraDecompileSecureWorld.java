import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class GhidraDecompileSecureWorld extends GhidraScript {
    private void dumpFunction(String addressText) throws Exception {
        Address address = toAddr(addressText);
        Function function = getFunctionContaining(address);
        if (function == null) {
            println("FUNCTION " + address + " <not found>");
            return;
        }

        println("FUNCTION " + function.getName() + " @ " + function.getEntryPoint());

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);

        try {
            DecompileResults results = decompiler.decompileFunction(function, 60, monitor);
            if (!results.decompileCompleted()) {
                println("  <decompile failed> " + results.getErrorMessage());
                return;
            }

            println(results.getDecompiledFunction().getC());
        } finally {
            decompiler.dispose();
        }
    }

    @Override
    protected void run() throws Exception {
        dumpFunction("0x140649440");
        dumpFunction("0x14064b270");
        dumpFunction("0x14064b600");
        dumpFunction("0x14063d680");
        dumpFunction("0x1406510e0");
        dumpFunction("0x14062c0f0");
    }
}
