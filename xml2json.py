#!/usr/bin/env python3
"""Expand MAVLink XML dialects (with includes) into JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List
import xml.etree.ElementTree as ET


SOURCE_KEY = "_source"


def mark_source(element: ET.Element, source: Path) -> None:
    """Annotate an element tree with the file it came from."""
    element.attrib[SOURCE_KEY] = str(source)
    for child in element:
        mark_source(child, source)


def element_to_obj(element: ET.Element) -> dict:
    """Convert an ElementTree node (with source annotation) to a dict."""
    attrs = dict(element.attrib)
    source = attrs.pop(SOURCE_KEY, None)

    obj: dict = {"tag": element.tag}
    if attrs:
        obj["attributes"] = attrs

    text = (element.text or "").strip()
    if text:
        obj["text"] = text

    children = [element_to_obj(child) for child in element]
    if children:
        obj["children"] = children

    return obj


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

    json.dump(element_to_obj(root), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
