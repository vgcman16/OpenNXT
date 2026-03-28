from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


WORKSPACE = Path(r"C:\Users\Demon\Documents\New project\OpenNXT")
PROT_DIR = WORKSPACE / "data" / "prot" / "946"
PHASE1_DIR = PROT_DIR / "generated" / "phase1"
PHASE2_DIR = PROT_DIR / "generated" / "phase2"
OUTPUT_DIR = PROT_DIR / "generated" / "phase3"
SHARED_DIR = PROT_DIR / "generated" / "shared"


@dataclass
class Candidate:
    side: str
    opcode: int
    size: int
    suggested_name: str
    confidence: str
    source: str
    family_label: str
    family_source: str
    exact_candidate_names: list[str]
    exact_candidate_source: str
    evidence: dict
    confidence_score: float
    score_breakdown: dict[str, float]
    cross_build: dict


def parse_names_toml(path: Path) -> dict[int, str]:
    text = path.read_text(encoding="utf-8")
    return {int(opcode): name for opcode, name in re.findall(r"^(\d+)\s*=\s*\"([^\"]+)\"", text, re.M)}


def parse_sizes_toml(path: Path) -> dict[int, int]:
    text = path.read_text(encoding="utf-8")
    return {int(opcode): int(size) for opcode, size in re.findall(r"^(\d+)\s*=\s*(-?\d+)", text, re.M)}


def write_names_toml(path: Path, names: dict[int, str], comment: str) -> None:
    lines = [f"# {comment}", "", "[values]"]
    for opcode in sorted(names):
        lines.append(f'{opcode} = "{names[opcode]}"')
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_cross_build_scaffold() -> dict[tuple[str, int], dict]:
    path = SHARED_DIR / "cross-build-index.json"
    if not path.exists():
        return {}
    payload = load_json(path)
    entries = payload.get("packets", []) if isinstance(payload, dict) else []
    result: dict[tuple[str, int], dict] = {}
    for entry in entries:
        side = entry.get("side", "")
        opcode = entry.get("opcode")
        if side and isinstance(opcode, int):
            result[(side, opcode)] = entry.get(
                "crossBuild",
                {
                    "matchedFromBuild": None,
                    "matchedOpcode": None,
                    "matchedPacketName": "",
                    "matchingBasis": "",
                    "signatureHash": entry.get("signatureHash", ""),
                    "confidence": 0.0,
                },
            )
    return result


def parse_legacy_names(path: Path, size_path: Path) -> list[tuple[int, str, int | None]]:
    names = parse_names_toml(path)
    sizes = parse_sizes_toml(size_path)
    return [(opcode, name, sizes.get(opcode)) for opcode, name in sorted(names.items())]


def classify_client_family(name: str) -> str:
    if name.startswith("OPPLAYER"):
        return "OPPLAYER"
    if name.startswith("OPNPC"):
        return "OPNPC"
    if name.startswith("OPLOC"):
        return "OPLOC"
    if name.startswith("OPOBJ"):
        return "OPOBJ"
    if name.startswith("IF_BUTTON"):
        return "IF_BUTTON"
    if name.startswith("MESSAGE_"):
        return "MESSAGE"
    if name.startswith("RESUME_"):
        return "RESUME"
    if name in {"WALK", "MINIMAP_WALK"}:
        return "WALK"
    if name == "MAP_BUILD_COMPLETE":
        return "MAP_BUILD_COMPLETE"
    if name == "NO_TIMEOUT":
        return "NO_TIMEOUT"
    if name == "CLIENT_CHEAT":
        return "CLIENT_CHEAT"
    return name


def classify_server_family(name: str) -> str:
    if name.startswith("IF_"):
        return "IF"
    if (
        name.startswith("MAP_")
        or name.startswith("OBJ_")
        or name.startswith("LOC_")
        or name.startswith("UPDATE_ZONE_")
    ):
        return "WORLD"
    if name in {"PLAYER_INFO", "NPC_INFO"}:
        return "SYNC"
    if (
        name.startswith("VARP_")
        or name.startswith("CLIENT_SETVARC")
        or name in {"UPDATE_STAT", "RESET_CLIENT_VARCACHE"}
    ):
        return "VAR"
    if name in {"NO_TIMEOUT", "SERVER_TICK_END", "REBUILD_NORMAL"}:
        return "SESSION"
    if name == "RUNCLIENTSCRIPT":
        return "SCRIPT"
    return name


