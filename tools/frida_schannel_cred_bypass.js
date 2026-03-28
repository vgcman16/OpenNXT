function formatHex(value) {
    return "0x" + (value >>> 0).toString(16);
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

function readUtf16Maybe(address) {
    if (address.isNull()) {
        return "<null>";
    }
    try {
        return Memory.readUtf16String(address);
    } catch (error) {
        return "<unreadable-utf16>";
    }
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

const SCHANNEL_CRED_OFFSETS = {
    dwVersion: 0x0,
    grbitEnabledProtocols: 0x38,
    dwFlags: 0x48,
    dwCredFormat: 0x4c
};

const CLEAR_REVOCATION_FLAGS = 0x00000100 | 0x00000200 | 0x00000400;
const ADD_IGNORE_FLAGS = 0x00000800 | 0x00001000;

function patchCredFlags(authDataPtr, apiName) {
    if (authDataPtr.isNull()) {
        console.log("[cred] " + apiName + " authData=<null>");
        return;
    }

    try {
        const version = Memory.readU32(authDataPtr.add(SCHANNEL_CRED_OFFSETS.dwVersion));
        const protocols = Memory.readU32(authDataPtr.add(SCHANNEL_CRED_OFFSETS.grbitEnabledProtocols));
        const originalFlags = Memory.readU32(authDataPtr.add(SCHANNEL_CRED_OFFSETS.dwFlags));
        const credFormat = Memory.readU32(authDataPtr.add(SCHANNEL_CRED_OFFSETS.dwCredFormat));
        const updatedFlags = ((originalFlags & (~CLEAR_REVOCATION_FLAGS >>> 0)) | ADD_IGNORE_FLAGS) >>> 0;

        if (updatedFlags !== originalFlags) {
            Memory.writeU32(authDataPtr.add(SCHANNEL_CRED_OFFSETS.dwFlags), updatedFlags);
        }

        console.log(
            "[cred] " +
                apiName +
                " version=" +
                formatHex(version) +
                " protocols=" +
                formatHex(protocols) +
                " flags=" +
                formatHex(originalFlags) +
                " -> " +
                formatHex(updatedFlags) +
                " credFormat=" +
                formatHex(credFormat)
        );
    } catch (error) {
        console.log("[cred] " + apiName + " failed to patch authData: " + error);
    }
}

function installAcquireHook(name, reader) {
    const address = findExport(["secur32.dll", "sspicli.dll"], name);
    if (address === null) {
        console.log("[cred] missing export " + name);
        return;
    }

    console.log("[cred] hooking " + name + " @ " + address);
    Interceptor.attach(address, {
        onEnter(args) {
            this.apiName = name;
            this.principal = reader(args[0]);
            this.packageName = reader(args[1]);
            this.credentialUse = args[2].toUInt32();
            this.authData = args[4];
            patchCredFlags(this.authData, name);
        },
        onLeave(retval) {
            console.log(
                "[cred] " +
                    this.apiName +
                    " leave status=" +
                    formatHex(retval.toUInt32()) +
                    " principal=" +
                    this.principal +
                    " package=" +
                    this.packageName +
                    " credentialUse=" +
                    formatHex(this.credentialUse)
            );
        }
    });
}

function installInitializeHook(name, reader) {
    const address = findExport(["secur32.dll", "sspicli.dll"], name);
    if (address === null) {
        console.log("[cred] missing export " + name);
        return;
    }

    console.log("[cred] hooking " + name + " @ " + address);
    Interceptor.attach(address, {
        onEnter(args) {
            this.target = reader(args[2]);
        },
        onLeave(retval) {
            console.log("[cred] " + name + " leave status=" + formatHex(retval.toUInt32()) + " target=" + this.target);
        }
    });
}

installAcquireHook("AcquireCredentialsHandleW", readUtf16Maybe);
installAcquireHook("AcquireCredentialsHandleA", readAnsiMaybe);
installInitializeHook("InitializeSecurityContextA", readAnsiMaybe);
