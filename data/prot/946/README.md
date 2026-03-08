# Build 946 Protocol Workspace

This directory is the in-repo workspace for RS3 build `946`.

## Status

- Live RS3 client build confirmed: `946`
- Ghidra import of the `win64` client succeeded
- The legacy `RS3NXTRefactorer` script does not yet complete on build `946`
- `serverProtSizes.toml` is now extracted from the live client
- The 2026 client registers `217` contiguous server packets through a new direct registrar at `FUN_140301280`

Current script breakpoints observed during headless runs:

- `SendPing not found (Obtained from ServerProt decoding)` during `ClientProt` discovery
- The legacy packet naming walk does not yet match the new `946` packet object layout

## Inputs

- Client binary:
  `data/clients/946/win64/original/rs2client.exe`

## Goal

Populate the following once the Ghidra heuristics are updated for build `946`:

- `clientProtNames.toml`
- `clientProtSizes.toml`
- `serverProtNames.toml`
- `clientProt/*.txt`
- `serverProt/*.txt`

## Notes

The current repository can download and patch the live `946` client and cache. The server remains pinned to
supported protocol data until packet names and client protocol data are recovered for build `946`.
