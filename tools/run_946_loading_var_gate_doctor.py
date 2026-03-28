from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from protocol_automation_common import SHARED_DIR, WORKSPACE, load_json, standard_tool_artifact, write_json
from protocol_946_debug_common import WORLD_LOG_DEFAULT


LOADING_VAR_GATE_JSON = "loading-var-gate-doctor.json"
LOADING_VAR_GATE_MD = "loading-var-gate-doctor.md"
SCRIPT_LINE_RE = re.compile(
    r"^(?P<timestamp>\S+)\s+(?P<kind>\S+)\s+.*?\bscripts=(?P<scripts>[0-9,]+)"
)
KIND_LINE_RE = re.compile(r"^(?P<timestamp>\S+)\s+(?P<kind>\S+)\s+")
RELEVANT_SCRIPT_KINDS = {
    "world-send-forced-fallback-deferred-completion-lite-scripts",
    "world-send-forced-fallback-deferred-completion-scripts",
    "world-send-forced-fallback-deferred-completion-core-scripts",
    "world-send-deferred-completion-lite-scripts",
    "world-send-deferred-completion-scripts",
    "world-send-deferred-completion-core-scripts",
    "world-send-deferred-completion-announcement-scripts",
    "world-send-deferred-light-tail-scripts-after-scene-start",
    "world-send-deferred-forced-fallback-completion-companions",
}
LATEST_SESSION_MARKERS = {
    "world-send-reset-client-varcache",
    "world-defer-default-varps",
    "world-send-deferred-default-varps",
    *RELEVANT_SCRIPT_KINDS,
}
DEFAULT_VAR_MEANING_ROOT = WORKSPACE / "data" / "cache-analysis" / "var-meaning"
DEFAULT_MAP_GATE_DIR = WORKSPACE / "data" / "debug" / "client-map-gate"
DEFAULT_SHARED_SCENE_START = SHARED_DIR / "scene-start-doctor.json"
DEFAULT_SHARED_POST_SCENE = SHARED_DIR / "post-scene-opcode-doctor.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Correlate the latest 946 loading/scene-start script burst with the built var-meaning index "
            "so the post-ready plateau can be explained in terms of concrete candidate varps/varbits."
        )
    )
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--var-meaning-root", type=Path, default=DEFAULT_VAR_MEANING_ROOT)
    parser.add_argument("--map-gate-dir", type=Path, default=DEFAULT_MAP_GATE_DIR)
    parser.add_argument("--scene-start-artifact", type=Path, default=DEFAULT_SHARED_SCENE_START)
    parser.add_argument("--post-scene-artifact", type=Path, default=DEFAULT_SHARED_POST_SCENE)
    parser.add_argument("--tail-bytes", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    return parser.parse_args()


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "json": output_dir / LOADING_VAR_GATE_JSON,
        "markdown": output_dir / LOADING_VAR_GATE_MD,
    }


def read_tail_text(path: Path, max_bytes: int) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        read_size = min(size, max_bytes)
        handle.seek(size - read_size)
        data = handle.read(read_size)
    text = data.decode("utf-8", errors="ignore")
    if read_size < size:
        newline = text.find("\n")
        if newline >= 0:
            text = text[newline + 1 :]
    return text


def latest_session_lines(world_log: Path, tail_bytes: int) -> list[str]:
    tail_text = read_tail_text(world_log, tail_bytes)
    if not tail_text:
        return []
    lines = [line for line in tail_text.splitlines() if line.strip()]
    appearance_indexes = [
        index
        for index, line in enumerate(lines)
        if " world-stage " in line and " stage=appearance" in line
    ]
    start_index = appearance_indexes[-1] if appearance_indexes else 0
    return lines[start_index:]


def parse_session_markers(lines: list[str]) -> tuple[list[dict[str, Any]], Counter[str]]:
    script_markers: list[dict[str, Any]] = []
    marker_counts: Counter[str] = Counter()
    for line in lines:
        kind_match = KIND_LINE_RE.match(line)
        if not kind_match:
            continue
        kind = kind_match.group("kind")
        if kind not in LATEST_SESSION_MARKERS:
            continue
        marker_counts[kind] += 1
        script_match = SCRIPT_LINE_RE.match(line)
        if not script_match:
            continue
        scripts = [
            int(part)
            for part in script_match.group("scripts").split(",")
            if part.strip().isdigit()
        ]
        script_markers.append(
            {
                "timestamp": script_match.group("timestamp"),
                "kind": kind,
                "scriptIds": scripts,
                "raw": line,
            }
        )
    return script_markers, marker_counts