def infer_family_label(side: str, name: str) -> str:
    if not name:
        return ""
    return classify_client_family(name) if side == "client" else classify_server_family(name)


LEGACY_SERVER_NAMES = parse_legacy_names(
    PROT_DIR.parent / "919" / "serverProtNames.toml",
    PROT_DIR.parent / "919" / "serverProtSizes.toml",
)


def dominant_family(labels: list[str]) -> str:
    labels = [label for label in labels if label]
    if not labels:
        return ""
    counts = Counter(labels)
    label, count = counts.most_common(1)[0]
    if len(counts) == 1:
        return label
    if count / len(labels) >= 0.8:
        return label
    return ""


def build_client_sender_family_map(
    confirmed: dict[int, str], sender_rows: dict[int, dict]
) -> dict[str, str]:
    labels_by_sender: dict[str, list[str]] = {}
    for opcode, row in sender_rows.items():
        sender = row.get("primarySenderName", "")
        if not sender or opcode not in confirmed:
            continue
        labels_by_sender.setdefault(sender, []).append(infer_family_label("client", confirmed[opcode]))

    inferred = {
        sender: dominant_family(labels)
        for sender, labels in labels_by_sender.items()
        if dominant_family(labels)
    }
    inferred.update(
        {
            "FUN_14008d840": "RAW_TEXT",
            "FUN_14008db20": "RAW_TEXT",
            "FUN_140099e30": "RAW_TEXT",
            "FUN_1400e4cd0": "WALK",
            "FUN_1400e5780": "OPLOC",
            "FUN_1400e5d10": "OPNPC",
            "FUN_1400e6190": "OPOBJ",
            "FUN_1400e6ea0": "OPPLAYER",
            "FUN_140169660": "IF_BUTTON",
            "FUN_1401a60d0": "IF_BUTTON",
            "FUN_1401f6b50": "MAP_BUILD_COMPLETE",
            "FUN_14014fe10": "TEXT_ENTRY",
            "FUN_14019abd0": "UI_RESET",
            "FUN_1401fd5b0": "RESUME_STRING",
            "FUN_1401fda40": "RESUME",
            "FUN_1401fdf30": "RESUME_STRING",
            "FUN_1401fe390": "RESUME_STRING",
            "FUN_1401fe5e0": "RESUME",
        }
    )
    return inferred


def build_server_setup_family_map(
    confirmed: dict[int, str], parser_rows: dict[int, dict]
) -> dict[str, str]:
    labels_by_setup: dict[str, list[str]] = {}
    for opcode, row in parser_rows.items():
        setup = row.get("setupFunctionName", "")
        if not setup or opcode not in confirmed:
            continue
        labels_by_setup.setdefault(setup, []).append(infer_family_label("server", confirmed[opcode]))
    return {
        setup: dominant_family(labels)
        for setup, labels in labels_by_setup.items()
        if dominant_family(labels)
    }


def build_legacy_server_candidates(confirmed: dict[int, str]) -> dict[str, dict[int, list[str]]]:
    used = set(confirmed.values())
    by_family_size: dict[str, dict[int, list[str]]] = {}
    for _, name, size in LEGACY_SERVER_NAMES:
        family = infer_family_label("server", name)
        if not family or name in used or size is None:
            continue
        by_family_size.setdefault(family, {}).setdefault(size, []).append(name)
    return by_family_size


MANUAL_SERVER_EXACT = {
    137: ["IF_SETRETEX"],
    202: ["IF_SETRECOL"],
}

