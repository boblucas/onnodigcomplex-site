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
INVERSION_REPEAT_MAP = {"segments": [
    {"start": 0.0, "end": 44.0, "source": 0.0},
    {"start": 44.0, "end": 80.0, "source": 4.0},
    {"start": 80.0, "end": 84.0, "source": 44.0},
]}
INVERSION_FOLLOWER_MAP = {"segments": [
    {"start": 8.0, "end": 52.0, "source": 0.0},
    {"start": 52.0, "end": 84.0, "source": 4.0},
]}


def modulation(period: float, label: str, *layers: tuple[float, float]) -> dict:
    return {"period": period, "label": label, "layers": [
        {"semitones": semitones, "y": y} for semitones, y in layers
    ]}


VISUALS = {
    "fly": {"start": 1.0, "beats": 72.0, "wrap": 24.0, "meter": 3, "performance": {"bpm": 120, "offset_beats": 0, "duration": 39.810612, "music_beats": 72, "tempo_map": [{"beat": 0, "bpm": 120}, {"beat": 67, "bpm": 100}, {"beat": 68, "bpm": 90}], "stems": [{"src": "audio/fly_dux.mp3", "tracks": [1]}, {"src": "audio/fly_comes.mp3", "tracks": [0]}, {"src": "audio/fly_bassline.mp3", "tracks": [2]}]}, "sources": [(1, "dux", "primary")], "lines": [([1], 0, "1"), ([0], 0, "2")], "maps": [{"scale": 1, "offset": 0}, {"scale": 1, "offset": -1}], "bass": [2]},
    "chromatic": {"beats": 38.0, "row_beats": [38.0], "pickup": 2.0, "meter": 4, "performance": {"bpm": 120, "offset_beats": 0, "duration": 22.073425, "music_beats": 38, "stems": [{"src": "audio/chromatic_dux.mp3", "tracks": [1, 3, 6]}, {"src": "audio/chromatic_comes.mp3", "tracks": [0, 2, 5]}, {"src": "audio/chromatic_bassline.mp3", "tracks": [4, 7]}]}, "sources": [(1, "dux", "primary")], "lines": [([1, 3, 6], 0, "1"), ([0, 2, 5], 0, "2")], "bass": [4, 7]},
    "autumn": {"beats": 98.0, "row_beats": [18.0, 16.0, 16.0, 16.0, 16.0, 16.0], "pickup": 2.0, "meter": 4, "swing": 0.6, "performance": {"bpm": 120, "offset_beats": 0, "duration": 52.062, "music_beats": 98, "stems": [{"src": "audio/autumn_dux.mp3", "tracks": [0]}, {"src": "audio/autumn_comes.mp3", "tracks": [1]}, {"src": "audio/autumn_bassline.mp3", "tracks": [2]}]}, "sources": [(0, "dux", "primary")], "lines": [([0], 0, "1"), ([1], 0, "2")], "maps": [{"scale": 1, "offset": 0}, {"scale": 1, "offset": -1.5}], "bass": [2]},
    "inversion": {"beats": 84.0, "wrap": 48.0, "meter": 4, "source_beats": [48.0], "source_wraps": [48.0], "source_sections": [[(0.0, 44.0), (80.0, 84.0)]], "source_maps": [INVERSION_REPEAT_MAP], "bass_beats": 48.0, "bass_sections": [(0.0, 44.0), (80.0, 84.0)], "bass_map": INVERSION_REPEAT_MAP, "sources": [(4, "dux", "primary")], "lines": [([4, 2, 7, 0], 0, "1"), ([5, 3, 8, 1], 0, "2")], "maps": [INVERSION_REPEAT_MAP, INVERSION_FOLLOWER_MAP], "transforms": [None, "inversion"], "bass": [6, 9, 10]},
    "slowboat": {"beats": 32.0, "wrap": 32.0, "meter": 4, "performance": {"bpm": 150, "offset_beats": 0, "duration": 15.8563, "music_beats": 32, "stems": [{"src": "audio/slowboat_dux.mp3", "tracks": [0]}, {"src": "audio/slowboat_comes.mp3", "tracks": [1]}, {"src": "audio/slowboat_bassline.mp3", "tracks": [2]}]}, "sources": [(0, "dux", "primary")], "lines": [([0], 0, "1"), ([1], 0, "2")], "transforms": [None, "inversion"], "bass": [2]},
    "retrograde": {"variation_set": "more_intervals", "sources": [(1, "dux", "primary")], "lines": [([1], 0, "1"), ([0], 0, "2")], "bass": [2]},
    "table": {"start": 16.0, "beats": 64.0, "wrap": 16.0, "meter": 4, "performance": {"bpm": 120, "offset_beats": 0, "duration": 35.0563, "music_beats": 64, "stems": [{"src": "audio/derectus_voice_1.mp3", "tracks": [0]}, {"src": "audio/derectus_voice_2.mp3", "tracks": [1]}, {"src": "audio/derectus_voice_3.mp3", "tracks": [2]}, {"src": "audio/derectus_voice_4.mp3", "tracks": [3]}]}, "split_source_bars": True, "sources": [(0, "vierkant", "primary")], "lines": [([0], 0, "1"), ([1], 0, "2"), ([2], 0, "3"), ([3], 0, "4")], "directions": ["right", "left", "down", "up"], "traversals": [
        {"bars": list(range(16)), "reverse": False},
        {"bars": list(reversed(range(16))), "reverse": True},
        {"bars": [row * 4 + column for column in range(4) for row in range(4)], "reverse": False},
        {"bars": [row * 4 + column for column in reversed(range(4)) for row in reversed(range(4))], "reverse": True},
    ], "bass": []},
    "intervals": {"variation_set": "intervals", "sources": [(1, "dux", "primary")], "lines": [([1], 0, "1"), ([0], 0, "2")], "bass": [2]},
    "double": {"beats": 70.0, "repeat_start": 4.0, "repeat_beats": 32.0, "repeat_count": 2, "repeat_tail": 2.0, "source_start": 4.0, "display_beats": 32.0, "display_offset": -4.0, "wrap": 16.0, "meter": 4, "performance": {"bpm": 80, "offset_beats": 0, "duration": 55.562425, "music_beats": 70, "stems": [{"src": "audio/double_canon_a1.mp3", "tracks": [1]}, {"src": "audio/double_canon_a2.mp3", "tracks": [0]}, {"src": "audio/double_canon_b1.mp3", "tracks": [2]}, {"src": "audio/double_canon_b2.mp3", "tracks": [3]}]}, "sources": [(0, "dux A", "primary"), (3, "dux B", "primary")], "lines": [([1], 0, "A1"), ([0], 0, "A2"), ([2], 1, "B1"), ([3], 1, "B2")], "maps": [{"scale": 1, "offset": -8, "modulo": 32}, {"scale": 1, "offset": -4, "modulo": 32}, {"scale": 1, "offset": -8, "modulo": 32}, {"scale": 1, "offset": -4, "modulo": 32}], "transforms": ["inversion", None, None, None], "bass": []},
    "doublemod": {"beats": 48.0, "meter": 4, "source_beats": [16.0, 24.0], "modulations": [modulation(16, "−2 ×3", (0, 0), (-2, -1), (-4, -2.5)), modulation(24, "+3 ×2", (0, 0), (3, 2))], "sources": [(0, "dux A · 4", "primary"), (2, "dux B · 6", "primary")], "lines": [([0], 0, "A1"), ([1], 0, "A2"), ([2], 1, "B1"), ([3], 1, "B2")], "maps": [{"scale": 1, "offset": 0, "modulo": 16}, {"scale": 1, "offset": -8, "modulo": 16}, {"scale": 1, "offset": 0, "modulo": 24}, {"scale": 1, "offset": -8, "modulo": 24}], "bass": []},
    "phasing": {"beats": 144.0, "meter": 4, "source_beats": [20.0, 28.0], "modulations": [modulation(20, "+1 ×8", (0, 0), (1, .5), (2, 1), (3, 1.5), (4, 2), (5, 2.5), (6, 3), (7, 3.5)), modulation(28, "−1 ×6", (0, 0), (-1, -.5), (-2, -1), (-3, -1.5), (-4, -2), (-5, -2.5))], "sources": [(0, "dux A · 5", "primary"), (2, "dux B · 7", "primary")], "lines": [([1], 0, "A1"), ([0], 0, "A2"), ([3], 1, "B1"), ([2], 1, "B2")], "maps": [{"scale": 1, "offset": -4, "modulo": 20}, {"scale": 1, "offset": 0, "modulo": 20}, {"scale": 1, "offset": -4, "modulo": 28}, {"scale": 1, "offset": 0, "modulo": 28}], "bass": []},
    "vitam": {"meter": 4, "source_beats": [16.0], "source_repeat_heads": [{"at": 16.0, "semitones": 4, "y": 2.5}], "performance": {"bpm": 110, "offset_beats": 1, "duration": 140.225306, "stems": [{"src": "audio/vitam_dux.mp3", "tracks": [2, 3]}, {"src": "audio/vitam_augmented.mp3", "tracks": [0, 1]}, {"src": "audio/vitam_bassline.mp3", "tracks": [4, 5]}]}, "modulations": [modulation(16, "−4 ×3", (0, 0), (-4, -2.5), (-8, -4.5))], "line_modulations": [modulation(16, "−4 ×3", (0, 0), (-4, -2.5), (-8, -4.5)), modulation(16, "+4 ×3", (0, 0), (4, 2.5), (8, 4.5))], "line_shepards": [{"direction": -1, "octave_y": 7, "cycles": 3}, {"direction": 1, "octave_y": 7, "cycles": 3}], "sources": [(2, "dux · 4", "primary")], "lines": [([2, 3], 0, "1×"), ([0, 1], 0, "2×")], "maps": [{"scale": 1, "offset": 0, "modulo": 16}, {"scale": 0.5, "offset": 0, "modulo": 16}], "transforms": [None, "inversion"], "bass": [4, 5]},
    "doublemod2": {"beats": 48.0, "meter": 4, "source_beats": [24.0, 24.0], "modulations": [modulation(24, "+4 ×2", (0, 0), (4, 2.5)), modulation(24, "+4 ×2", (0, 0), (4, 2.5))], "line_modulations": [modulation(24, "+4 ×2", (0, 0), (4, 2.5)), modulation(24, "0 ×1", (0, 0)), modulation(24, "+4 ×2", (0, 0), (4, 2.5)), modulation(24, "0 ×1", (0, 0))], "sources": [(0, "dux A · 6", "primary"), (2, "dux B · 6", "primary")], "lines": [([0], 0, "A1"), ([1], 0, "A2"), ([2], 1, "B1"), ([3, 4], 1, "B2")], "maps": [{"scale": 1, "offset": 0, "modulo": 24}, {"scale": 0.5, "offset": 0, "modulo": 24}, {"scale": 1, "offset": 0, "modulo": 24}, {"scale": 0.5, "offset": 0, "modulo": 24}], "transforms": [None, "inversion", None, "inversion"], "bass": []},
    "multi": {"beats": 48.0, "meter": 4, "source_beats": [24.0, 24.0], "modulations": [modulation(24, "+4 ×2", (0, 0), (4, 2.5)), modulation(24, "+4 ×2", (0, 0), (4, 2.5))], "line_modulations": [modulation(24, "+4 ×2", (0, 0), (4, 2.5)), modulation(24, "0 ×1", (0, 0)), modulation(24, "+4 ×2", (0, 0), (4, 2.5)), modulation(24, "0 ×1", (0, 0))], "sources": [(0, "dux A · 6", "primary"), (1, "dux B · 6", "primary")], "lines": [([0], 0, "A1"), ([2], 0, "A2"), ([1], 1, "B1"), ([3], 1, "B2")], "maps": [{"scale": 1, "offset": 0, "modulo": 24}, {"scale": 0.5, "offset": 0, "modulo": 24}, {"scale": 1, "offset": 0, "modulo": 24}, {"scale": 0.5, "offset": -4, "modulo": 24}], "transforms": [None, "inversion", None, "inversion"], "bass": []},
    "grail": {"beats": 96.0, "meter": 4, "source_beats": [24.0], "modulations": [modulation(24, "+4 ×4", (0, 0), (4, 2.5), (8, 4.5), (12, 7))], "line_modulations": [modulation(24, "+4 ×4", (0, 0), (4, 2.5), (8, 4.5), (12, 7)), modulation(24, "−4 ×2", (0, 0), (-4, -2.5)), modulation(24, "0 ×1", (0, 0))], "sources": [(0, "dux · 6", "primary")], "lines": [([0], 0, "1×"), ([2, 4], 0, "2×"), ([1, 3], 0, "4×")], "maps": [{"scale": 1, "offset": 0, "modulo": 24}, {"scale": 0.5, "offset": 0, "modulo": 24}, {"scale": 0.25, "offset": 0, "modulo": 24}], "transforms": [None, "inversion", None], "bass": []},
}

