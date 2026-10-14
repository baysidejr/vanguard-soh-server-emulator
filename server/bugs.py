"""In-game bug reports (/bug opens the client's Bug Report window, VGUIBugReport.xml).

Submit sends zone 0x4aa {wstr description, i32 category, i32 severity, i32 reproducibility};
the indexes follow the client's name tables (strings at 0x1072720..0x1072d90). The server
keeps the reports in bug_reports.json (not committed) for the content editor."""
import json
import os
import storage
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


# The client's Quest Feedback window (VGUIBugReport.xml "Quest Feedback"): Accept sends 0x4ab
# {i32 quest id (-1 when the window was opened by the server's toggle), wstr comments, i32
# challenge, i32 reward, i32 lore, i32 confusion, i32 friends needed, i32 fun grade}.
# 0x4ad {wstr, i32} is meant to open it but shows nothing, so the server toggles the window.
QUEST_FEEDBACK = 0x4AB
CHALLENGE = ["Too easy", "Just right", "Too hard"]
AMOUNT = ["Too little", "Just right", "Too much"]
CONFUSION = ["Too confusing", "Just right", "Too much detail"]
FRIENDS = ["None", "One", "Two", "Three", "Four", "Five", "Six+"]
FUN = ["A - Excellent", "B - Average", "C - Below average", "F - Unacceptable"]


def parse_quest_feedback(data):
    qid = struct.unpack_from("<i", data, 0)[0]
    end = 4
    while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
        end += 2
    text = data[4:end].decode("utf-16-le", "replace")
    ch, rw, lo, co, fr, fu = struct.unpack_from("<6i", data, end + 2)
    return {"quest_id": qid, "comments": text, "challenge": _name(CHALLENGE, ch, "-"),
            "reward": _name(AMOUNT, rw, "-"), "lore": _name(AMOUNT, lo, "-"),
            "confusion": _name(CONFUSION, co, "-"), "friends_needed": _name(FRIENDS, fr, "-"),
            "fun": _name(FUN, fu, "-")}


# /report <name>: 0x4ac {i32 line count, wstr reported name, then per chat line {wstr text,
# i32 channel, u16}} (FUN_00601b90 -> FUN_0063d2c0, recent lines from the chat window; the
# client pads the message with stale bytes after the last line). The server answers with
# notice 0x0e {i16 code}: 149 PlayerReportSubmitted, 150 CantSubmitPlayerReport, 148
# WaitLongerToSubmitPlayerReport (switch FUN_0061d530, code = table entry + 1).
PLAYER_REPORT = 0x4AC
REPORT_SUBMITTED, REPORT_FAILED, REPORT_WAIT = 149, 150, 148
MAX_REPORT_LINES = 200


def _wstr(data, pos):
    end = pos
    while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
        end += 2
    if end + 1 >= len(data):
        raise struct.error("unterminated string")
    return data[pos:end].decode("utf-16-le", "replace"), end + 2


def parse_player_report(data):
    count = struct.unpack_from("<i", data, 0)[0]
    name, pos = _wstr(data, 4)
    lines = []
    for _ in range(max(0, min(count, MAX_REPORT_LINES))):
        text, pos = _wstr(data, pos)
        channel = struct.unpack_from("<i", data, pos)[0]
        pos += 6
        lines.append({"channel": channel, "text": text})
    return {"reported": name, "chat": lines}


def _name(table, i, unknown):
    return table[i] if 0 <= i < len(table) else unknown


def parse(data):
    """0x4aa payload -> report dict (without who/where)."""
    end = 0
    while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
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
    storage.write_json_atomic(path, reports, ensure_ascii=False)
    return report["id"]