MANUAL_CLIENT_EXACT = {
    24: ["RESUME_P_STRINGDIALOG", "RESUME_P_NAMEDIALOG", "RESUME_P_OBJDIALOG"],
    67: ["RESUME_P_STRINGDIALOG", "RESUME_P_NAMEDIALOG", "RESUME_P_OBJDIALOG"],
    93: ["RESUME_P_STRINGDIALOG", "RESUME_P_NAMEDIALOG", "RESUME_P_OBJDIALOG"],
}

MANUAL_CLIENT_DISPATCH_HINTS = {
    24: {
        "dispatcherFunction": "14003b9e0",
        "dispatcherFunctionName": "FUN_14003b9e0",
        "dispatchSelector": 0x754,
        "dispatchSelectorHex": "0x754",
        "dispatchCluster": "resume-prompt-cluster",
    },
    67: {
        "dispatcherFunction": "14003b9e0",
        "dispatcherFunctionName": "FUN_14003b9e0",
        "dispatchSelector": 0x323,
        "dispatchSelectorHex": "0x323",
        "dispatchCluster": "resume-prompt-cluster",
    },
    87: {
        "dispatcherFunction": "14003b9e0",
        "dispatcherFunctionName": "FUN_14003b9e0",
        "dispatchSelector": 0x203,
        "dispatchSelectorHex": "0x203",
        "dispatchCluster": "resume-prompt-cluster",
    },
    93: {
        "dispatcherFunction": "14003b9e0",
        "dispatcherFunctionName": "FUN_14003b9e0",
        "dispatchSelector": 0x7D7,
        "dispatchSelectorHex": "0x7d7",
        "dispatchCluster": "resume-prompt-cluster",
    },
}


def build_server_candidates() -> list[Candidate]:
    confirmed = parse_names_toml(PROT_DIR / "serverProtNames.toml")
    sizes = parse_sizes_toml(PHASE1_DIR / "serverProtSizes.generated.toml")
    parser_rows = {row["opcode"]: row for row in load_json(PHASE2_DIR / "serverParsers.json")}
    setup_family_map = build_server_setup_family_map(confirmed, parser_rows)
    legacy_exact_map = build_legacy_server_candidates(confirmed)
    cross_build = load_cross_build_scaffold()
    unresolved_family_size_counts: Counter[tuple[str, int]] = Counter()

    preclassified_rows: dict[int, tuple[str, str]] = {}
    for opcode in sorted(sizes):
        parser_row = parser_rows.get(opcode, {})
        name = confirmed.get(opcode, "")
        family_label = infer_family_label("server", name)
        family_source = "confirmed-name" if family_label else ""
        if not family_label and parser_row:
            setup_name = parser_row.get("setupFunctionName", "")
            family_label = setup_family_map.get(setup_name, "")
            family_source = "phase2-setup-family" if family_label else ""
        preclassified_rows[opcode] = (family_label, family_source)
        if not name and family_label:
            unresolved_family_size_counts[(family_label, sizes[opcode])] += 1

    candidates: list[Candidate] = []
    for opcode in sorted(sizes):
        parser_row = parser_rows.get(opcode, {})
        name = confirmed.get(opcode, "")
        confidence = "confirmed" if name else ("candidate" if parser_row else "unknown")
        source = "serverProtNames.toml" if name else ("phase2-server-parsers" if parser_row else "unmapped")
        family_label, family_source = preclassified_rows[opcode]
        exact_candidate_names: list[str] = []
        exact_candidate_source = ""
        if name:
            exact_candidate_names = [name]
            exact_candidate_source = "confirmed-name"
        elif opcode in MANUAL_SERVER_EXACT:
            exact_candidate_names = MANUAL_SERVER_EXACT[opcode]
            exact_candidate_source = "manual-override"
        elif family_label:
            size_candidates = legacy_exact_map.get(family_label, {}).get(sizes[opcode], [])
            unresolved_count = unresolved_family_size_counts[(family_label, sizes[opcode])]
            if size_candidates and unresolved_count == 1 and len(size_candidates) == 1:
                exact_candidate_names = size_candidates
                exact_candidate_source = "legacy-family-size-unique"
            elif size_candidates and unresolved_count <= len(size_candidates):
                exact_candidate_names = size_candidates
                exact_candidate_source = "legacy-family-size-ambiguous"
        candidates.append(
            Candidate(
                side="server",
                opcode=opcode,
                size=sizes[opcode],
                suggested_name=name,
                confidence=confidence,
                source=source,
                family_label=family_label,
                family_source=family_source,
                exact_candidate_names=exact_candidate_names,
                exact_candidate_source=exact_candidate_source,
                evidence={
                    "setupFunction": parser_row.get("setupFunction", ""),
                    "setupFunctionName": parser_row.get("setupFunctionName", ""),
                    "parserTarget": parser_row.get("parserTarget", ""),
                    "parserName": parser_row.get("parserName", ""),
                },
                confidence_score=0.0,
                score_breakdown={},
                cross_build=cross_build.get(
                    ("server", opcode),
                    {
                        "matchedFromBuild": None,
                        "matchedOpcode": None,
                        "matchedPacketName": "",
                        "matchingBasis": "",
                        "signatureHash": "",
                        "confidence": 0.0,
                    },
                ),
            )
        )
    return candidates


