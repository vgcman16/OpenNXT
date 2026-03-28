# 946 Plateau Diff

- Status: `ok`
- Left window: `959546:965703`
- Right window: `1081680:1082691`
- Left scene state: `reference-tables-only`
- Right scene state: `reference-tables-only`
- Top hypothesis: `asset-delivery stall`

## Hypotheses

- `asset-delivery stall` score=`75` Right plateau remained in `reference-tables-only`, which still points at asset-delivery or capture timing.
- `post-bootstrap state divergence` score=`55` The plateau event counts diverge materially even though both sessions reached interfaces.
- `scene settle stall` score=`25` Runtime traces do not show a strong post-asset settle difference yet.

## Client Opcode Delta

- Missing in right: `{'113': 3, '17': 1, '28': 1, '48': 1}`
- Extra in right: `{}`

## Server Opcode Delta

- Missing in right: `{'131': 218, '42': 1848}`
- Extra in right: `{}`