INTERVAL_LABELS = [
    ("1", "unisono"),
    ("2", "secunde"),
    ("3", "terts"),
    ("4", "kwart"),
    ("5", "kwint"),
    ("6", "sext"),
    ("7", "septiem"),
    ("8", "octaaf"),
]

# Each variation is unfolded into its sounding order. The third canon in
# more_intervals has a two-bar introduction followed by a written repeat;
# the fourth has a one-bar introduction before the ground bass enters.
VARIATION_LAYOUTS = {
    "intervals": [
        {"measure_sections": [(index * 16, index * 16 + 16), (128, 129)], "bpm": 120, "bass_offset_measures": 0}
        for index in range(8)
    ],
    "more_intervals": [
        {"measure_sections": [(0, 17)], "bpm": 115, "bass_offset_measures": 0},
        {"measure_sections": [(17, 34)], "bpm": 115, "bass_offset_measures": 0},
        {"measure_sections": [(34, 44), (36, 42), (44, 45)], "bpm": 75, "bass_offset_measures": 0},
        {"measure_sections": [(45, 63)], "bpm": 57, "bass_offset_measures": 1, "collapse_dux_repeat": True, "line_scales": [1, 1]},
        {"measure_sections": [(63, 80)], "bpm": 115, "bass_offset_measures": 0, "collapse_dux_repeat": True, "line_scales": [1, 0.5]},
        {"measure_sections": [(80, 97)], "bpm": 86, "bass_offset_measures": 0, "collapse_dux_repeat": True, "line_scales": [1, 1]},
        {"measure_sections": [(97, 114)], "bpm": 114, "bass_offset_measures": 0, "nested_inversion": True},
        {"measure_sections": [(114, 131)], "bpm": 114, "bass_offset_measures": 0, "retrograde_line": 1},
    ],
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


def measure_beat_boundaries(staff: ET.Element) -> tuple[list[float], list[float]]:
    boundaries = [0.0]
    meters = []
    signature = (4, 4)
    for measure in staff.findall("Measure"):
        time_sig = measure.find(".//TimeSig")
        if time_sig is not None:
            signature = (int(time_sig.findtext("sigN", str(signature[0]))), int(time_sig.findtext("sigD", str(signature[1]))))
        measure_beats = signature[0] * 4.0 / signature[1]
        if measure.get("len"):
            measure_beats = fraction_beats(measure.get("len"))
        meters.append(measure_beats)
        boundaries.append(boundaries[-1] + measure_beats)
    return boundaries, meters

def extract_staff_sections(staff: list[dict], sections: list[tuple[float, float]]) -> list[dict]:
    """Unfold score sections while preserving each voice's entered rest ordinals."""
    result: list[dict] = []
    cursor = 0.0
    voice_indices: dict[int, int] = {}
    for start, end in sections:
        clipped = [note for note in staff if note["t"] < end and note["t"] + note["d"] > start]
        voice_ranges: dict[int, tuple[int, int]] = {}
        for voice in {note["v"] for note in clipped}:
            indices = [note["i"] for note in clipped if note["v"] == voice]
            voice_ranges[voice] = (min(indices), max(indices))
        for original in clipped:
            note_start = max(original["t"], start)
            note_end = min(original["t"] + original["d"], end)
            voice = original["v"]
            first_index, _ = voice_ranges[voice]
            note = dict(original)
            note["t"] = round(cursor + note_start - start, 4)
            note["d"] = round(note_end - note_start, 4)
            note["i"] = voice_indices.get(voice, 0) + original["i"] - first_index
            result.append(note)
        for voice, (first_index, last_index) in voice_ranges.items():
            voice_indices[voice] = voice_indices.get(voice, 0) + last_index - first_index + 1
        cursor += end - start
    return sorted(result, key=lambda note: (note["t"], note["v"], note["p"]))


def harmonic_bass_notes(staff: list[dict], offset: float = 0.0) -> list[dict]:
    """Reduce the first eight-bar bass cycle to one harmonic anchor per bar."""
    anchors = []
    for bar in range(8):
        start = offset + bar * 4.0
        candidates = [note for note in staff if start <= note["t"] < start + 4.0]
        if not candidates:
            raise RuntimeError(f"No bass anchor found in bar {bar + 1}")
        attack = min(note["t"] for note in candidates)
        source = min((note for note in candidates if note["t"] == attack), key=lambda note: note["p"])
        anchors.append({**source, "t": bar * 4.0, "d": 4.0, "i": bar, "v": 0})
    return anchors

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
    variations = None
    variation_set = visual.get("variation_set")
    if variation_set:
        layouts = VARIATION_LAYOUTS[variation_set]
        score_staffs = score.findall("Staff")
        boundaries, meters = measure_beat_boundaries(score_staffs[0])
        parse_limit = boundaries[max(end for layout in layouts for _, end in layout["measure_sections"])]
        full_staffs = [parse_staff(staff, parse_limit) for staff in score_staffs]
        variations = []
        for index, (short, label) in enumerate(INTERVAL_LABELS):
            layout = layouts[index]
            sections = [(boundaries[start], boundaries[end]) for start, end in layout["measure_sections"]]
            variant_staffs = [extract_staff_sections(staff, sections) for staff in full_staffs]
            beats = round(sum(end - start for start, end in sections), 3)
            first_measure = layout["measure_sections"][0][0]
            meter = meters[first_measure]
            bass_offset = sum(meters[first_measure:first_measure + layout["bass_offset_measures"]])
            variant = {
                "short": short,
                "label": label,
                "bpm": layout["bpm"],
                "beats": beats,
                "meter": meter,
                "bass_offset": bass_offset,
                "staffs": variant_staffs,
            }
            if layout.get("line_transforms"):
                variant["line_transforms"] = layout["line_transforms"]
            if layout.get("nested_inversion"):
                five_measures = meter * 5
                three_measures = meter * 3
                eight_measures = meter * 8
                follower_start = meter * 4
                dux_map = {"segments": [
                    {"start": 0, "end": five_measures, "source": 0},
                    {"start": five_measures, "end": eight_measures, "source": 0, "transform": "inversion"},
                    {"start": eight_measures, "end": eight_measures + five_measures, "source": 0},
                    {"start": eight_measures + five_measures, "end": eight_measures * 2, "source": 0, "transform": "inversion"},
                    {"start": eight_measures * 2, "end": beats, "source": 0},
                ]}
                follower_map = {"segments": [
                    {"start": follower_start, "end": follower_start + five_measures, "source": 0},
                    {"start": follower_start + five_measures, "end": follower_start + eight_measures, "source": 0, "transform": "inversion"},
                    {"start": follower_start + eight_measures, "end": beats, "source": 0},
                ]}
                variant["source_beats"] = [five_measures]
                variant["source_maps"] = [dux_map]
                variant["line_maps"] = [dux_map, follower_map]
                variant["line_transforms"] = [None, "inversion"]
            if "retrograde_line" in layout:
                line_index = layout["retrograde_line"]
                cycle = beats
                variant["line_maps"] = [None, None]
                variant["line_maps"][line_index] = {"scale": -1, "offset": cycle - 0.0001, "modulo": cycle}
                variant["line_transforms"] = [None, None]
                variant["line_transforms"][line_index] = "retrograde"
                variant["line_directions"] = [None, None]
                variant["line_directions"][line_index] = "left"
            if layout.get("collapse_dux_repeat"):
                cycle = meter * 8
                variant["source_beats"] = [cycle]
                variant["source_maps"] = [{"scale": 1, "offset": 0, "modulo": cycle}]
                variant["line_maps"] = [
                    {"scale": scale, "offset": 0, "modulo": cycle}
                    for scale in layout.get("line_scales", [1, 1])
                ]
            variations.append(variant)
        staffs = variations[0]["staffs"]

    bpm = 90
    tempo = score.find(".//Tempo/tempo")
    if tempo is not None:
        bpm = round(text_float(tempo, 1.5) * 60)
    if variations:
        bpm = variations[0]["bpm"]
    end = visual.get("beats", max(note["t"] + note["d"] for staff in staffs for note in staff))
    if variations:
        end = variations[0]["beats"]
    sources = [{"track": track, "label": label, "role": role} for track, label, role in visual["sources"]]
    if visual.get("split_source_bars"):
        sources[0]["split_bars"] = visual["meter"]
    if "source_beats" in visual:
        for source, beats in zip(sources, visual["source_beats"]):
            source["beats"] = beats
            source["wrap"] = beats
    if "source_wraps" in visual:
        for source, wrap in zip(sources, visual["source_wraps"]):
            source["wrap"] = wrap
    if "modulations" in visual:
        for source, modulation in zip(sources, visual["modulations"]):
            source["modulation"] = modulation
    if "source_repeat_heads" in visual:
        for source, repeat_head in zip(sources, visual["source_repeat_heads"]):
            source["repeat_head"] = repeat_head
    if "source_start" in visual:
        for source in sources:
            source["start"] = visual["source_start"]
    if "source_sections" in visual:
        for source, sections in zip(sources, visual["source_sections"]):
            source["sections"] = [{"start": start, "end": end} for start, end in sections]
    if "source_maps" in visual:
        for source, mapping in zip(sources, visual["source_maps"]):
            source["map"] = mapping
    lines = []
    for index, (tracks, source, label) in enumerate(visual["lines"]):
        line = {"tracks": tracks, "source": source, "label": label}
        if "maps" in visual:
            line["map"] = visual["maps"][index]
        if "line_modulations" in visual:
            line["modulation"] = visual["line_modulations"][index]
        if "line_shepards" in visual and index < len(visual["line_shepards"]):
            line["shepard"] = visual["line_shepards"][index]
        if "traversals" in visual:
            line["traversal"] = visual["traversals"][index]
        if "directions" in visual:
            line["direction"] = visual["directions"][index]
        if "transforms" in visual and visual["transforms"][index]:
            line["transform"] = visual["transforms"][index]
        lines.append(line)
    if visual["bass"]:
        bass_source = {"track": visual["bass"][0], "label": "vrije bas", "role": "bass"}
        if variations:
            bass_source.update({
                "label": "harmonische bas · 8",
                "ground_bass": True,
                "notes": harmonic_bass_notes(staffs[visual["bass"][0]], variations[0]["bass_offset"]),
                "beats": 32.0,
            })
        if "bass_beats" in visual:
            bass_source["beats"] = visual["bass_beats"]
        if "bass_sections" in visual:
            bass_source["sections"] = [{"start": start, "end": end} for start, end in visual["bass_sections"]]
        if "bass_map" in visual:
            bass_source["map"] = visual["bass_map"]
        sources.append(bass_source)
        bass_line = {"tracks": visual["bass"], "source": len(sources) - 1, "label": "bas"}
        if variations:
            bass_line["ground_bass"] = True
            bass_line["map"] = {"scale": 1, "offset": 0, "modulo": 32, "start": 0}
        if "bass_map" in visual:
            bass_line["map"] = visual["bass_map"]
        lines.append(bass_line)
    visual_output = {"sources": sources, "lines": lines}
    if "performance" in visual:
        visual_output["performance"] = visual["performance"]
    for setting in ("wrap", "meter", "row_beats", "pickup", "swing", "display_beats", "display_offset"):
        if setting in visual:
            visual_output[setting] = visual[setting]
    output = {"id": key, "title": title, "bpm": max(48, min(bpm, 180)), "beats": round(end, 3), "staffs": staffs,
              "visual": visual_output}
    if variations:
        output["variations"] = variations
    return output


def main() -> None:
    data = [parse_score(*score) for score in SCORES]
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    note_count = sum(len(staff) for score in data for staff in score["staffs"])
    print(f"Wrote {len(data)} scores / {note_count} notes to {OUTPUT}")


if __name__ == "__main__":
    main()