def build_client_candidates() -> list[Candidate]:
    confirmed = parse_names_toml(PROT_DIR / "clientProtNames.toml")
    sizes = parse_sizes_toml(PHASE1_DIR / "clientProtSizes.generated.toml")
    sender_rows = {row["opcode"]: row for row in load_json(PHASE2_DIR / "clientParsers.json")}
    sender_family_map = build_client_sender_family_map(confirmed, sender_rows)
    cross_build = load_cross_build_scaffold()

    candidates: list[Candidate] = []
    for opcode in sorted(sizes):
        sender_row = sender_rows.get(opcode, {})
        name = confirmed.get(opcode, "")
        confidence = "confirmed" if name else ("candidate" if sender_row.get("primarySenderName") else "unknown")
        source = "clientProtNames.toml" if name else ("phase2-client-senders" if sender_row.get("primarySenderName") else "unmapped")
        primary = sender_row.get("senderCandidates", [{}])[0] if sender_row.get("senderCandidates") else {}
        family_label = infer_family_label("client", name)
        family_source = "confirmed-name" if family_label else ""
        if not family_label and sender_row.get("primarySenderName"):
            family_label = sender_family_map.get(sender_row["primarySenderName"], "")
            family_source = "phase2-sender-family" if family_label else ""
        exact_candidate_names = [name] if name else []
        exact_candidate_source = "confirmed-name" if name else ""
        if not name and opcode in MANUAL_CLIENT_EXACT:
            exact_candidate_names = MANUAL_CLIENT_EXACT[opcode]
            exact_candidate_source = "manual-override"
        evidence = {
            "primarySender": sender_row.get("primarySender", ""),
            "primarySenderName": sender_row.get("primarySenderName", ""),
            "senderRole": primary.get("role", ""),
            "distinctOpcodeCount": primary.get("distinctOpcodeCount", 0),
            "score": primary.get("score", 0),
        }
        if opcode in MANUAL_CLIENT_DISPATCH_HINTS:
            evidence.update(MANUAL_CLIENT_DISPATCH_HINTS[opcode])
        candidates.append(
            Candidate(
                side="client",
                opcode=opcode,
                size=sizes[opcode],
                suggested_name=name,
                confidence=confidence,
                source=source,
                family_label=family_label,
                family_source=family_source,
                exact_candidate_names=exact_candidate_names,
                exact_candidate_source=exact_candidate_source,
                evidence=evidence,
                confidence_score=0.0,
                score_breakdown={},
                cross_build=cross_build.get(
                    ("client", opcode),
                    {
                        "matchedFromBuild": None,
                        "matchedOpcode": None,
                        "matchedPacketName": "",
                        "matchingBasis": "",
                        "signatureHash": "",
                        "confidence": 0.0,
                    },
                ),
            )
        )
    return candidates


