# OpenNXT by vgcman16

Maintained fork of the RS3 NXT framework originally published as [Techdaan/OpenNXT](https://github.com/Techdaan/OpenNXT).
This fork keeps the project buildable on a modern toolchain while preserving the existing code and data layout.

## Repository

- Current fork: [vgcman16/OpenNXT](https://github.com/vgcman16/OpenNXT)
- Upstream source: [Techdaan/OpenNXT](https://github.com/Techdaan/OpenNXT)

## Support

Project tracking and support for this fork live in [GitHub Issues](https://github.com/vgcman16/OpenNXT/issues).

## Tooling

One of the goals of this project is to keep the required tools built into the repository. That includes the client
downloader, launcher patcher, cache downloader, and related workflow helpers.

Tools can be executed with `run-tool <tool-name> [--help]`.

New tools can be added by creating a class in `com.opennxt.tools.impl` that extends `com.opennxt.tools.Tool`. The
tool registry is populated automatically through classpath scanning.

## Build

This fork currently builds with Gradle 9.4, Kotlin 2.3, and Java 25.

```bash
./gradlew build
```

Compatibility note: the internal package namespace remains `com.opennxt` in this fork to avoid a large breaking
refactor.

## Updating

To move the project to a newer RS3 build:

1. Download the latest clients using `run-tool client-downloader`.
2. Download the latest cache using `run-tool cache-downloader`.
3. Patch the latest clients using `run-tool client-patcher`.
4. Update the `build` field in `./data/config/server.toml`.

If the target version is not yet supported, or you are contributing to packet/protocol support, also do the following:

1. In `com.opennxt.net.login.LoginEncoder`, replace `RS3_MODULUS` with the `old login` key printed by the patcher.
2. Create `./data/prot/[new version]/`, replacing `[new version]` with the server build number.
3. Open the client in Ghidra and run the [Ghidra NXT Auto Refactoring Script](https://github.com/Techdaan/rs3nxt-ghidra-scripts). Background on that workflow is also available in the linked [Rune-Server release thread](https://www.rune-server.ee/runescape-development/rs-503-client-server/downloads/698604-nxt-win64-ghidra-refactoring-script.html).
4. Use the script output to populate the files in `./data/prot/[version]/*.toml`. The tool does not emit `clientProtNames`, so those still need to be filled in manually.
5. Populate packet fields using the files in `./data/prot/[version]/[(client/server)prot]`.

## Setup

1. Generate your server RSA keys with `run-tool rsa-key-generator`.
2. Download the RS clients with `run-tool client-downloader`.

   Warning: the latest clients are not guaranteed to match this repository. Keep the repository build and client build aligned.

3. Put the original launcher in `./data/launcers/win/original.exe` from `C:\Program Files\Jagex\RuneScape Launcher\RuneScape.exe`.
4. Create `./data/config/server.toml` with at least:

   ```toml
   hostname = "127.0.0.1"
   configUrl = "http://127.0.0.1/jav_config.ws?binaryType=2"
   ```

   `configUrl` is the URL the launcher should use to fetch `jav_config.ws`.
   `hostname` is the address your server binds to.

5. Patch the client and launcher with `run-tool client-patcher`.
6. Download the latest compatible cache with `run-tool cache-downloader`.
7. Build and run the server once your cache, launcher, and protocol data are in place.
