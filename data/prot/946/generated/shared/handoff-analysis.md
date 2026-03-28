# 946 Handoff Analysis

- Build: `946`
- Status: `partial`
- Session window: `172294` -> `181650`
- Session stages: `appearance, login-response, pipeline-switch, rebuild, stats, default-state, interfaces`

## Top Targets

- `opcode 0` score=`20` class=`handled-report` reason=`class=handled-report; stages=2; sender=FUN_14014dba0`
  next: Treat opcode 0 as handled bootstrap traffic unless a later behavioral diff proves it still needs semantics.
- `PLAYER_INFO` score=`8` class=`unknown` reason=`initial appearance burst is followed by sustained 3-byte PLAYER_INFO frames`
  next: Verify why PLAYER_INFO collapses to repeated 3-byte frames after the initial appearance burst.
- `opcode 83` score=`8` class=`state-report` reason=`class=state-report; stages=1; sender=FUN_1400cfcb0`
  next: Treat opcode 83 as a likely state-report until a caller proves it blocks the handoff.
- `opcode 48` score=`2` class=`state-report` reason=`class=state-report; stages=2`
  next: Treat opcode 48 as a likely state-report until a caller proves it blocks the handoff.
- `opcode 17` score=`-8` class=`state-report` reason=`class=state-report; stages=1`
  next: Treat opcode 17 as a likely state-report until a caller proves it blocks the handoff.

## PLAYER_INFO

- Opcode: `42`
- First large send: `64`
- Repeated 3-byte sends: `3040`
- Size range: `3` -> `64`
- Stage distribution: `{'interfaces': 3067}`
- Appearance burst present: `True`
- Needs review: `True`
- Next action: Verify why PLAYER_INFO collapses to repeated 3-byte frames after the initial appearance burst.

## Suspects

### Opcode 0 `UNRESOLVED`

- Coverage status: `unresolved`
- Candidate status: `draft`
- Suspect class: `handled-report`
- Size: `-2` family=``
- Sender: `FUN_14014dba0`
- Decomp log: `clean` `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\sender-aid\opcode-0\decompile.stdout.log`
- Stage counts: `{'interfaces': 1, 'rebuild': 1}`
- Runtime markers: `{'handled': 2}`
- First/last stage: `rebuild` -> `interfaces`
- Next action: Treat opcode 0 as handled bootstrap traffic unless a later behavioral diff proves it still needs semantics.
- Sample previews:
  - line `172303` stage=`rebuild` bytes=`1291` preview=`010b2f2936ffff0b30264445350b31ff3728270b32ffffffff0b33232446380b`
  - line `172389` stage=`interfaces` bytes=`139` preview=`010b2f29ffffff1ff500ff00001ff8001602121ff91363d0001b34ffffffff0c`
- Decomp snippet:
  - `  }`
  - `  return;`
  - `}`
  - ` (GhidraScript)`
  - `WARNING: A terminally deprecated method in sun.misc.Unsafe has been called`
  - `WARNING: sun.misc.Unsafe::staticFieldOffset has been called by org.apache.felix.framework.util.SecureAction (file:/C:/Users/Demon/Tools/ghidra/ghidra_12.0.4_PUBLIC/Ghidra/Features/Base/lib/org.apache.felix.framework-7.0.5.jar)`
  - `WARNING: Please consider reporting this to the maintainers of class org.apache.felix.framework.util.SecureAction`
  - `WARNING: sun.misc.Unsafe::staticFieldOffset will be removed in a future release`

### Opcode 17 `UNRESOLVED`

- Coverage status: `unresolved`
- Candidate status: `draft`
- Suspect class: `state-report`
- Size: `-1` family=``
- Sender: `unknown`
- Decomp log: `missing-sender` `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\sender-aid\opcode-17\decompile.stdout.log`
- Stage counts: `{'interfaces': 6}`
- Runtime markers: `{'ignored': 4}`
- First/last stage: `interfaces` -> `interfaces`
- Next action: Treat opcode 17 as a likely state-report until a caller proves it blocks the handoff.
- Sample previews:
  - line `172512` stage=`interfaces` bytes=`9` preview=`0000ffff012c029100`
  - line `172541` stage=`interfaces` bytes=`101` preview=`080708a20008a30008e30008e20008e50008e30009240008e40008e50008a400`
  - line `173095` stage=`interfaces` bytes=`9` preview=`0900f354019b02cb00`

### Opcode 48 `UNRESOLVED`

- Coverage status: `unresolved`
- Candidate status: `draft`
- Suspect class: `state-report`
- Size: `-1` family=``
- Sender: `unknown`
- Decomp log: `missing-sender` `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\sender-aid\opcode-48\decompile.stdout.log`
- Stage counts: `{'interfaces': 6, 'rebuild': 1}`
- Runtime markers: `{'ignored': 4}`
- First/last stage: `rebuild` -> `interfaces`
- Next action: Treat opcode 48 as a likely state-report until a caller proves it blocks the handoff.
- Sample previews:
  - line `172302` stage=`rebuild` bytes=`93` preview=`090cffff00ab04d68004ac804a9380209e805b8a00a80167805c8601e305e0e1`
  - line `172513` stage=`interfaces` bytes=`12` preview=`0701e439012c029108a208a3`
  - line `172542` stage=`interfaces` bytes=`46` preview=`0b0a09a509a8092409a9096808e6096a096b08a4092a08e70862086308620822`

### Opcode 83 `UNRESOLVED`

- Coverage status: `unresolved`
- Candidate status: `draft`
- Suspect class: `state-report`
- Size: `1` family=``
- Sender: `FUN_1400cfcb0`
- Decomp log: `clean` `C:\Users\Demon\Documents\New project\OpenNXT\data\prot\946\generated\shared\sender-aid\opcode-83\decompile.stdout.log`
- Stage counts: `{'interfaces': 3}`
- Runtime markers: `{'ignored': 3}`
- First/last stage: `interfaces` -> `interfaces`
- Next action: Treat opcode 83 as a likely state-report until a caller proves it blocks the handoff.
- Sample previews:
  - line `173570` stage=`interfaces` bytes=`1` preview=`00`
  - line `174713` stage=`interfaces` bytes=`1` preview=`01`
  - line `174730` stage=`interfaces` bytes=`1` preview=`00`
- Decomp snippet:
  - `  }`
  - `  return;`
  - `}`
  - ` (GhidraScript)`
  - `WARNING: A terminally deprecated method in sun.misc.Unsafe has been called`
  - `WARNING: sun.misc.Unsafe::staticFieldOffset has been called by org.apache.felix.framework.util.SecureAction (file:/C:/Users/Demon/Tools/ghidra/ghidra_12.0.4_PUBLIC/Ghidra/Features/Base/lib/org.apache.felix.framework-7.0.5.jar)`
  - `WARNING: Please consider reporting this to the maintainers of class org.apache.felix.framework.util.SecureAction`
  - `WARNING: sun.misc.Unsafe::staticFieldOffset will be removed in a future release`

## Notes

- Sender-aid output was used to normalize mixed-encoding decomp evidence.
- One or more suspects currently look like periodic/state-report traffic rather than a direct handoff blocker.