def score_candidate(candidate: Candidate) -> tuple[float, dict[str, float]]:
    breakdown: dict[str, float] = {}
    score = 0.05

    if candidate.suggested_name:
        breakdown["confirmed_name"] = 0.75
        score += 0.75
    elif candidate.exact_candidate_names:
        if len(candidate.exact_candidate_names) == 1:
            breakdown["unique_exact_candidate"] = 0.45
            score += 0.45
        else:
            breakdown["ambiguous_exact_candidate"] = 0.28
            score += 0.28

    if candidate.family_label:
        breakdown["family_hint"] = 0.12
        score += 0.12

    if candidate.source.startswith("phase2-"):
        breakdown["phase2_mapping"] = 0.08
        score += 0.08

    parser_target = candidate.evidence.get("parserTarget", "")
    if parser_target:
        breakdown["parser_target"] = 0.08
        score += 0.08

    primary_sender = candidate.evidence.get("primarySender", "")
    if primary_sender:
        breakdown["primary_sender"] = 0.08
        score += 0.08

    sender_score = candidate.evidence.get("score", 0)
    if sender_score:
        normalized = min(float(sender_score) / 5000.0, 0.08)
        breakdown["sender_strength"] = round(normalized, 4)
        score += normalized

    if candidate.exact_candidate_source == "legacy-family-size-unique":
        breakdown["legacy_unique_shape"] = 0.1
        score += 0.1
    elif candidate.exact_candidate_source == "legacy-family-size-ambiguous":
        breakdown["legacy_shape"] = 0.04
        score += 0.04

    if candidate.evidence.get("dispatchCluster"):
        breakdown["dispatch_cluster"] = 0.06
        score += 0.06

    if candidate.confidence == "unknown":
        score = min(score, 0.35)

    return round(min(score, 1.0), 4), breakdown


def apply_scores(candidates: list[Candidate]) -> list[Candidate]:
    for candidate in candidates:
        score, breakdown = score_candidate(candidate)
        candidate.confidence_score = score
        candidate.score_breakdown = breakdown
    return candidates


def to_json_payload(candidates: list[Candidate]) -> list[dict]:
    return [
        {
            "side": candidate.side,
            "opcode": candidate.opcode,
            "size": candidate.size,
            "suggestedName": candidate.suggested_name,
            "confidence": candidate.confidence,
            "source": candidate.source,
            "familyLabel": candidate.family_label,
            "familySource": candidate.family_source,
            "exactCandidateNames": candidate.exact_candidate_names,
            "exactCandidateSource": candidate.exact_candidate_source,
            "evidence": candidate.evidence,
            "confidenceScore": candidate.confidence_score,
            "scoreBreakdown": candidate.score_breakdown,
            "crossBuild": candidate.cross_build,
        }
        for candidate in candidates
    ]


def build_ambiguous_client_clusters(candidates: list[Candidate]) -> list[dict]:
    clusters: dict[tuple[str, str], dict] = {}
    for candidate in candidates:
        if candidate.side != "client":
            continue
        if candidate.suggested_name:
            continue
        if len(candidate.exact_candidate_names) <= 1:
            continue
        cluster_name = candidate.evidence.get("dispatchCluster", "")
        dispatcher_name = candidate.evidence.get("dispatcherFunctionName", "")
        if not cluster_name or not dispatcher_name:
            continue
        key = (cluster_name, dispatcher_name)
        cluster = clusters.setdefault(
            key,
            {
                "cluster": cluster_name,
                "dispatcherFunction": candidate.evidence.get("dispatcherFunction", ""),
                "dispatcherFunctionName": dispatcher_name,
                "members": [],
                "candidateNameUniverse": [],
            },
        )
        cluster["members"].append(
            {
                "opcode": candidate.opcode,
                "size": candidate.size,
                "familyLabel": candidate.family_label,
                "exactCandidateNames": candidate.exact_candidate_names,
                "dispatchSelector": candidate.evidence.get("dispatchSelector"),
                "dispatchSelectorHex": candidate.evidence.get("dispatchSelectorHex", ""),
                "primarySender": candidate.evidence.get("primarySender", ""),
                "primarySenderName": candidate.evidence.get("primarySenderName", ""),
            }
        )
        for name in candidate.exact_candidate_names:
            if name not in cluster["candidateNameUniverse"]:
                cluster["candidateNameUniverse"].append(name)

    for cluster in clusters.values():
        cluster["members"].sort(key=lambda row: row["opcode"])
    return sorted(clusters.values(), key=lambda row: (row["cluster"], row["dispatcherFunctionName"]))


