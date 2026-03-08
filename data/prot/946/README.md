# Build 946 Protocol Workspace

This directory is the in-repo workspace for RS3 build `946`.

## Status

- Live RS3 client build confirmed: `946`
- Ghidra import of the `win64` client succeeded
- The legacy `RS3NXTRefactorer` script does not yet complete on build `946`

Current script breakpoints observed during headless runs:

- `More than 1 CALL in jag::Isaac::Init`
- `What @ 140ec0ce0` during `ServerProt` recursion
- `SendPing not found (Obtained from ServerProt decoding)` during `ClientProt` discovery

## Inputs

- Client binary:
  `data/clients/946/win64/original/rs2client.exe`

## Goal

Populate the following once the Ghidra heuristics are updated for build `946`:

- `clientProtNames.toml`
- `clientProtSizes.toml`
- `serverProtNames.toml`
- `serverProtSizes.toml`
- `clientProt/*.txt`
- `serverProt/*.txt`

## Notes

The current repository can download and patch the live `946` client and cache, but the server remains pinned to
supported protocol data until this directory is fully populated.
