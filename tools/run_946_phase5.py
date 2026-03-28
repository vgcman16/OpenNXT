from __future__ import annotations

import argparse
import json
from pathlib import Path

from protocol_automation_common import (
    PHASE_DIRS,
    SHARED_DIR,
    WORKSPACE,
    camel_case_packet_name,
    ensure_directory,
    kotlin_property_name,
    kotlin_type_for_field,
    packet_class_name,
    sanitize_identifier,
    stable_json_text,
)


DEFAULT_VERIFIED_INPUT = SHARED_DIR / "verified-packets.json"
DEFAULT_OUTPUT_DIR = PHASE_DIRS[5]
DEFAULT_GENERATED_SRC_DIR = WORKSPACE / "src" / "generated" / "kotlin"
DEFAULT_GENERATED_PACKAGE = "com.opennxt.net.game.generated"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 5 of the RS3 build 946 extraction pipeline.")
    parser.add_argument("--verified-input", type=Path, default=DEFAULT_VERIFIED_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--generated-src-dir", type=Path, default=DEFAULT_GENERATED_SRC_DIR)
    parser.add_argument("--generated-package", default=DEFAULT_GENERATED_PACKAGE)
    return parser.parse_args()


def load_verified_entries(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload.get("entries", [])
    return payload


def write_if_changed(path: Path, text: str) -> None:
    ensure_directory(path.parent)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8")


def generated_package_for(base_package: str, side: str) -> str:
    return f"{base_package}.{side}prot"


def generated_file_path(base_dir: Path, package_name: str, class_name: str) -> Path:
    package_dir = package_name.replace(".", "\\")
    return base_dir / package_dir / f"{class_name}.kt"


def field_entries(entry: dict) -> list[dict]:
    fields = entry.get("fieldDeclaration", {}).get("fields", [])
    result: list[dict] = []
    for index, field in enumerate(fields):
        name = field["name"]
        result.append(
            {
                "name": name,
                "propertyName": kotlin_property_name(name),
                "safePropertyName": sanitize_identifier(name),
                "type": field["type"],
                "kotlinType": kotlin_type_for_field(field["type"]),
                "index": index,
            }
        )
    return result


def render_packet_file(entry: dict, package_name: str, class_name: str) -> str:
    fields = field_entries(entry)
    constructor = ", ".join(
        f"val {field['propertyName']}: {field['kotlinType']}" for field in fields
    )
    from_map_args = ",\n                ".join(
        f"{field['safePropertyName']} = packet[\"{field['name']}\"] as {field['kotlinType']}"
        for field in fields
    )
    to_map_args = ",\n                ".join(
        f"\"{field['name']}\" to packet.{field['safePropertyName']}"
        for field in fields
    )
    field_lines = ",\n            ".join(
        f'GeneratedPacketCatalog.Field("{field["name"]}", "{field["type"]}", "{field["kotlinType"]}")' for field in fields
    )
    return f"""package {package_name}

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class {class_name}({constructor}) : GamePacket {{
    companion object {{
        val catalogFields = listOf(
            {field_lines}
        )
    }}

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<{class_name}>(fields) {{
        override fun fromMap(packet: Map<String, Any>): {class_name} {{
            return {class_name}(
                {from_map_args}
            )
        }}

        override fun toMap(packet: {class_name}): Map<String, Any> = linkedMapOf(
                {to_map_args}
        )
    }}
}}
"""


def render_catalog(entries: list[dict], generated_package: str) -> str:
    import_lines = []
    register_lines = []
    catalog_entries = []
    seen_imports: set[str] = set()

    for entry in entries:
        class_name = packet_class_name(entry["packetName"])
        package_name = generated_package_for(generated_package, entry["side"])
        import_name = f"{package_name}.{class_name}"
        if import_name not in seen_imports:
            seen_imports.add(import_name)
            import_lines.append(f"import {import_name}")
        field_entries_text = ", ".join(
            f'Field("{field["name"]}", "{field["type"]}", "{kotlin_type_for_field(field["type"])}")'
            for field in entry["fieldDeclaration"]["fields"]
        )
        catalog_entries.append(
            f"""        Entry(
            side = Side.{entry["side"].upper()},
            name = "{entry["packetName"]}",
            opcode = {entry["opcode"]},
            clazz = {class_name}::class,
            codecType = {class_name}.Codec::class,
            fields = listOf({field_entries_text}),
            hasManualRegistration = {str(entry["hasManualRegistration"]).lower()},
            runtimePriority = {str(entry["runtimePriority"]).lower()}
        )"""
        )
        if not entry["hasManualRegistration"]:
            register_lines.append(
                f'        PacketRegistry.registerInspectionGenerated(Side.{entry["side"].upper()}, "{entry["packetName"]}", {class_name}::class, {class_name}.Codec::class)'
            )

    imports = "\n".join(sorted(import_lines))
    entries_text = ",\n".join(catalog_entries)
    registers_text = "\n".join(register_lines) or "        // No generated inspection registrations on this run"
    return f"""package {generated_package}

import com.opennxt.net.Side
import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.PacketRegistry
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import kotlin.reflect.KClass
{imports}

object GeneratedPacketCatalog {{
    data class Field(val name: String, val type: String, val kotlinType: String)

    data class Entry(
        val side: Side,
        val name: String,
        val opcode: Int,
        val clazz: KClass<out GamePacket>,
        val codecType: KClass<out DynamicGamePacketCodec<*>>,
        val fields: List<Field>,
        val hasManualRegistration: Boolean,
        val runtimePriority: Boolean
    )

    val entries: List<Entry> = listOf(
{entries_text}
    )

    fun registerAll() {{
{registers_text}
    }}
}}
"""


def write_summary(path: Path, entries: list[dict], generated_dir: Path, catalog_path: Path) -> None:
    lines = [
        "# Phase 5 Integration Summary",
        "",
        f"- Verified packet entries: `{len(entries)}`",
        f"- Generated source root: `{generated_dir}`",
        f"- Generated catalog: `{catalog_path}`",
        "",
        "## Packets",
        "",
    ]
    for entry in entries:
        lines.append(
            f"- `{entry['side']}:{entry['opcode']}` `{entry['packetName']}`"
            f" manual-precedence=`{entry['hasManualRegistration']}`"
            f" runtime-priority=`{entry['runtimePriority']}`"
        )
    lines.append("")
    write_if_changed(path, "\n".join(lines))


def main() -> int:
    args = parse_args()
    entries = load_verified_entries(args.verified_input)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if not entries:
        raise SystemExit(f"No verified packet entries found in {args.verified_input}")

    rendered_entries = []
    for entry in entries:
        class_name = packet_class_name(entry["packetName"])
        package_name = generated_package_for(args.generated_package, entry["side"])
        packet_path = generated_file_path(args.generated_src_dir, package_name, class_name)
        write_if_changed(packet_path, render_packet_file(entry, package_name, class_name))
        rendered_entry = {
            **entry,
            "generatedClassName": class_name,
            "generatedPackage": package_name,
            "generatedFile": str(packet_path),
        }
        rendered_entries.append(rendered_entry)

    catalog_package_dir = args.generated_package.replace(".", "\\")
    catalog_path = args.generated_src_dir / catalog_package_dir / "GeneratedPacketCatalog.kt"
    write_if_changed(catalog_path, render_catalog(rendered_entries, args.generated_package))

    write_if_changed(args.output_dir / "generatedPackets.json", stable_json_text(rendered_entries))
    write_summary(args.output_dir / "phase5-summary.md", rendered_entries, args.generated_src_dir, catalog_path)

    print(
        json.dumps(
            {
                "verifiedInput": str(args.verified_input),
                "generatedPackets": str(args.output_dir / "generatedPackets.json"),
                "summary": str(args.output_dir / "phase5-summary.md"),
                "generatedSourceRoot": str(args.generated_src_dir),
                "generatedCatalog": str(catalog_path),
                "generatedPacketCount": len(rendered_entries),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
