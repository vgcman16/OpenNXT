# Opcode 113 Verdict

- Build: `946`
- Status: `ok`
- Verdict: `state-report`
- Confidence: `medium`

## Address Validation

- Requested sender: `FUN_1400ced60` `1400ced60`
- Resolved containing function: `FUN_1400cec80` `1400cec80`
- Caller lookup: source=`requested-address` target=`FUN_1400ced60` `1400ced60`

## Trigger Assessment

- Timer driven: `yes`
- Focus/window-state driven: `unknown`
- World-handshake driven: `unlikely`

## Payload

- Observed packet size: `4`
- Writer pattern: `zero-prefix + little-endian ushort + transformed state byte`

## Live Correlation

- Observed count: `3`
- Stage counts: `{'interfaces': 2, 'rebuild': 1}`
- Unique previews: `['00000043', '000000db', '000000e7']`
- Unique tail bytes: `['0x43', '0xdb', '0xe7']`
- Zero-prefixed samples: `3`
- Matches payload hypothesis: `True`

## Rationale

- Containing function sets a +10000 timer threshold before enabling the send flag.
- Function toggles a dedicated pending flag/state pair at +0x77c0/+0x77b8.
- Timer gating points to periodic state transmission rather than a single world-ready transition.
- The live burst is dominated by interfaces-stage repeats after rebuild.
- The live burst looks periodic and state-bearing rather than like a single handshake gate.

## Next Lead

- Opcode `116` `server`
- Reason: Opcode 116 already exports a usable active-sub shape and becomes the next missing UI-path lead once 113 is ruled out.

## Notes

- Requested sender address 1400ced60 resolves inside FUN_1400cec80 @ 1400cec80.
- Caller proof remains thin; the verdict relies primarily on the containing-function body plus live packet values.
- Opcode 67 remains out of scope here; it is still a separate parser/export recovery task.
