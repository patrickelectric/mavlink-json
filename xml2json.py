#!/usr/bin/env python3
"""Expand MAVLink XML dialects (with includes) into JSON."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET


SOURCE_KEY = "_source"


def mark_source(element: ET.Element, source: Path) -> None:
    """Annotate an element tree with the file it came from."""
    element.attrib[SOURCE_KEY] = str(source)
    for child in element:
        mark_source(child, source)


def normalize_text(text: Optional[str]) -> Optional[str]:
    """Strip and collapse whitespace; return None if empty."""
    if text is None:
        return None
    collapsed = " ".join(text.split())
    return collapsed or None


def clean_attributes(element: ET.Element) -> Dict[str, str]:
    """Return attributes without internal markers."""
    return {k: v for k, v in element.attrib.items() if k != SOURCE_KEY}


def parse_deprecated(element: ET.Element) -> Optional[Dict[str, Any]]:
    """Extract deprecated metadata if present."""
    deprecated = element.find("deprecated")
    if deprecated is None:
        return None

    data: Dict[str, Any] = clean_attributes(deprecated)
    text = normalize_text(deprecated.text)
    if text:
        data["description"] = text
    return data


def load_and_expand(file_path: Path, stack: List[Path]) -> ET.Element:
    """Load an XML file, expand includes recursively, and return its root."""
    if file_path in stack:
        cycle = " -> ".join(str(p.name) for p in (*stack, file_path))
        raise ValueError(f"Include cycle detected: {cycle}")

    tree = ET.parse(file_path)
    root = tree.getroot()
    mark_source(root, file_path)

    expand_includes(root, current_file=file_path, stack=stack + [file_path])
    return root


def parse_param(element: ET.Element) -> Dict[str, Any]:
    data: Dict[str, Any] = clean_attributes(element)
    text = normalize_text(element.text)
    if text:
        data["description"] = text
    return data


def parse_enum_entry(element: ET.Element) -> Dict[str, Any]:
    attrs = clean_attributes(element)
    entry: Dict[str, Any] = {}

    name = attrs.pop("name", None)
    if name:
        entry["name"] = name

    value = attrs.pop("value", None)
    if value is not None:
        try:
            entry["value"] = int(value, 0)
        except ValueError:
            entry["value"] = value

    if attrs:
        entry.update(attrs)

    description = element.find("description")
    if description is not None:
        text = normalize_text(description.text)
        if text:
            entry["description"] = text

    deprecated = parse_deprecated(element)
    if deprecated:
        entry["deprecated"] = deprecated

    if element.find("wip") is not None:
        entry["wip"] = True

    params = [parse_param(child) for child in element.findall("param")]
    if params:
        entry["params"] = params

    return entry


def parse_enum(element: ET.Element) -> Dict[str, Any]:
    attrs = clean_attributes(element)
    enum: Dict[str, Any] = {}

    name = attrs.pop("name", None)
    if name:
        enum["name"] = name
    if attrs:
        enum.update(attrs)

    description = element.find("description")
    if description is not None:
        text = normalize_text(description.text)
        if text:
            enum["description"] = text

    deprecated = parse_deprecated(element)
    if deprecated:
        enum["deprecated"] = deprecated

    if element.find("wip") is not None:
        enum["wip"] = True

    entries = [parse_enum_entry(child) for child in element.findall("entry")]
    enum["entries"] = entries
    return enum


def parse_field(element: ET.Element, *, extension: bool) -> Dict[str, Any]:
    attrs = clean_attributes(element)
    field: Dict[str, Any] = {}

    name = attrs.pop("name", None)
    if name:
        field["name"] = name

    field_type = attrs.pop("type", None)
    if field_type:
        field["type"] = field_type

    if attrs:
        field.update(attrs)

    text = normalize_text(element.text)
    if text:
        field["description"] = text

    deprecated = parse_deprecated(element)
    if deprecated:
        field["deprecated"] = deprecated

    if element.find("wip") is not None:
        field["wip"] = True

    if extension:
        field["extension"] = True

    return field


def parse_message(element: ET.Element) -> Dict[str, Any]:
    attrs = clean_attributes(element)
    message: Dict[str, Any] = {}

    name = attrs.pop("name", None)
    if name:
        message["name"] = name

    message_id = attrs.pop("id", None)
    if message_id is not None:
        try:
            message["id"] = int(message_id, 0)
        except ValueError:
            message["id"] = message_id

    if attrs:
        message.update(attrs)

    description = element.find("description")
    if description is not None:
        text = normalize_text(description.text)
        if text:
            message["description"] = text

    deprecated = parse_deprecated(element)
    if deprecated:
        message["deprecated"] = deprecated

    if element.find("wip") is not None:
        message["wip"] = True

    fields: List[Dict[str, Any]] = []
    in_extensions = False
    for child in element:
        if child.tag == "extensions":
            in_extensions = True
        elif child.tag == "field":
            fields.append(parse_field(child, extension=in_extensions))

    message["fields"] = fields
    return message


def parse_enums(root: ET.Element) -> List[Dict[str, Any]]:
    return [parse_enum(enum) for enum in root.findall("enum")]


def parse_messages(root: ET.Element) -> List[Dict[str, Any]]:
    return [parse_message(message) for message in root.findall("message")]


def dedupe(items: List[Dict[str, Any]], key_fn) -> List[Dict[str, Any]]:
    """Keep first occurrence of each key."""
    seen = set()
    unique: List[Dict[str, Any]] = []
    for item in items:
        key = key_fn(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def mavlink_to_flat(root: ET.Element) -> Dict[str, Any]:
    """Transform expanded MAVLink XML into a flat JSON structure."""
    data: Dict[str, Any] = {"enums": [], "messages": []}

    for child in root:
        if child.tag == "version" and "version" not in data:
            text = normalize_text(child.text)
            if text:
                try:
                    data["version"] = int(text, 0)
                except ValueError:
                    data["version"] = text
        elif child.tag == "dialect" and "dialect" not in data:
            text = normalize_text(child.text)
            if text:
                try:
                    data["dialect"] = int(text, 0)
                except ValueError:
                    data["dialect"] = text
        elif child.tag == "enums":
            data["enums"].extend(parse_enums(child))
        elif child.tag == "messages":
            data["messages"].extend(parse_messages(child))

    data["enums"] = dedupe(data["enums"], key_fn=lambda item: item.get("name"))
    data["messages"] = dedupe(
        data["messages"], key_fn=lambda item: (item.get("id"), item.get("name"))
    )

    return data


def expand_includes(element: ET.Element, current_file: Path, stack: List[Path]) -> None:
    """Inline <include> tags by splicing in the referenced file's children."""
    new_children = []
    for child in list(element):
        if child.tag == "include":
            target = (child.text or "").strip()
            if not target:
                continue

            include_path = (current_file.parent / target).resolve()
            included_root = load_and_expand(include_path, stack)
            # Insert the included file's children where the <include> tag sat.
            new_children.extend(list(included_root))
        else:
            expand_includes(child, current_file, stack)
            new_children.append(child)

    element[:] = new_children


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate a MAVLink XML dialect (expanding <include>) to JSON.",
    )
    parser.add_argument("xml_file", help="Path to the root MAVLink XML file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    xml_path = Path(args.xml_file).resolve()
    if not xml_path.exists():
        sys.exit(f"File not found: {xml_path}")

    try:
        root = load_and_expand(xml_path, stack=[])
    except Exception as exc:
        sys.exit(f"Failed to process includes: {exc}")

    flat = mavlink_to_flat(root)
    json.dump(flat, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