def write_summary(path: Path, candidates: list[Candidate]) -> None:
    by_side: dict[str, list[Candidate]] = {"server": [], "client": []}
    for candidate in candidates:
        by_side[candidate.side].append(candidate)
    ambiguous_client_clusters = build_ambiguous_client_clusters(candidates)

    lines = [
        "# Phase 3 Name Candidate Summary",
        "",
    ]

    for side in ("server", "client"):
        rows = by_side[side]
        confidence_counts = Counter(candidate.confidence for candidate in rows)
        named = sum(1 for candidate in rows if candidate.suggested_name)
        unresolved = sum(1 for candidate in rows if not candidate.suggested_name)
        family_classified = sum(1 for candidate in rows if candidate.family_label)
        unresolved_family_classified = sum(
            1 for candidate in rows if not candidate.suggested_name and candidate.family_label
        )
        unresolved_exact_candidates = [
            candidate for candidate in rows if not candidate.suggested_name and candidate.exact_candidate_names
        ]
        unresolved_exact_unique = [
            candidate for candidate in unresolved_exact_candidates if len(candidate.exact_candidate_names) == 1
        ]
        unresolved_exact_ambiguous = [
            candidate for candidate in unresolved_exact_candidates if len(candidate.exact_candidate_names) > 1
        ]
        top_unresolved_families = Counter(
            candidate.family_label for candidate in rows if not candidate.suggested_name and candidate.family_label
        ).most_common(5)
        lines.extend(
            [
                f"## {side.title()}",
                "",
                f"- Total opcodes: `{len(rows)}`",
                f"- Named opcodes: `{named}`",
                f"- Unresolved opcodes: `{unresolved}`",
                f"- Confirmed: `{confidence_counts.get('confirmed', 0)}`",
                f"- Candidate: `{confidence_counts.get('candidate', 0)}`",
                f"- Unknown: `{confidence_counts.get('unknown', 0)}`",
                f"- Family classified: `{family_classified}`",
                f"- Unresolved with family hint: `{unresolved_family_classified}`",
                f"- Unresolved with exact-name candidates: `{len(unresolved_exact_candidates)}`",
                f"- Unresolved with unique exact candidate: `{len(unresolved_exact_unique)}`",
                f"- Mean confidence score: `{round(sum(candidate.confidence_score for candidate in rows) / max(len(rows), 1), 4)}`",
                "",
            ]
        )
        if top_unresolved_families:
            lines.append("Top unresolved families:")
            for family_label, count in top_unresolved_families:
                lines.append(f"- `{family_label}` -> `{count}`")
            lines.append("")
        if unresolved_exact_unique:
            lines.append("Sample unique exact-name candidates:")
            for candidate in unresolved_exact_unique[:8]:
                lines.append(
                    f"- `{candidate.opcode}` -> `{candidate.exact_candidate_names[0]}`"
                    f" via `{candidate.exact_candidate_source}`"
                )
            lines.append("")
        if unresolved_exact_ambiguous:
            lines.append("Sample ambiguous exact-name candidates:")
            for candidate in unresolved_exact_ambiguous[:6]:
                joined = ", ".join(candidate.exact_candidate_names)
                dispatch_suffix = ""
                if candidate.evidence.get("dispatchSelectorHex"):
                    dispatch_suffix = (
                        f" [dispatcher {candidate.evidence['dispatcherFunctionName']}"
                        f", selector {candidate.evidence['dispatchSelectorHex']}]"
                    )
                lines.append(
                    f"- `{candidate.opcode}` -> `{joined}`"
                    f" via `{candidate.exact_candidate_source}`{dispatch_suffix}"
                )
            lines.append("")

    lines.extend(
        [
            "## Ambiguous Client Clusters",
            "",
        ]
    )
    if ambiguous_client_clusters:
        for cluster in ambiguous_client_clusters:
            lines.append(
                f"- `{cluster['cluster']}` via `{cluster['dispatcherFunctionName']}`"
                f" with candidates `{', '.join(cluster['candidateNameUniverse'])}`"
            )
            for member in cluster["members"]:
                lines.append(
                    f"  - opcode `{member['opcode']}` selector `{member['dispatchSelectorHex']}`"
                    f" sender `{member['primarySenderName']}`"
                )
        lines.append("")
    else:
        lines.extend(["- none", ""])

    lines.extend(
        [
            "## Outputs",
            "",
            "- `nameCandidates.json`",
            "- `clientAmbiguousClusters.json`",
            "- `serverProtNames.generated.toml`",
            "- `clientProtNames.generated.toml`",
            "- `serverProtNames.uniqueCandidates.generated.toml`",
            "- `clientProtNames.uniqueCandidates.generated.toml`",
            "- `phase3-summary.md`",
            "",
        ]
    )

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    server_candidates = build_server_candidates()
    client_candidates = build_client_candidates()
    all_candidates = apply_scores(server_candidates + client_candidates)

    write_names_toml(
        OUTPUT_DIR / "serverProtNames.generated.toml",
        {candidate.opcode: candidate.suggested_name for candidate in server_candidates if candidate.suggested_name},
        "Draft server packet names generated from confirmed 946 mappings plus Phase 1/2 evidence",
    )
    write_names_toml(
        OUTPUT_DIR / "clientProtNames.generated.toml",
        {candidate.opcode: candidate.suggested_name for candidate in client_candidates if candidate.suggested_name},
        "Draft client packet names generated from confirmed 946 mappings plus Phase 1/2 evidence",
    )
    write_names_toml(
        OUTPUT_DIR / "serverProtNames.uniqueCandidates.generated.toml",
        {
            candidate.opcode: candidate.exact_candidate_names[0]
            for candidate in server_candidates
            if not candidate.suggested_name and len(candidate.exact_candidate_names) == 1
        },
        "Unique unresolved server packet name candidates generated from Phase 3 exact-candidate heuristics",
    )
    write_names_toml(
        OUTPUT_DIR / "clientProtNames.uniqueCandidates.generated.toml",
        {
            candidate.opcode: candidate.exact_candidate_names[0]
            for candidate in client_candidates
            if not candidate.suggested_name and len(candidate.exact_candidate_names) == 1
        },
        "Unique unresolved client packet name candidates generated from Phase 3 exact-candidate heuristics",
    )
    (OUTPUT_DIR / "nameCandidates.json").write_text(
        json.dumps(to_json_payload(all_candidates), indent=2) + "\n",
        encoding="utf-8",
    )
    (OUTPUT_DIR / "clientAmbiguousClusters.json").write_text(
        json.dumps(build_ambiguous_client_clusters(all_candidates), indent=2) + "\n",
        encoding="utf-8",
    )
    write_summary(OUTPUT_DIR / "phase3-summary.md", all_candidates)

    print(
        json.dumps(
            {
                "outputDir": str(OUTPUT_DIR),
                "nameCandidates": str(OUTPUT_DIR / "nameCandidates.json"),
                "clientAmbiguousClusters": str(OUTPUT_DIR / "clientAmbiguousClusters.json"),
                "serverNamesToml": str(OUTPUT_DIR / "serverProtNames.generated.toml"),
                "clientNamesToml": str(OUTPUT_DIR / "clientProtNames.generated.toml"),
                "serverUniqueCandidatesToml": str(OUTPUT_DIR / "serverProtNames.uniqueCandidates.generated.toml"),
                "clientUniqueCandidatesToml": str(OUTPUT_DIR / "clientProtNames.uniqueCandidates.generated.toml"),
                "summary": str(OUTPUT_DIR / "phase3-summary.md"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