def latest_map_gate_summary(root: Path) -> dict[str, Any]:
    if not root.exists():
        return {}
    candidates = sorted(root.glob("summary*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for candidate in candidates:
        payload = load_json(candidate, {})
        if isinstance(payload, dict):
            payload = dict(payload)
            payload["path"] = str(candidate)
            return payload
    return {}


def load_script_evidence(root: Path, script_id: int) -> dict[str, Any] | None:
    path = root / "scripts" / f"{script_id}.json"
    payload = load_json(path, None)
    if not isinstance(payload, dict):
        return None
    payload = dict(payload)
    payload["path"] = str(path)
    return payload


def load_var_entry(root: Path, ref_type: str, ref_id: int) -> dict[str, Any] | None:
    folder = "varps" if ref_type == "varp" else "varbits"
    path = root / folder / f"{ref_id}.json"
    payload = load_json(path, None)
    if not isinstance(payload, dict):
        return None
    payload = dict(payload)
    payload["path"] = str(path)
    return payload


def summarize_var_entry(ref_type: str, ref_id: int, entry: dict[str, Any] | None) -> dict[str, Any]:
    if not entry:
        return {
            "present": False,
            "refType": ref_type,
            "id": ref_id,
        }
    if ref_type == "varp":
        backing_varbits = entry.get("backingVarbits") if isinstance(entry.get("backingVarbits"), list) else []
        return {
            "present": True,
            "refType": ref_type,
            "id": ref_id,
            "domain": entry.get("domain", ""),
            "type": entry.get("type", ""),
            "forceDefault": bool(entry.get("forceDefault", False)),
            "backingVarbitCount": len(backing_varbits),
            "path": entry.get("path", ""),
        }
    return {
        "present": True,
        "refType": ref_type,
        "id": ref_id,
        "baseVar": entry.get("baseVar"),
        "lsb": entry.get("lsb"),
        "msb": entry.get("msb"),
        "path": entry.get("path", ""),
    }


def aggregate_refs(
    root: Path,
    script_records: list[dict[str, Any]],
    field_name: str,
    ref_type: str,
) -> list[dict[str, Any]]:
    aggregated: dict[int, dict[str, Any]] = {}
    for script in script_records:
        for ref in script.get(field_name, []):
            if not isinstance(ref, dict):
                continue
            ref_id = ref.get("id")
            if not isinstance(ref_id, int):
                continue
            entry = aggregated.setdefault(
                ref_id,
                {
                    "id": ref_id,
                    "refType": ref_type,
                    "scriptIds": set(),
                    "accesses": Counter(),
                    "extractions": Counter(),
                    "offsets": [],
                },
            )
            entry["scriptIds"].add(int(script["scriptId"]))
            access = str(ref.get("access", "") or "")
            extraction = str(ref.get("extraction", "") or "")
            if access:
                entry["accesses"][access] += 1
            if extraction:
                entry["extractions"][extraction] += 1
            if ref.get("offset") is not None:
                entry["offsets"].append(ref["offset"])

    results: list[dict[str, Any]] = []
    for ref_id, entry in sorted(
        aggregated.items(),
        key=lambda item: (-len(item[1]["scriptIds"]), item[0]),
    ):
        meaning = summarize_var_entry(ref_type, ref_id, load_var_entry(root, ref_type, ref_id))
        results.append(
            {
                "id": ref_id,
                "refType": ref_type,
                "scriptIds": sorted(entry["scriptIds"]),
                "scriptCount": len(entry["scriptIds"]),
                "accesses": dict(sorted(entry["accesses"].items())),
                "extractions": dict(sorted(entry["extractions"].items())),
                "sampleOffsets": sorted({int(offset) for offset in entry["offsets"]})[:8],
                "meaning": meaning,
            }
        )
    return results


def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    session_lines = latest_session_lines(args.world_log, args.tail_bytes)
    script_markers, marker_counts = parse_session_markers(session_lines)

    script_sources: dict[int, dict[str, Any]] = {}
    for marker in script_markers:
        for script_id in marker["scriptIds"]:
            entry = script_sources.setdefault(
                script_id,
                {
                    "scriptId": script_id,
                    "sourceKinds": set(),
                    "sourceLines": [],
                },
            )
            entry["sourceKinds"].add(marker["kind"])
            entry["sourceLines"].append(marker["raw"])

    script_records: list[dict[str, Any]] = []
    missing_scripts: list[int] = []
    for script_id in sorted(script_sources):
        evidence = load_script_evidence(args.var_meaning_root, script_id)
        base = script_sources[script_id]
        record = {
            "scriptId": script_id,
            "sourceKinds": sorted(base["sourceKinds"]),
            "sourceLines": base["sourceLines"][-3:],
            "evidencePresent": evidence is not None,
        }
        if evidence is None:
            missing_scripts.append(script_id)
            record.update(
                {
                    "decodeMode": "missing",
                    "exactParse": False,
                    "directVarps": [],
                    "directVarbits": [],
                    "heuristicVarps": [],
                    "heuristicVarbits": [],
                }
            )
        else:
            record.update(
                {
                    "decodeMode": evidence.get("decodeMode", ""),
                    "exactParse": bool(evidence.get("exactParse", False)),
                    "instructionCount": int(evidence.get("instructionCount", 0) or 0),
                    "directVarps": list(evidence.get("directVarps", [])),
                    "directVarbits": list(evidence.get("directVarbits", [])),
                    "heuristicVarps": list(evidence.get("heuristicVarps", [])),
                    "heuristicVarbits": list(evidence.get("heuristicVarbits", [])),
                    "evidencePath": evidence.get("path", ""),
                }
            )
        script_records.append(record)

    direct_varps = aggregate_refs(args.var_meaning_root, script_records, "directVarps", "varp")
    heuristic_varps = aggregate_refs(args.var_meaning_root, script_records, "heuristicVarps", "varp")
    direct_varbits = aggregate_refs(args.var_meaning_root, script_records, "directVarbits", "varbit")
    heuristic_varbits = aggregate_refs(args.var_meaning_root, script_records, "heuristicVarbits", "varbit")

    scene_start = load_json(args.scene_start_artifact, {}) or {}
    post_scene = load_json(args.post_scene_artifact, {}) or {}
    latest_likely_blocker = (
        ((post_scene.get("summary") or {}).get("latestLikelyBlocker"))
        or ((scene_start.get("summary") or {}).get("latestLikelyBlocker"))
        or "unknown"
    )
    map_gate = latest_map_gate_summary(args.map_gate_dir)

    top_candidate_varps = (direct_varps + [entry for entry in heuristic_varps if entry["id"] not in {item["id"] for item in direct_varps}])[:12]
    needs: list[str] = []
    if map_gate:
        if int(map_gate.get("idxLookupCount", 0) or 0) == 0 and int(map_gate.get("httpMsRequestCount", 0) or 0) == 0:
            needs.append("client-side var gate before archive resolution; no cache idx lookups or /ms archive requests occurred")
    if marker_counts.get("world-send-reset-client-varcache", 0) > 0 and marker_counts.get("world-send-deferred-default-varps", 0) <= 0:
        needs.append("default varp handoff after ResetClientVarcache on the accepted-ready path")
    if top_candidate_varps:
        candidate_ids = ",".join(str(entry["id"]) for entry in top_candidate_varps[:6])
        needs.append(f"live read/write capture for candidate varps {candidate_ids} before the first scene archive request")
    if missing_scripts:
        sample = ",".join(str(script_id) for script_id in missing_scripts[:6])
        needs.append(f"materialize or infer var evidence for loading-tail scripts {sample}")
    if not needs:
        needs.append("first non-reference scene archive request after reference-table[0]")

    summary = {
        "latestLikelyBlocker": latest_likely_blocker,
        "scriptCount": len(script_records),
        "scriptIds": [record["scriptId"] for record in script_records],
        "scriptsMissingEvidence": missing_scripts,
        "resetClientVarcacheObserved": marker_counts.get("world-send-reset-client-varcache", 0) > 0,
        "deferredDefaultVarpsObserved": marker_counts.get("world-send-deferred-default-varps", 0) > 0,
        "candidateDirectVarpCount": len(direct_varps),
        "candidateHeuristicVarpCount": len(heuristic_varps),
        "candidateDirectVarbitCount": len(direct_varbits),
        "candidateHeuristicVarbitCount": len(heuristic_varbits),
        "mapGateIdxLookupCount": int(map_gate.get("idxLookupCount", 0) or 0),
        "mapGateHttpMsRequestCount": int(map_gate.get("httpMsRequestCount", 0) or 0),
        "mapGateHttpNonReferenceRequestCount": int(map_gate.get("httpNonReferenceRequestCount", 0) or 0),
    }

    artifacts = {
        "loadingVarGateDoctorJson": str(args.output_dir / LOADING_VAR_GATE_JSON),
        "loadingVarGateDoctorMarkdown": str(args.output_dir / LOADING_VAR_GATE_MD),
    }
    return standard_tool_artifact(
        tool_name="run_946_loading_var_gate_doctor",
        status="ok",
        inputs={
            "worldLog": str(args.world_log),
            "varMeaningRoot": str(args.var_meaning_root),
            "sceneStartArtifact": str(args.scene_start_artifact),
            "postSceneArtifact": str(args.post_scene_artifact),
            "mapGateDir": str(args.map_gate_dir),
        },
        artifacts=artifacts,
        summary=summary,
        extra={
            "markerCounts": dict(sorted(marker_counts.items())),
            "mapGateSummary": map_gate,
            "scripts": script_records,
            "candidateVarps": {
                "direct": direct_varps,
                "heuristic": heuristic_varps,
            },
            "candidateVarbits": {
                "direct": direct_varbits,
                "heuristic": heuristic_varbits,
            },
            "verdict": {
                "likelyBlocker": latest_likely_blocker,
                "needs": needs,
                "recommendation": (
                    "The client is still stalling before scene archive fetches begin. Focus on the candidate "
                    "loading vars touched by the late bootstrap scripts, especially where the live map-gate "
                    "capture shows no idx lookups and no non-reference /ms requests."
                ),
            },
        },
    )


def render_var_section(title: str, entries: list[dict[str, Any]]) -> list[str]:
    lines = [f"### {title}", ""]
    if not entries:
        lines.append("- none")
        lines.append("")
        return lines
    for entry in entries[:12]:
        meaning = entry["meaning"]
        meaning_bits: list[str] = []
        if meaning.get("present"):
            if meaning["refType"] == "varp":
                if meaning.get("domain"):
                    meaning_bits.append(f"domain={meaning['domain']}")
                if meaning.get("type"):
                    meaning_bits.append(f"type={meaning['type']}")
                meaning_bits.append(f"forceDefault={meaning.get('forceDefault', False)}")
                meaning_bits.append(f"backingVarbits={meaning.get('backingVarbitCount', 0)}")
            else:
                meaning_bits.append(f"baseVar={meaning.get('baseVar')}")
                meaning_bits.append(f"bits={meaning.get('lsb')}..{meaning.get('msb')}")
        else:
            meaning_bits.append("meaning=missing")
        lines.append(
            f"- `{entry['refType']} {entry['id']}` scripts={entry['scriptIds']} "
            f"accesses={entry['accesses']} extractions={entry['extractions']} "
            f"{' '.join(meaning_bits)}"
        )
    lines.append("")
    return lines


def render_markdown(artifact: dict[str, Any]) -> str:
    summary = artifact.get("summary", {})
    verdict = artifact.get("verdict", {})
    lines = [
        "# 946 Loading Var Gate Doctor",
        "",
        f"- Status: `{artifact.get('status', 'unknown')}`",
        f"- Latest likely blocker: `{summary.get('latestLikelyBlocker', 'unknown')}`",
        f"- Loading-tail scripts found: `{summary.get('scriptCount', 0)}`",
        f"- Scripts missing evidence: `{summary.get('scriptsMissingEvidence', [])}`",
        f"- ResetClientVarcache observed: `{summary.get('resetClientVarcacheObserved', False)}`",
        f"- Deferred default varps observed: `{summary.get('deferredDefaultVarpsObserved', False)}`",
        f"- Map-gate idx lookups: `{summary.get('mapGateIdxLookupCount', 0)}`",
        f"- Map-gate /ms requests: `{summary.get('mapGateHttpMsRequestCount', 0)}`",
        f"- Map-gate non-reference /ms requests: `{summary.get('mapGateHttpNonReferenceRequestCount', 0)}`",
        "",
        "## Verdict",
        "",
        f"- Recommendation: {verdict.get('recommendation', '')}",
        "",
        "## Exact Needs",
        "",
    ]
    for need in verdict.get("needs", []):
        lines.append(f"- {need}")
    lines.extend(["", "## Scripts", ""])
    scripts = artifact.get("scripts", [])
    if not scripts:
        lines.append("- none")
    for record in scripts:
        lines.append(
            f"- `script {record['scriptId']}` decode=`{record.get('decodeMode', '')}` "
            f"exact=`{record.get('exactParse', False)}` sources=`{record.get('sourceKinds', [])}` "
            f"directVarps=`{len(record.get('directVarps', []))}` heuristicVarps=`{len(record.get('heuristicVarps', []))}` "
            f"directVarbits=`{len(record.get('directVarbits', []))}` heuristicVarbits=`{len(record.get('heuristicVarbits', []))}`"
        )
    lines.extend(["", "## Candidate Vars", ""])
    lines.extend(render_var_section("Direct Varps", (artifact.get("candidateVarps") or {}).get("direct", [])))
    lines.extend(render_var_section("Heuristic Varps", (artifact.get("candidateVarps") or {}).get("heuristic", [])))
    lines.extend(render_var_section("Direct Varbits", (artifact.get("candidateVarbits") or {}).get("direct", [])))
    lines.extend(render_var_section("Heuristic Varbits", (artifact.get("candidateVarbits") or {}).get("heuristic", [])))
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifact = build_artifact(args)
    paths = output_paths(args.output_dir)
    write_json(paths["json"], artifact)
    paths["markdown"].write_text(render_markdown(artifact), encoding="utf-8")
    print(
        render_markdown(
            {
                "status": artifact.get("status"),
                "summary": artifact.get("summary"),
                "verdict": artifact.get("verdict"),
                "scripts": artifact.get("scripts"),
                "candidateVarps": artifact.get("candidateVarps"),
                "candidateVarbits": artifact.get("candidateVarbits"),
            }
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
