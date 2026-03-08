# Build 946 Protocol Workspace

This directory is the in-repo workspace for RS3 build `946`.

## Status

- Live RS3 client build confirmed: `946`
- Ghidra import of the `win64` client succeeded
- The legacy `RS3NXTRefactorer` script does not yet complete on build `946`
- `serverProtSizes.toml` is now extracted from the live client
- `clientProtSizes.toml` is now extracted from the live client
- `sizeDiffReport.md` now compares `919` vs `946` size tables to produce the first naming shortlist
- The 2026 client registers `217` contiguous server packets through a new direct registrar at `FUN_140301280`
- The 2026 client registers `130` contiguous client packets through a direct registrar at `FUN_140301100`

Current script breakpoints observed during headless runs:

- The legacy packet naming walk does not yet match the new `946` packet object layout
- The legacy `SendPing` anchor is no longer required for packet size extraction, but packet naming still needs new heuristics

## Inputs

- Client binary:
  `data/clients/946/win64/original/rs2client.exe`

## Goal

Populate the following once the Ghidra heuristics are updated for build `946`:

- `clientProtNames.toml`
- `serverProtNames.toml`
- `clientProt/*.txt`
- `serverProt/*.txt`

## Notes

The current repository can download and patch the live `946` client and cache. The server remains pinned to
supported protocol data until packet names and handler mappings are recovered for build `946`.

Regenerate the size-based shortlist with:

`python scripts/protocol_size_diff.py --source-build 919 --target-build 946 --out data/prot/946/sizeDiffReport.md`
