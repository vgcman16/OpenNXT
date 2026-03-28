import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;

public class GhidraSecureWorldRefs extends GhidraScript {
    private void dumpRefs(String label, String addressText) {
        Address address = toAddr(addressText);
        ReferenceManager refs = currentProgram.getReferenceManager();

        println("TARGET " + label + " @ " + address);

        ReferenceIterator references = refs.getReferencesTo(address);
        if (!references.hasNext()) {
            println("  <no references>");
            return;
        }

        while (references.hasNext()) {
            Reference ref = references.next();
            Address from = ref.getFromAddress();
            Function function = getFunctionContaining(from);
            String functionLabel = function == null
                ? "<no function>"
                : function.getName() + " @ " + function.getEntryPoint();

            println(
                "  from=" + from +
                    " type=" + ref.getReferenceType() +
                    " opIndex=" + ref.getOperandIndex() +
                    " function=" + functionLabel
            );
        }
    }

    @Override
    protected void run() throws Exception {
        dumpRefs("secur32.dll", "0x140b97908");
        dumpRefs("InitSecurityInterfaceA", "0x140b97918");
        dumpRefs("security.dll", "0x140b97930");
        dumpRefs("AcquireCredentialsHandle", "0x140b98468");
        dumpRefs("DecryptMessage", "0x140b984c0");
        dumpRefs("EncryptMessage", "0x140b986b8");
        dumpRefs("sha256//", "0x140b99ed0");
        dumpRefs("CertGetCertificateChain failed", "0x140b99f68");
        dumpRefs("server certificate name verification failed", "0x140b99f98");
        dumpRefs("public key mismatch", "0x140b998d8");
        dumpRefs("sni or certificate check failed", "0x140b99690");
        dumpRefs("FUN_14064b270 entry", "0x14064b270");
        dumpRefs("FUN_14064b600 entry", "0x14064b600");
        dumpRefs("FUN_14063d680 entry", "0x14063d680");
        dumpRefs("CertGetCertificateChain thunk", "0x1408000f0");
        dumpRefs("CertFreeCertificateChain thunk", "0x1408000e0");
        dumpRefs("CryptQueryObject thunk", "0x1408000d0");
        dumpRefs("CertGetNameStringA thunk", "0x1408000c0");
        dumpRefs("GetProcAddress thunk", "0x140800730");
        dumpRefs("LoadLibraryA thunk", "0x140800780");
        dumpRefs("LoadLibraryExA thunk", "0x1408006e8");
    }
}
