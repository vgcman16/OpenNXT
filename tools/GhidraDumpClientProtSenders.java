import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.Symbol;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class GhidraDumpClientProtSenders extends GhidraScript {
    private static final int[] TARGET_OPCODES = {
        0, 17, 28, 48, 50, 82, 83, 85, 113
    };

    private void decompile(Function function) throws Exception {
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            DecompileResults results = decompiler.decompileFunction(function, 30, monitor);
            if (!results.decompileCompleted()) {
                println("    <decompile failed> " + results.getErrorMessage());
                return;
            }
            println(results.getDecompiledFunction().getC());
        } finally {
            decompiler.dispose();
        }
    }

    private void inspectOpcode(int opcode) throws Exception {
        String symbolName = "ClientProtOP_" + opcode;
        List<Symbol> symbols = getSymbols(symbolName, null);
        println("============================================================");
        println("SYMBOL " + symbolName);
        if (symbols.isEmpty()) {
            println("  <not found>");
            return;
        }

        for (Symbol symbol : symbols) {
            Address address = symbol.getAddress();
            println("  address=" + address);

            Reference[] refs = getReferencesTo(address);
            if (refs.length == 0) {
                println("  refs=<none>");
                continue;
            }

            Map<String, Function> uniqueFunctions = new LinkedHashMap<>();
            for (Reference ref : refs) {
                Function function = getFunctionContaining(ref.getFromAddress());
                String functionLabel = function == null
                    ? "<no-function>@" + ref.getFromAddress()
                    : function.getName() + "@" + function.getEntryPoint();
                println(
                    "  ref from=" + ref.getFromAddress() +
                        " type=" + ref.getReferenceType() +
                        " function=" + functionLabel
                );
                if (function != null) {
                    uniqueFunctions.putIfAbsent(functionLabel, function);
                }
            }

            int decompiled = 0;
            for (Map.Entry<String, Function> entry : uniqueFunctions.entrySet()) {
                if (decompiled >= 4) {
                    break;
                }
                println("  ----------------------------------------------------------");
                println("  DECOMPILE " + entry.getKey());
                decompile(entry.getValue());
                decompiled++;
            }
        }
    }

    @Override
    protected void run() throws Exception {
        println("PROGRAM " + currentProgram.getName());
        println("IMAGE_BASE " + currentProgram.getImageBase());
        for (int opcode : TARGET_OPCODES) {
            inspectOpcode(opcode);
        }
    }
}
