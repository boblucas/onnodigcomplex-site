#!/usr/bin/env python3
"""Extract compact playback data from MuseScore archives for the canon essay."""

from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from fractions import Fraction
from pathlib import Path


SOURCE = Path("/home/bob/programming/musescore_backup")
OUTPUT = Path(__file__).resolve().parents[1] / "posts" / "canon-data.json"

SCORES = [
    ("fly", "Fly me to the moon", "fly-me-to-the-moon-canon.mscz", 73),
    ("chromatic", "Little chromatic canon at the major 2nd", "little-chromatic-canon-at-the-major-2nd.mscz", 38),
    ("autumn", "Canon based on Autumn leaves", "canon-based-on-autumn-leaves-at-a-syncopated-time-distance.mscz", 98),
    ("inversion", "Canons in inversion on shared harmony", "canons-in-inversion-on-shared-harmony-1-of-4.mscz", 84),
    ("slowboat", "On a slow boat to China", "on-a-slow-boat-to-china-augmented-inversion-canons.mscz", 32),
    ("retrograde", "8 more canons on a shared harmony, no. 8", "8-more-canons-on-a-shared-harmony-revised.mscz", 40),
    ("table", "Canon a 4, retrograde inversion & directus", "canon-a-4-retrograde-inversion-derectus.mscz", 80),
    ("intervals", "8 canons at each interval", "8-canons-at-each-interval-on-the-same-harmony.mscz", 40),
    ("fugue", "Fugue in G minor", "fugue-in-g-minor-with-performance.mscz", 40),
    ("double", "Double canon", "double-canon.mscz", 36),
    ("doublemod", "Double modulating canons", "double-modulating-canons-of-different-modulations.mscz", 48),
    ("phasing", "Double phasing modulation canon", "double-phasing-modulation-canon.mscz", 144),
    ("vitam", "Vitam et Mortem", "muse-sounds-40-test-performance-vitam-et-mortem-a-modulation-canon-in-augmentation.mscz", 48),
    ("doublemod2", "Double modulation canon no. 2", "double-modulation-canon-no2.mscz", 48),
    ("multi", "Infinite inverted augmented multi-modulation multi-canon", "infinite-inverted-augmented-multi-modulation-multi-canon.mscz", 48),
    ("grail", "Infinite modulation canon a 3", "infinite-modulation-canon-a-3-with-2x-and-4x-augmentation(1).mscz", 96),
]

