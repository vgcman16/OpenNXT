# 946 Sender Analysis

- Status: `partial`
- Selected opcodes: `[113, 0, 83, 48, 17]`

## Opcode 0 `UNRESOLVED`

- Status: `clean`
- Error kind: ``
- Sender: `FUN_14014dba0` `14014dba0`
- Resolved function: `FUN_14014dab0` `14014dab0`
- Caller lookup: source=`requested-address` target=`FUN_14014dba0` `14014dba0`
- Size/family: `-2` ``
- Clone: strategy=`disposable-project-clone` cleanup=`cleaned`
- Packet-size evidence: count=`2` stages=`{'interfaces': 1, 'rebuild': 1}`
- Symbol references: `{'functions': ['FUN_14001bab0', 'FUN_14002cf60', 'FUN_140032200', 'FUN_140032530', 'FUN_1400adab0', 'FUN_1400d8e30', 'FUN_14014dab0', 'FUN_14016bfb0', 'FUN_14016d5f0', 'FUN_140791660'], 'data': ['DAT_140e55a70', 'DAT_140e55a90', 'DAT_140e56f00', 'DAT_140e56f10', 'DAT_140e56f14']}`
- Decomp snippet:
  - `  }`
  - `  return;`
  - `}`
  - ` (GhidraScript)`
  - `WARNING: A terminally deprecated method in sun.misc.Unsafe has been called`
  - `WARNING: sun.misc.Unsafe::staticFieldOffset has been called by org.apache.felix.framework.util.SecureAction (file:/C:/Users/Demon/Tools/ghidra/ghidra_12.0.4_PUBLIC/Ghidra/Features/Base/lib/org.apache.felix.framework-7.0.5.jar)`
  - `WARNING: Please consider reporting this to the maintainers of class org.apache.felix.framework.util.SecureAction`
  - `WARNING: sun.misc.Unsafe::staticFieldOffset will be removed in a future release`

## Opcode 17 `UNRESOLVED`

- Status: `missing-sender`
- Error kind: `missing-sender`
- Sender: `unknown` ``
- Caller lookup: source=`requested-address` target=`unknown` ``
- Size/family: `-1` ``
- Clone: strategy=`disposable-project-clone` cleanup=`not-used`
- Packet-size evidence: count=`4` stages=`{'interfaces': 4}`

## Opcode 48 `UNRESOLVED`

- Status: `missing-sender`
- Error kind: `missing-sender`
- Sender: `unknown` ``
- Caller lookup: source=`requested-address` target=`unknown` ``
- Size/family: `-1` ``
- Clone: strategy=`disposable-project-clone` cleanup=`not-used`
- Packet-size evidence: count=`5` stages=`{'interfaces': 4, 'rebuild': 1}`

## Opcode 83 `UNRESOLVED`

- Status: `clean`
- Error kind: ``
- Sender: `FUN_1400cfcb0` `1400cfcb0`
- Resolved function: `FUN_1400cfbd0` `1400cfbd0`
- Caller lookup: source=`requested-address` target=`FUN_1400cfcb0` `1400cfcb0`
- Size/family: `1` ``
- Clone: strategy=`disposable-project-clone` cleanup=`cleaned`
- Packet-size evidence: count=`3` stages=`{'interfaces': 3}`
- Named tokens: `['GetFocus']`
- Symbol references: `{'functions': ['FUN_1400adab0', 'FUN_1400cfbd0', 'FUN_1400d0540', 'FUN_140144d10', 'FUN_1403d35b0', 'FUN_1403d8170', 'FUN_140791660', 'FUN_1407a4820', 'FUN_1407b77b0'], 'data': ['DAT_140e570d0', 'DAT_140e570d4', 'DAT_140e571e0', 'DAT_140e571e4', 'DAT_140e57240', 'DAT_140e57244', 'DAT_140e57440', 'DAT_140e57444']}`
- Decomp snippet:
  - `  }`
  - `  return;`
  - `}`
  - ` (GhidraScript)`
  - `WARNING: A terminally deprecated method in sun.misc.Unsafe has been called`
  - `WARNING: sun.misc.Unsafe::staticFieldOffset has been called by org.apache.felix.framework.util.SecureAction (file:/C:/Users/Demon/Tools/ghidra/ghidra_12.0.4_PUBLIC/Ghidra/Features/Base/lib/org.apache.felix.framework-7.0.5.jar)`
  - `WARNING: Please consider reporting this to the maintainers of class org.apache.felix.framework.util.SecureAction`
  - `WARNING: sun.misc.Unsafe::staticFieldOffset will be removed in a future release`

## Opcode 113 `UNRESOLVED`

- Status: `clean`
- Error kind: ``
- Sender: `FUN_1400ced60` `1400ced60`
- Resolved function: `FUN_1400cec80` `1400cec80`
- Caller lookup: source=`requested-address` target=`FUN_1400ced60` `1400ced60`
- Size/family: `4` ``
- Clone: strategy=`disposable-project-clone` cleanup=`cleaned`
- Packet-size evidence: count=`3` stages=`{'interfaces': 2, 'rebuild': 1}`
- Symbol references: `{'functions': ['FUN_1400adab0', 'FUN_1400bbb90', 'FUN_1400cec80', 'FUN_1406742c0', 'FUN_140674330', 'FUN_140791660'], 'data': ['DAT_140e55a90', 'DAT_140e57620', 'DAT_140e57624', 'DAT_140e73e68']}`
- Decomp snippet:
  - `  }`
  - `  return;`
  - `}`
  - ` (GhidraScript)`
  - `WARNING: A terminally deprecated method in sun.misc.Unsafe has been called`
  - `WARNING: sun.misc.Unsafe::staticFieldOffset has been called by org.apache.felix.framework.util.SecureAction (file:/C:/Users/Demon/Tools/ghidra/ghidra_12.0.4_PUBLIC/Ghidra/Features/Base/lib/org.apache.felix.framework-7.0.5.jar)`
  - `WARNING: Please consider reporting this to the maintainers of class org.apache.felix.framework.util.SecureAction`
  - `WARNING: sun.misc.Unsafe::staticFieldOffset will be removed in a future release`
