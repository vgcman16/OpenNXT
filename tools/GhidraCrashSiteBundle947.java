import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class GhidraCrashSiteBundle947 extends GhidraScript {
    private static final int DEFAULT_INSTRUCTIONS_BEFORE = 12;
    private static final int DEFAULT_INSTRUCTIONS_AFTER = 24;

    private String quote(String value) {
        if (value == null) {
            return "null";
        }

        StringBuilder escaped = new StringBuilder();
        escaped.append('"');
        for (int index = 0; index < value.length(); index++) {
            char current = value.charAt(index);
            switch (current) {
                case '\\':
                    escaped.append("\\\\");
                    break;
                case '"':
                    escaped.append("\\\"");
                    break;
                case '\b':
                    escaped.append("\\b");
                    break;
                case '\f':
                    escaped.append("\\f");
                    break;
                case '\n':
                    escaped.append("\\n");
                    break;
                case '\r':
                    escaped.append("\\r");
                    break;
                case '\t':
                    escaped.append("\\t");
                    break;
                default:
                    if (current < 0x20) {
                        escaped.append(String.format("\\u%04x", (int) current));
                    } else {
                        escaped.append(current);
                    }
                    break;
            }
        }
        escaped.append('"');
        return escaped.toString();
    }

    private String toJson(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String) {
            return quote((String) value);
        }
        if (value instanceof Number || value instanceof Boolean) {
            return value.toString();
        }
        if (value instanceof Map<?, ?>) {
            StringBuilder builder = new StringBuilder();
            builder.append('{');
            boolean first = true;
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
                if (!first) {
                    builder.append(',');
                }
                first = false;
                builder.append(quote(String.valueOf(entry.getKey())));
                builder.append(':');
                builder.append(toJson(entry.getValue()));
            }
            builder.append('}');
            return builder.toString();
        }
        if (value instanceof Iterable<?>) {
            StringBuilder builder = new StringBuilder();
            builder.append('[');
            boolean first = true;
            for (Object item : (Iterable<?>) value) {
                if (!first) {
                    builder.append(',');
                }
                first = false;
                builder.append(toJson(item));
            }
            builder.append(']');
            return builder.toString();
        }
        return quote(String.valueOf(value));
    }

    private Map<String, Object> referenceInfo(Reference reference) {
        Map<String, Object> info = new LinkedHashMap<>();
        Function caller = getFunctionContaining(reference.getFromAddress());
        info.put("fromAddress", reference.getFromAddress().toString());
        info.put("toAddress", reference.getToAddress().toString());
        info.put("referenceType", reference.getReferenceType().toString());
        info.put("callerName", caller != null ? caller.getName() : null);
        info.put("callerEntry", caller != null ? caller.getEntryPoint().toString() : null);
        return info;
    }

    private List<Map<String, Object>> collectReferences(Address address) {
        List<Map<String, Object>> refs = new ArrayList<>();
        for (Reference reference : getReferencesTo(address)) {
            refs.add(referenceInfo(reference));
        }
        return refs;
    }

    private boolean instructionContains(Instruction instruction, Address target) {
        if (instruction == null || target == null) {
            return false;
        }
        return instruction.getAddress().compareTo(target) <= 0 && instruction.getMaxAddress().compareTo(target) >= 0;
    }

    private List<Map<String, Object>> collectInstructionWindow(Address target, int beforeCount, int afterCount) {
        List<Map<String, Object>> instructions = new ArrayList<>();
        Instruction center = getInstructionContaining(target);
        if (center == null) {
            center = getInstructionBefore(target);
        }
        if (center == null) {
            return instructions;
        }

        List<Instruction> before = new ArrayList<>();
        Instruction cursor = center;
        for (int count = 0; cursor != null && count < beforeCount; count++) {
            before.add(cursor);
            cursor = getInstructionBefore(cursor);
        }
        Collections.reverse(before);

        List<Instruction> combined = new ArrayList<>(before);
        Instruction afterCursor = getInstructionAfter(center);
        for (int count = 0; afterCursor != null && count < afterCount; count++) {
            combined.add(afterCursor);
            afterCursor = getInstructionAfter(afterCursor);
        }

        for (Instruction instruction : combined) {
            Map<String, Object> info = new LinkedHashMap<>();
            info.put("address", instruction.getAddress().toString());
            info.put("maxAddress", instruction.getMaxAddress().toString());
            info.put("mnemonic", instruction.getMnemonicString());
            info.put("operand", instruction.getDefaultOperandRepresentation(0));
            info.put("text", instruction.toString());
            info.put("containsTarget", instructionContains(instruction, target));
            instructions.add(info);
        }
        return instructions;
    }

    private Map<String, Object> summarizeAddress(Address address) throws Exception {
        Map<String, Object> info = new LinkedHashMap<>();
        info.put("requestedAddress", address.toString());

        Instruction instruction = getInstructionContaining(address);
        if (instruction == null) {
            instruction = getInstructionBefore(address);
        }
        info.put("instructionAddress", instruction != null ? instruction.getAddress().toString() : null);
        info.put("instructionText", instruction != null ? instruction.toString() : null);

        Function function = getFunctionContaining(address);
        if (function != null) {
            info.put("functionName", function.getName());
            info.put("functionEntry", function.getEntryPoint().toString());
            info.put("functionBody", function.getBody().toString());
            info.put("functionCallers", collectReferences(function.getEntryPoint()));
            info.put("decompiledC", decompileFunction(function));
        } else {
            info.put("functionName", null);
            info.put("functionEntry", null);
            info.put("functionBody", null);
            info.put("functionCallers", Collections.emptyList());
            info.put("decompiledC", "");
        }

        info.put("referencesToAddress", collectReferences(address));
        info.put("instructionWindow", collectInstructionWindow(address, 4, 8));
        return info;
    }

    private String decompileFunction(Function function) throws Exception {
        if (function == null) {
            return "";
        }
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            DecompileResults results = decompiler.decompileFunction(function, 60, monitor);
            if (!results.decompileCompleted()) {
                return "<decompile failed> " + results.getErrorMessage();
            }
            return results.getDecompiledFunction().getC();
        } finally {
            decompiler.dispose();
        }
    }

    private int parseIntArg(String[] args, int index, int defaultValue) {
        if (args.length <= index) {
            return defaultValue;
        }
        try {
            return Integer.decode(args[index]);
        } catch (NumberFormatException ignored) {
            return defaultValue;
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            throw new IllegalArgumentException(
                "Usage: GhidraCrashSiteBundle947.java <output-json-path> <target-address> [instructions-before] [instructions-after] [extra-address ...]"
            );
        }

        String outputJsonPath = args[0];
        Address targetAddress = toAddr(args[1]);
        int instructionsBefore = parseIntArg(args, 2, DEFAULT_INSTRUCTIONS_BEFORE);
        int instructionsAfter = parseIntArg(args, 3, DEFAULT_INSTRUCTIONS_AFTER);
        List<Address> extraAddresses = new ArrayList<>();
        for (int index = 4; index < args.length; index++) {
            extraAddresses.add(toAddr(args[index]));
        }

        Function function = getFunctionContaining(targetAddress);

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("programName", currentProgram.getName());
        payload.put("imageBase", currentProgram.getImageBase().toString());
        payload.put("targetAddress", targetAddress.toString());
        payload.put("instructionsBefore", instructionsBefore);
        payload.put("instructionsAfter", instructionsAfter);
        payload.put("targetReferences", collectReferences(targetAddress));
        payload.put("instructionWindow", collectInstructionWindow(targetAddress, instructionsBefore, instructionsAfter));
        List<Map<String, Object>> inspectedAddresses = new ArrayList<>();
        for (Address extraAddress : extraAddresses) {
            inspectedAddresses.add(summarizeAddress(extraAddress));
        }
        payload.put("inspectedAddresses", inspectedAddresses);

        if (function != null) {
            Map<String, Object> functionInfo = new LinkedHashMap<>();
            functionInfo.put("name", function.getName());
            functionInfo.put("entryPoint", function.getEntryPoint().toString());
            functionInfo.put("body", function.getBody().toString());
            functionInfo.put("callers", collectReferences(function.getEntryPoint()));
            functionInfo.put("decompiledC", decompileFunction(function));
            payload.put("function", functionInfo);
        } else {
            payload.put("function", null);
        }

        Path outputPath = Path.of(outputJsonPath);
        Files.createDirectories(outputPath.getParent());
        Files.writeString(outputPath, toJson(payload), StandardCharsets.UTF_8);
        println("WROTE " + outputPath);
        println("TARGET " + targetAddress);
        if (function != null) {
            println("FUNCTION " + function.getName() + " @ " + function.getEntryPoint());
        } else {
            println("FUNCTION <not found>");
        }
    }
}
