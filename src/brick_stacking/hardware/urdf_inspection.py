"""Inspect XML without loading meshes, installing SDKs or touching hardware."""
from pathlib import Path
import xml.etree.ElementTree as ET


def inspect_urdf(path):
    root = ET.fromstring(Path(path).read_text(encoding="utf-8"))
    if root.tag != "robot":
        raise ValueError("not a URDF robot")
    joints = []
    for element in root.findall("joint"):
        limit, mimic = element.find("limit"), element.find("mimic")
        parent, child = element.find("parent"), element.find("child")
        joints.append({"name": element.get("name"), "type": element.get("type"),
            "parent": parent.get("link") if parent is not None else None,
            "child": child.get("link") if child is not None else None,
            "declared_limits": dict(limit.attrib) if limit is not None else None,
            "mimic": dict(mimic.attrib) if mimic is not None else None})
    return {"robot": root.get("name"), "link_count": len(root.findall("link")),
            "joints": joints, "hardware_match_verified": False,
            "notice": "Declared model geometry is not measured installation or certified hardware limits."}
