import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

public class GhidraInspectAddresses extends GhidraScript {
    private static final String[] TARGETS = {
        "0x1400cae03",
        "0x140703fd2",
        "0x140727fc6",
        "0x140791702"
    };

    private void printRefs(Function function) {
        println("CALLERS:");
        Reference[] refs = getReferencesTo(function.getEntryPoint());
        if (refs.length == 0) {
            println("  <none>");
            return;
        }

        for (Reference ref : refs) {
            Function caller = getFunctionContaining(ref.getFromAddress());
            String callerName = caller != null ? caller.getName() : "<no-function>";
            println("  " + ref.getFromAddress() + " -> " + function.getEntryPoint() + " caller=" + callerName);
        }
    }

    private void decompileFunction(Function function) throws Exception {
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            DecompileResults results = decompiler.decompileFunction(function, 60, monitor);
            if (!results.decompileCompleted()) {
                println("DECOMPILE FAILED: " + results.getErrorMessage());
                return;
            }

            println("DECOMPILE:");
            println(results.getDecompiledFunction().getC());
        } finally {
            decompiler.dispose();
        }
    }

    private void inspectAddress(String addressText) throws Exception {
        Address address = toAddr(addressText);
        Function function = getFunctionContaining(address);
        println("============================================================");
        println("TARGET " + address);
        if (function == null) {
            println("FUNCTION <not found>");
            return;
        }

        println("FUNCTION " + function.getName() + " @ " + function.getEntryPoint());
        println("BODY " + function.getBody());
        printRefs(function);
        decompileFunction(function);
    }

    @Override
    protected void run() throws Exception {
        println("PROGRAM " + currentProgram.getName());
        println("IMAGE_BASE " + currentProgram.getImageBase());
        for (String target : TARGETS) {
            inspectAddress(target);
        }
    }
}
