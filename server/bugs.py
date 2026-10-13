"""In-game bug reports (/bug opens the client's Bug Report window, VGUIBugReport.xml).

Submit sends zone 0x4aa {wstr description, i32 category, i32 severity, i32 reproducibility};
the indexes follow the client's name tables (strings at 0x1072720..0x1072d90). The server
keeps the reports in bug_reports.json (not committed) for the content editor."""
import json
import os
import struct
import time

SUBMIT = 0x4AA
CATEGORIES = [
    "Graphics: Animation", "Graphics: Character", "Graphics: Environment", "Graphics: Flora",
    "Graphics: Models", "Graphics: Particle Effects", "Graphics: Structures & Interiors",
    "Graphics: Texturing", "Graphics: Other", "Gameplay: Ability", "Gameplay: Adventuring",
    "Gameplay: Combat", "Gameplay: Crafting", "Gameplay: Death", "Gameplay: Difficulty",
    "Gameplay: Diplomacy", "Gameplay: Grouping", "Gameplay: Harvesting", "Gameplay: Inventory",
    "Gameplay: Journal", "Gameplay: Mounts", "Gameplay: Pathing", "Gameplay: Placement",
    "Gameplay: Quest", "Gameplay: Region", "Gameplay: Rewards", "Gameplay: Trade", "Gameplay: Other",
    "Sound Effects: General", "Sound Effects: Environment", "Sound Effects: Music",
    "User Interface (Default)", "User Interface (Customized)", "Other"]
SEVERITIES = ["Severe (e.g. Exploitable)", "Standard", "Minor (e.g. Cosmetic)"]
REPRODUCIBILITY = ["Every time", "Some of the time", "Only seen once"]


def _name(table, i, unknown):
    return table[i] if 0 <= i < len(table) else unknown


def parse(data):
    """0x4aa payload -> report dict (without who/where)."""
    end = 0
    while data[end:end + 2] != b"\0\0":
        end += 2
    text = data[:end].decode("utf-16-le", "replace")
    cat, sev, rep = struct.unpack_from("<iii", data, end + 2)
    return {"description": text, "category": _name(CATEGORIES, cat, "Unknown Category"),
            "severity": _name(SEVERITIES, sev, "Unknown Severity"),
            "reproducibility": _name(REPRODUCIBILITY, rep, "Unknown Reproducibility")}


def save(path, report):
    reports = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            reports = json.load(f)
    report = dict(report, id=len(reports) + 1, time=int(time.time()))
    reports.append(report)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2, ensure_ascii=False)
    return report["id"]
