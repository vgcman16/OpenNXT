#@category OpenNXT

from ghidra.program.model.symbol import RefType


TARGETS = [
    0x140B99108,  # secur32.dll
    0x140B9AE90,  # schannel: SNI or certificate check failed: %s
    0x140B9B0D8,  # SSL: public key does not match pinned public key!
    0x140B9B768,  # schannel: CertGetCertificateChain failed: %s
    0x140B9B798,  # schannel: server certificate name verification failed
    0x140B9B6D0,  # sha256//
]


def describe_ref(ref):
    from_addr = ref.getFromAddress()
    to_addr = ref.getToAddress()
    ref_type = ref.getReferenceType()
    function = getFunctionContaining(from_addr)
    function_name = function.getName() if function else "<no-function>"
    print(
        "  from=%s to=%s type=%s function=%s" %
        (from_addr, to_addr, ref_type, function_name)
    )


def main():
    print("Program: %s" % currentProgram.getName())
    print("Image base: %s" % currentProgram.getImageBase())
    print("")

    for value in TARGETS:
        addr = toAddr(value)
        print("Target %s" % addr)
        data = getDataAt(addr)
        if data:
            print("  data=%s" % data)

        refs = list(getReferencesTo(addr))
        if not refs:
            print("  refs=<none>")
            print("")
            continue

        for ref in refs:
            describe_ref(ref)
        print("")


if __name__ == "__main__":
    main()
