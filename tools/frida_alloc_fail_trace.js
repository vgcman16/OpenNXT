const moduleName = "rs2client.exe";
const targetOffset = 0x791660;
const minimumLoggedBytes = 0x1000;

function safeHex(value) {
    try {
        return "0x" + value.toString(16);
    } catch (error) {
        return "<hex-error>";
    }
}

function argToString(value) {
    try {
        return value.toString();
    } catch (error) {
        return "<arg-error>";
    }
}

function formatRelative(address) {
    try {
        return moduleName + "+0x" + address.sub(moduleObject.base).toString(16);
    } catch (error) {
        return DebugSymbol.fromAddress(address).toString();
    }
}

function formatBacktrace(context) {
    try {
        return Thread.backtrace(context, Backtracer.ACCURATE)
            .slice(0, 12)
            .map((address) => formatRelative(address))
            .join(" | ");
    } catch (error) {
        return "<backtrace-error> " + error;
    }
}

const moduleObject = Process.getModuleByName(moduleName);
const targetAddress = moduleObject.base.add(targetOffset);

console.log("[alloc-fail] hooking " + moduleName + " +" + safeHex(targetOffset) + " @ " + targetAddress);

Interceptor.attach(targetAddress, {
    onEnter(args) {
        const requestedBytes32 = args[0].toUInt32();
        if (requestedBytes32 < minimumLoggedBytes) {
            return;
        }

        const requestedBytes = argToString(args[0]);
        const alignment = argToString(args[1]);
        console.log(
            "[alloc-fail] requestedBytes=" +
                requestedBytes +
                " alignment=" +
                alignment +
                " backtrace=" +
                formatBacktrace(this.context)
        );
    }
});