# Logical musical lines. Multiple tracks in one line are timbral doublings,
# not extra contrapuntal voices. Each line points at the dux it projects onto.
VISUALS = {
    "fly": {"start": 1.0, "beats": 72.0, "wrap": 24.0, "meter": 3, "sources": [(1, "dux", "primary")], "lines": [([1], 0, "1"), ([0], 0, "2")], "maps": [{"scale": 1, "offset": 0}, {"scale": 1, "offset": -1}], "bass": [2]},
    "chromatic": {"beats": 38.0, "row_beats": [18.0, 20.0], "pickup": 2.0, "meter": 4, "sources": [(1, "dux", "primary")], "lines": [([1, 3, 6], 0, "1"), ([0, 2, 5], 0, "2")], "bass": [4, 7]},
    "autumn": {"beats": 98.0, "row_beats": [18.0, 16.0, 16.0, 16.0, 16.0, 16.0], "pickup": 2.0, "meter": 4, "swing": 0.6, "sources": [(0, "dux", "primary")], "lines": [([0], 0, "1"), ([1], 0, "2")], "maps": [{"scale": 1, "offset": 0}, {"scale": 1, "offset": -1.5}], "bass": [2]},
    "inversion": {"beats": 84.0, "wrap": 16.0, "meter": 4, "sources": [(2, "dux", "primary")], "lines": [([2, 4, 7, 0], 0, "1"), ([3, 5, 8, 1], 0, "2")], "transforms": [None, "inversion"], "bass": [6, 9, 10]},
    "slowboat": {"beats": 32.0, "wrap": 16.0, "meter": 4, "sources": [(0, "dux", "primary")], "lines": [([0], 0, "1"), ([1], 0, "2")], "transforms": [None, "inversion"], "bass": [2]},
    "retrograde": {"sources": [(1, "dux", "primary")], "lines": [([1], 0, "1"), ([0], 0, "2")], "bass": [2]},
    "table": {"start": 16.0, "beats": 64.0, "wrap": 16.0, "meter": 4, "split_source_bars": True, "sources": [(0, "vierkant", "primary")], "lines": [([0], 0, "1"), ([1], 0, "2"), ([2], 0, "3"), ([3], 0, "4")], "directions": ["right", "left", "down", "up"], "traversals": [
        {"bars": list(range(16)), "reverse": False},
        {"bars": list(reversed(range(16))), "reverse": True},
        {"bars": [row * 4 + column for column in range(4) for row in range(4)], "reverse": False},
        {"bars": [row * 4 + column for column in reversed(range(4)) for row in reversed(range(4))], "reverse": True},
    ], "bass": [4]},
    "intervals": {"sources": [(1, "dux", "primary")], "lines": [([1], 0, "1"), ([0], 0, "2")], "bass": [2]},
    "fugue": {"sources": [(0, "dux A", "primary"), (3, "dux B", "primary")], "lines": [([0], 0, "A1"), ([1, 4], 0, "A2"), ([2, 5], 0, "A3"), ([3], 1, "B")], "bass": []},
    "double": {"beats": 70.0, "repeat_start": 4.0, "repeat_beats": 32.0, "repeat_count": 2, "repeat_tail": 2.0, "source_start": 4.0, "display_beats": 32.0, "display_offset": -4.0, "wrap": 16.0, "meter": 4, "sources": [(0, "dux A", "primary"), (3, "dux B", "primary")], "lines": [([1], 0, "A1"), ([0], 0, "A2"), ([2], 1, "B1"), ([3], 1, "B2")], "maps": [{"scale": 1, "offset": -8, "modulo": 32}, {"scale": 1, "offset": -4, "modulo": 32}, {"scale": 1, "offset": -8, "modulo": 32}, {"scale": 1, "offset": -4, "modulo": 32}], "bass": []},
    "doublemod": {"sources": [(0, "dux A", "primary"), (2, "dux B", "primary")], "lines": [([0], 0, "A1"), ([1], 0, "A2"), ([2], 1, "B1"), ([3], 1, "B2")], "bass": []},
    "phasing": {"beats": 144.0, "meter": 4, "source_beats": [20.0, 28.0], "sources": [(0, "dux A · 5", "primary"), (2, "dux B · 7", "primary")], "lines": [([1], 0, "A1"), ([0], 0, "A2"), ([3], 1, "B1"), ([2], 1, "B2")], "maps": [{"scale": 1, "offset": -4, "modulo": 20}, {"scale": 1, "offset": 0, "modulo": 20}, {"scale": 1, "offset": -4, "modulo": 28}, {"scale": 1, "offset": 0, "modulo": 28}], "bass": []},
    "vitam": {"meter": 4, "source_beats": [16.0], "sources": [(2, "dux · 4", "primary")], "lines": [([2, 3], 0, "1×"), ([0, 1], 0, "2×")], "maps": [{"scale": 1, "offset": 0, "modulo": 16}, {"scale": 0.5, "offset": 0, "modulo": 16}], "transforms": [None, "inversion"], "bass": [4, 5]},
    "doublemod2": {"sources": [(0, "dux A", "primary"), (2, "dux B", "primary")], "lines": [([0], 0, "A1"), ([1], 0, "A2"), ([2], 1, "B1"), ([3, 4], 1, "B2")], "bass": []},
    "multi": {"beats": 48.0, "meter": 4, "source_beats": [24.0, 24.0], "sources": [(0, "dux A · 6", "primary"), (1, "dux B · 6", "primary")], "lines": [([0], 0, "A1"), ([2], 0, "A2"), ([1], 1, "B1"), ([3], 1, "B2")], "maps": [{"scale": 1, "offset": 0, "modulo": 24}, {"scale": 0.5, "offset": 0, "modulo": 24}, {"scale": 1, "offset": 0, "modulo": 24}, {"scale": 0.5, "offset": -4, "modulo": 24}], "transforms": [None, "inversion", None, "inversion"], "bass": []},
    "grail": {"beats": 96.0, "meter": 4, "source_beats": [24.0], "sources": [(0, "dux · 6", "primary")], "lines": [([0], 0, "1×"), ([2, 4], 0, "2×"), ([1, 3], 0, "4×")], "maps": [{"scale": 1, "offset": 0, "modulo": 24}, {"scale": 0.5, "offset": 0, "modulo": 24}, {"scale": 0.25, "offset": 0, "modulo": 24}], "transforms": [None, "inversion", None], "bass": []},
}

