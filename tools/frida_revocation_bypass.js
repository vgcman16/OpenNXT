function formatStatus(value) {
    const signed = value.toInt32();
    const unsigned = signed >>> 0;
    return "0x" + unsigned.toString(16).padStart(8, "0") + " (" + signed + ")";
}

function readAnsiMaybe(address) {
    if (address.isNull()) {
        return "<null>";
    }
    try {
        return Memory.readCString(address);
    } catch (error) {
        return "<unreadable-ansi>";
    }
}

function readHexPreview(address, length) {
    if (address.isNull()) {
        return "<null>";
    }
    try {
        return hexdump(address, {
            offset: 0,
            length: length,
            header: false,
            ansi: false
        }).trim().replace(/\s+/g, " ");
    } catch (error) {
        return "<unreadable-bytes>";
    }
}

function findExport(moduleNames, exportName) {
    for (const moduleName of moduleNames) {
        const moduleObject = Process.findModuleByName(moduleName);
        if (moduleObject === null) {
            continue;
        }
        try {
            return moduleObject.getExportByName(exportName);
        } catch (error) {
        }
    }
    return null;
}

const REVOCATION_FLAGS = 0x10000000 | 0x20000000 | 0x40000000;

function installChainHook() {
    const address = findExport(["crypt32.dll"], "CertGetCertificateChain");
    if (address === null) {
        console.log("[revocation] missing export CertGetCertificateChain");
        return;
    }

    console.log("[revocation] hooking CertGetCertificateChain @ " + address);
    Interceptor.attach(address, {
        onEnter(args) {
            this.originalFlags = args[5].toUInt32();
            this.updatedFlags = this.originalFlags & (~REVOCATION_FLAGS >>> 0);
            if (this.updatedFlags !== this.originalFlags) {
                args[5] = ptr(this.updatedFlags >>> 0);
            }
            console.log(
                "[revocation] CertGetCertificateChain flags=" +
                    "0x" + this.originalFlags.toString(16) +
                    " -> 0x" + this.updatedFlags.toString(16)
            );
        },
        onLeave(retval) {
            console.log(
                "[revocation] CertGetCertificateChain result=" +
                    formatStatus(retval) +
                    " flags=0x" + this.updatedFlags.toString(16)
            );
        }
    });
}

function installInitializeSecurityContextHook(name) {
    const address = findExport(["secur32.dll", "sspicli.dll"], name);
    if (address === null) {
        console.log("[revocation] missing export " + name);
        return;
    }

    console.log("[revocation] hooking " + name + " @ " + address);
    Interceptor.attach(address, {
        onEnter(args) {
            this.targetPtr = args[2];
            this.target = readAnsiMaybe(this.targetPtr);
            this.targetPreview = readHexPreview(this.targetPtr, 32);
        },
        onLeave(retval) {
            console.log(
                "[revocation] " +
                    name +
                    " status=" +
                    formatStatus(retval) +
                    " target=" +
                    this.target +
                    " targetPtr=" +
                    this.targetPtr +
                    " bytes=" +
                    this.targetPreview
            );
        }
    });
}

installChainHook();
installInitializeSecurityContextHook("InitializeSecurityContextA");
