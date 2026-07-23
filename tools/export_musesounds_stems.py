#!/usr/bin/env python3
"""Render website stems with each score's saved MuseSounds mixer settings."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
MUSESCORE_BACKUP = Path("/home/bob/programming/musescore_backup")
DEFAULT_MUSESCORE = Path(
    "/home/bob/Downloads/MuseScore-Studio-4.7.4.260706075-x86_64.AppImage"
)
DEFAULT_OUTPUT = ROOT / "posts" / "audio"

DURATIONS = {
    "longa": Fraction(16),
    "breve": Fraction(8),
    "whole": Fraction(4),
    "half": Fraction(2),
    "quarter": Fraction(1),
    "eighth": Fraction(1, 2),
    "16th": Fraction(1, 4),
    "32nd": Fraction(1, 8),
    "64th": Fraction(1, 16),
}


@dataclass(frozen=True)
class Preset:
    source: Path
    stems: dict[tuple[str, ...], str]
    arrange: Callable[[bytes], bytes] | None = None
    trim_seconds: float = 0


def event_duration(event: ET.Element) -> Fraction:
    duration = DURATIONS.get(event.findtext("durationType", "quarter"), Fraction(1))
    dots = int(event.findtext("dots", "0") or 0)
    return duration * sum(
        (Fraction(1, 2) ** index for index in range(dots + 1)), Fraction()
    )


def remove_identity_and_spanners(element: ET.Element) -> None:
    for parent in element.iter():
        for child in list(parent):
            if child.tag in {"eid", "linkedTo", "Slur", "Tie", "Spanner"}:
                parent.remove(child)


def two_beat_repeat_head(measure: ET.Element) -> ET.Element:
    tail = copy.deepcopy(measure)
    tail.set("len", "2/4")
    for marker in tail.findall("startRepeat") + tail.findall("endRepeat"):
        tail.remove(marker)

    for voice in tail.findall("voice"):
        elapsed = Fraction()
        finished = False
        for event in list(voice):
            if event.tag in {"Chord", "Rest"}:
                duration = event_duration(event)
                if finished or elapsed + duration > 2:
                    voice.remove(event)
                    continue
                elapsed += duration
                finished = elapsed >= 2
            elif finished:
                voice.remove(event)

    remove_identity_and_spanners(tail)
    return tail


def arrange_derectus(xml: bytes) -> bytes:
    root = ET.fromstring(xml)
    score = root.find("Score")
    if score is None:
        raise RuntimeError("No Score element in derectus canon")

    for staff in score.findall("Staff"):
        measures = staff.findall("Measure")
        if len(measures) < 20:
            raise RuntimeError("Derectus canon has fewer than twenty measures")

        setup = []
        first_voice = measures[0].find("voice")
        if first_voice is not None:
            setup = [
                copy.deepcopy(element)
                for element in first_voice
                if element.tag in {"KeySig", "TimeSig"}
            ]
        destination_voice = measures[4].find("voice")
        if destination_voice is not None:
            for element in reversed(setup):
                remove_identity_and_spanners(element)
                destination_voice.insert(0, element)

        for measure in measures[:4]:
            staff.remove(measure)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def arrange_double_canon(xml: bytes) -> bytes:
    root = ET.fromstring(xml)
    score = root.find("Score")
    if score is None:
        raise RuntimeError("No Score element in Double Canon")

    for staff in score.findall("Staff"):
        measures = staff.findall("Measure")
        if len(measures) < 9:
            raise RuntimeError("Double Canon has fewer than nine measures")

        repeat_head = two_beat_repeat_head(measures[1])
        for measure in measures[9:]:
            staff.remove(measure)
        staff.append(repeat_head)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def arrange_first_eight_measures(xml: bytes) -> bytes:
    root = ET.fromstring(xml)
    score = root.find("Score")
    if score is None:
        raise RuntimeError("No Score element in eight-measure excerpt")

    for staff in score.findall("Staff"):
        measures = staff.findall("Measure")
        if len(measures) < 8:
            raise RuntimeError("Score has fewer than eight measures")
        for measure in measures[8:]:
            staff.remove(measure)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


PRESETS = {
    "double": Preset(
        source=MUSESCORE_BACKUP / "double-canon.mscz",
        stems={
            ("1",): "double_canon_a2.mp3",
            ("2",): "double_canon_a1.mp3",
            ("3",): "double_canon_b1.mp3",
            ("4",): "double_canon_b2.mp3",
        },
        arrange=arrange_double_canon,
    ),
    "fly": Preset(
        source=MUSESCORE_BACKUP / "fly-me-to-the-moon-canon.mscz",
        stems={
            ("1",): "fly_comes.mp3",
            ("2",): "fly_dux.mp3",
            ("3",): "fly_bassline.mp3",
        },
        trim_seconds=0.5,
    ),
    "chromatic": Preset(
        source=MUSESCORE_BACKUP
        / "little-chromatic-canon-at-the-major-2nd-musesounds.mscz",
        stems={
            ("6", "9"): "chromatic_dux.mp3",
            ("5", "8"): "chromatic_comes.mp3",
            ("7", "10", "11"): "chromatic_bassline.mp3",
        },
    ),
    "autumn": Preset(
        source=MUSESCORE_BACKUP
        / "canon-based-on-autumn-leaves-at-a-syncopated-time-distance.mscz",
        stems={
            ("1",): "autumn_dux.mp3",
            ("2",): "autumn_comes.mp3",
            ("3",): "autumn_bassline.mp3",
        },
    ),
    "slowboat": Preset(
        source=MUSESCORE_BACKUP
        / "on-a-slow-boat-to-china-augmented-inversion-canons.mscz",
        stems={
            ("1",): "slowboat_dux.mp3",
            ("2",): "slowboat_comes.mp3",
            ("3",): "slowboat_bassline.mp3",
        },
        arrange=arrange_first_eight_measures,
    ),
    "derectus": Preset(
        source=MUSESCORE_BACKUP
        / "canon-a-4-retrograde-inversion-derectus.mscz",
        stems={
            ("1",): "derectus_voice_1.mp3",
            ("2",): "derectus_voice_2.mp3",
            ("3",): "derectus_voice_3.mp3",
            ("4", "5"): "derectus_voice_4.mp3",
        },
        arrange=arrange_derectus,
    ),
}


def stem_audio_settings(raw: bytes, part_ids: tuple[str, ...]) -> bytes:
    settings = json.loads(raw)
    for track in settings["tracks"]:
        active = track.get("partId") in part_ids
        track["soloMuteState"] = {"mute": False, "solo": False}
        if not active:
            track["out"]["volumeDb"] = -60
            for send in track["out"].get("auxSends", []):
                send["signalAmount"] = 0
    return json.dumps(settings, indent=4).encode()


def stem_score(
    source: Path, preset: Preset, part_ids: tuple[str, ...], destination: Path
) -> None:
    with zipfile.ZipFile(source) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}

    score_names = [name for name in files if name.endswith(".mscx")]
    if len(score_names) != 1:
        raise RuntimeError(f"Expected one MSCX score, found {score_names}")
    if preset.arrange:
        score_name = score_names[0]
        files[score_name] = preset.arrange(files[score_name])
    files["audiosettings.json"] = stem_audio_settings(
        files["audiosettings.json"], part_ids
    )

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)


def render_stem(
    preset: Preset,
    musescore: Path,
    ffmpeg: str,
    output: Path,
    part_ids: tuple[str, ...],
    filename: str,
) -> None:
    with tempfile.TemporaryDirectory(prefix="musesounds-stem-") as temp_dir:
        temp = Path(temp_dir)
        score = temp / f"parts-{'-'.join(part_ids)}.mscz"
        stem_score(preset.source, preset, part_ids, score)
        destination = output / filename

        if not preset.trim_seconds:
            subprocess.run(
                [str(musescore), "-b", "320", "-o", str(destination), str(score)],
                check=True,
            )
            return

        wave = temp / f"parts-{'-'.join(part_ids)}.wav"
        subprocess.run([str(musescore), "-o", str(wave), str(score)], check=True)
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(wave),
                "-af",
                f"atrim=start={preset.trim_seconds},asetpts=PTS-STARTPTS",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "320k",
                str(destination),
            ],
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("preset", choices=[*PRESETS, "all"], default="all", nargs="?")
    parser.add_argument("--musescore", type=Path, default=DEFAULT_MUSESCORE)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    names = PRESETS if args.preset == "all" else [args.preset]
    for name in names:
        preset = PRESETS[name]
        for part_ids, filename in preset.stems.items():
            label = "+".join(part_ids)
            print(f"Rendering {name} parts {label}: {filename}", flush=True)
            render_stem(
                preset, args.musescore, args.ffmpeg, args.output, part_ids, filename
            )


if __name__ == "__main__":
    main()