DURATIONS = {
    "longa": 16.0,
    "breve": 8.0,
    "whole": 4.0,
    "half": 2.0,
    "quarter": 1.0,
    "eighth": 0.5,
    "16th": 0.25,
    "32nd": 0.125,
    "64th": 0.0625,
    "128th": 0.03125,
}
TPC_TO_LETTER = {0: 0, 1: 4, 2: 1, 3: 5, 4: 2, 5: 6, 6: 3}
NATURAL_PC = [0, 2, 4, 5, 7, 9, 11]
NATURAL_TPC = [14, 16, 18, 13, 15, 17, 19]
SHARP_ORDER = [3, 0, 4, 1, 5, 2, 6]
FLAT_ORDER = [6, 2, 5, 1, 4, 0, 3]


def text_float(node: ET.Element | None, default: float = 0.0) -> float:
    if node is None or not node.text:
        return default
    try:
        return float(node.text)
    except ValueError:
        return default


def fraction_beats(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return float(Fraction(value)) * 4.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def duration(element: ET.Element, tuplets: dict[str, float], measure_beats: float) -> float:
    kind = element.findtext("durationType", "quarter")
    value = measure_beats if kind == "measure" else DURATIONS.get(kind, 1.0)
    dots = int(element.findtext("dots", "0") or 0)
    value *= sum(0.5**index for index in range(dots + 1))
    tuplet_id = element.findtext("Tuplet")
    if tuplet_id:
        value *= tuplets.get(tuplet_id, 1.0)
    return value


def diatonic_pitch(pitch: int, tpc: int | None, key_signature: int = 0) -> float:
    if tpc is None:
        letter = min(range(7), key=lambda index: abs((pitch % 12) - NATURAL_PC[index]))
    else:
        letter = TPC_TO_LETTER[tpc % 7]
    octave = round((pitch - NATURAL_PC[letter]) / 12)
    result = octave * 7 + letter
    if tpc is not None:
        alteration = round((tpc - NATURAL_TPC[letter]) / 7)
        key_order = SHARP_ORDER if key_signature > 0 else FLAT_ORDER
        key_alteration = (1 if key_signature > 0 else -1) if letter in key_order[:abs(key_signature)] else 0
        result += (alteration - key_alteration) * 0.5
    return result


def main_score_xml(archive: Path) -> bytes:
    with zipfile.ZipFile(archive) as bundle:
        candidates = [name for name in bundle.namelist() if name.endswith(".mscx") and not name.startswith("Excerpts/")]
        if not candidates:
            raise RuntimeError(f"No score in {archive}")
        name = max(candidates, key=lambda candidate: bundle.getinfo(candidate).file_size)
        return bundle.read(name)


def merge_tied_notes(notes: list[dict], rest_times: dict[int, set[float]]) -> list[dict]:
    """Turn MuseScore's notated tie fragments into logical note events."""
    merged: list[dict] = []
    open_ties: dict[tuple[int, int], dict] = {}

    for original in notes:
        note = dict(original)
        tie_start = note.pop("_tie_start", False)
        tie_end = note.pop("_tie_end", False)
        key = (note["v"], note["p"])

        if tie_end and key in open_ties:
            target = open_ties[key]
            target["d"] = round(max(target["t"] + target["d"], note["t"] + note["d"]) - target["t"], 4)
            if not tie_start:
                del open_ties[key]
            continue

        merged.append(note)
        if tie_start:
            open_ties[key] = note

    # Rests inside an entered voice occupy a motif event; introductory rests do not.
    voices = {note["v"] for note in merged}
    indices: dict[int, dict[float, int]] = {}
    for voice in voices:
        attacks = {note["t"] for note in merged if note["v"] == voice}
        first_attack = min(attacks)
        events = attacks | {time for time in rest_times.get(voice, set()) if time >= first_attack}
        indices[voice] = {time: index for index, time in enumerate(sorted(events))}
    for note in merged:
        note["i"] = indices[note["v"]][note["t"]]
    return merged


def parse_staff(staff: ET.Element, clip_beats: float) -> list[dict]:
    notes: list[dict] = []
    rest_times: dict[int, set[float]] = {}
    measure_start = 0.0
    signature = (4, 4)
    key_signature = 0

    for measure in staff.findall("Measure"):
        key_sig = measure.find(".//KeySig")
        if key_sig is not None:
            key_signature = int(key_sig.findtext("accidental", str(key_signature)))
        time_sig = measure.find(".//TimeSig")
        if time_sig is not None:
            signature = (int(time_sig.findtext("sigN", str(signature[0]))), int(time_sig.findtext("sigD", str(signature[1]))))
        measure_beats = signature[0] * 4.0 / signature[1]
        if measure.get("len"):
            measure_beats = fraction_beats(measure.get("len"))

        voices = measure.findall("voice")
        # MuseScore 2 stored the primary voice directly inside Measure.
        if not voices and measure.find("Chord") is not None:
            voices = [measure]
        furthest = measure_start
        for voice_index, voice in enumerate(voices):
            cursor = measure_start
            tuplets: dict[str, float] = {}
            for child in voice:
                if child.tag == "Tuplet":
                    actual = text_float(child.find("actualNotes"), 1.0)
                    normal = text_float(child.find("normalNotes"), 1.0)
                    tuplets[child.get("id", "")] = normal / actual if actual else 1.0
                    continue
                if child.tag == "location":
                    cursor += fraction_beats(child.findtext("fractions"))
                    continue
                if child.tag not in {"Chord", "Rest"}:
                    continue
                length = duration(child, tuplets, measure_beats)
                if child.tag == "Rest" and cursor < clip_beats:
                    rest_times.setdefault(voice_index, set()).add(round(cursor, 4))
                if child.tag == "Chord" and cursor < clip_beats:
                    chord_notes = child.findall("Note")
                    for note in chord_notes:
                        pitch = int(note.findtext("pitch", "60"))
                        tpc_text = note.findtext("tpc")
                        tpc = int(tpc_text) if tpc_text and re.fullmatch(r"-?\d+", tpc_text) else None
                        tie_spanners = [item for item in note.findall("Spanner") if item.get("type") == "Tie"]
                        notes.append({
                            "t": round(cursor, 4),
                            "d": round(min(length, clip_beats - cursor), 4),
                            "p": pitch,
                            "y": diatonic_pitch(pitch, tpc, key_signature),
                            "i": 0,
                            "v": voice_index,
                            "_tie_start": note.find("Tie") is not None or any(item.find("Tie") is not None for item in tie_spanners),
                            "_tie_end": note.find("endSpanner") is not None or any(item.find("prev") is not None for item in tie_spanners),
                        })
                cursor += length
                furthest = max(furthest, cursor)
        measure_start += measure_beats
        if measure_start >= clip_beats:
            break
    return merge_tied_notes(notes, rest_times)


def parse_score(key: str, title: str, filename: str, clip_beats: int) -> dict:
    xml = main_score_xml(SOURCE / filename)
    root = ET.fromstring(xml)
    score = root.find("Score")
    if score is None:
        raise RuntimeError(f"No Score node in {filename}")
    visual = VISUALS[key]
    staffs = [parse_staff(staff, clip_beats) for staff in score.findall("Staff")]
    staffs = [staff for staff in staffs if staff]
    if not staffs:
        raise RuntimeError(f"No notes parsed from {filename}")
    start = visual.get("start", 0.0)
    if start:
        trimmed = []
        for staff in staffs:
            clipped = []
            for original in staff:
                note_end = original["t"] + original["d"]
                if note_end <= start:
                    continue
                note = dict(original)
                note["t"] = round(max(0.0, note["t"] - start), 4)
                note["d"] = round(note_end - max(original["t"], start), 4)
                clipped.append(note)
            trimmed.append(clipped)
        staffs = trimmed
    else:
        first = min(note["t"] for staff in staffs for note in staff)
        if first:
            for staff in staffs:
                for note in staff:
                    note["t"] = round(note["t"] - first, 4)
    if visual.get("repeat_count", 1) > 1:
        repeat_start = visual.get("repeat_start", 0.0)
        repeat_beats = visual["repeat_beats"]
        repeat_end = repeat_start + repeat_beats
        repeated = []
        for staff in staffs:
            prefix = [dict(note) for note in staff if note["t"] < repeat_start]
            section = [note for note in staff if repeat_start <= note["t"] < repeat_end]
            copies = prefix
            for repetition in range(visual["repeat_count"]):
                target_start = repeat_start + repetition * repeat_beats
                for original in section:
                    note = dict(original)
                    note["t"] = round(target_start + original["t"] - repeat_start, 4)
                    copies.append(note)
            tail_beats = visual.get("repeat_tail", 0.0)
            if tail_beats:
                target_start = repeat_start + visual["repeat_count"] * repeat_beats
                for original in section:
                    source_start = max(original["t"], repeat_start)
                    source_end = min(original["t"] + original["d"], repeat_start + tail_beats)
                    if source_end <= source_start:
                        continue
                    note = dict(original)
                    note["t"] = round(target_start + source_start - repeat_start, 4)
                    note["d"] = round(source_end - source_start, 4)
                    copies.append(note)
            repeated.append(sorted(copies, key=lambda note: (note["t"], note["v"], note["p"])))
        staffs = repeated
    bpm = 90
    tempo = score.find(".//Tempo/tempo")
    if tempo is not None:
        bpm = round(text_float(tempo, 1.5) * 60)
    end = visual.get("beats", max(note["t"] + note["d"] for staff in staffs for note in staff))
    sources = [{"track": track, "label": label, "role": role} for track, label, role in visual["sources"]]
    if visual.get("split_source_bars"):
        sources[0]["split_bars"] = visual["meter"]
    if "source_beats" in visual:
        for source, beats in zip(sources, visual["source_beats"]):
            source["beats"] = beats
            source["wrap"] = beats
    if "source_start" in visual:
        for source in sources:
            source["start"] = visual["source_start"]
    lines = []
    for index, (tracks, source, label) in enumerate(visual["lines"]):
        line = {"tracks": tracks, "source": source, "label": label}
        if "maps" in visual:
            line["map"] = visual["maps"][index]
        if "traversals" in visual:
            line["traversal"] = visual["traversals"][index]
        if "directions" in visual:
            line["direction"] = visual["directions"][index]
        if "transforms" in visual and visual["transforms"][index]:
            line["transform"] = visual["transforms"][index]
        lines.append(line)
    if visual["bass"]:
        sources.append({"track": visual["bass"][0], "label": "vrije bas", "role": "bass"})
        lines.append({"tracks": visual["bass"], "source": len(sources) - 1, "label": "bas"})
    visual_output = {"sources": sources, "lines": lines}
    for setting in ("wrap", "meter", "row_beats", "pickup", "swing", "display_beats", "display_offset"):
        if setting in visual:
            visual_output[setting] = visual[setting]
    return {"id": key, "title": title, "bpm": max(48, min(bpm, 180)), "beats": round(end, 3), "staffs": staffs,
            "visual": visual_output}


def main() -> None:
    data = [parse_score(*score) for score in SCORES]
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    note_count = sum(len(staff) for score in data for staff in score["staffs"])
    print(f"Wrote {len(data)} scores / {note_count} notes to {OUTPUT}")


if __name__ == "__main__":
    main()
