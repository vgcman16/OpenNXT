function formatStatus(value) {
    const signed = value.toInt32();
    const unsigned = signed >>> 0;
    return "0x" + unsigned.toString(16).padStart(8, "0") + " (" + signed + ")";
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

function safeReadAnsi(ptrValue) {
    if (ptrValue.isNull()) {
        return "<null>";
    }
    try {
        return Memory.readCString(ptrValue);
    } catch (error) {
        return "<unreadable-ansi>";
    }
}

function safeReadWide(ptrValue) {
    if (ptrValue.isNull()) {
        return "<null>";
    }
    try {
        return Memory.readUtf16String(ptrValue);
    } catch (error) {
        return "<unreadable-wide>";
    }
}

function installInitializeSecurityContextHook(name, reader) {
    const address = findExport(["secur32.dll", "sspicli.dll"], name);
    if (address === null) {
        console.log("[schannel] missing export " + name);
        return;
    }

    console.log("[schannel] hooking " + name + " @ " + address);
    Interceptor.attach(address, {
        onEnter(args) {
            this.name = name;
            this.targetName = reader(args[2]);
            this.contextReq = args[3].toUInt32();
            this.inputDesc = args[6];
            this.outputDesc = args[9];
            console.log(
                "[schannel] " +
                    name +
                    " enter target=" +
                    this.targetName +
                    " req=0x" +
                    this.contextReq.toString(16) +
                    " input=" +
                    this.inputDesc +
                    " output=" +
                    this.outputDesc
            );
        },
        onLeave(retval) {
            console.log(
                "[schannel] " +
                    this.name +
                    " leave status=" +
                    formatStatus(retval) +
                    " target=" +
                    this.targetName
            );
        }
    });
}

function installCertPolicyHook() {
    const address = findExport(["crypt32.dll"], "CertVerifyCertificateChainPolicy");
    if (address === null) {
        console.log("[schannel] missing export CertVerifyCertificateChainPolicy");
        return;
    }

    console.log("[schannel] hooking CertVerifyCertificateChainPolicy @ " + address);
    Interceptor.attach(address, {
        onEnter(args) {
            this.policyOid = safeReadAnsi(args[0]);
            console.log("[schannel] CertVerifyCertificateChainPolicy enter policy=" + this.policyOid);
        },
        onLeave(retval) {
            console.log(
                "[schannel] CertVerifyCertificateChainPolicy leave status=" +
                    formatStatus(retval) +
                    " policy=" +
                    this.policyOid
            );
        }
    });
}

installInitializeSecurityContextHook("InitializeSecurityContextW", safeReadWide);
installInitializeSecurityContextHook("InitializeSecurityContextA", safeReadAnsi);
installCertPolicyHook();
