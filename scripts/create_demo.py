#!/usr/bin/env python3
"""Generate synthetic bars/tone and runnable inputs; never mark human review done."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def create_source(work):
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-n",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=25:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(work / "source.mp4"),
        ],
        check=True,
    )


def create(work, font, family):
    work = Path(work).resolve()
    font = Path(font).expanduser().resolve()
    if not font.is_file() or not family.strip():
        raise ValueError("Provide a real font and its family")
    work.mkdir(parents=True, exist_ok=False)
    create_source(work)
    (work / "captions.srt").write_text(
        "1\n00:00:00,000 --> 00:00:00,700\nSynthetic demo\n\n2\n00:00:00,800 --> 00:00:01,200\nNot an interview\n",
        encoding="utf-8",
    )
    chapters = [
        {"start": 0, "label": "Demo", "semantic_basis": "Synthetic fixture only"},
        {
            "start": 1,
            "label": "Check",
            "semantic_basis": "Synthetic transition, not a real editorial decision",
        },
    ]
    spec = {
        "id": "01",
        "theme_id": "demo",
        "series_order": 1,
        "source": "source.mp4",
        "srt": "captions.srt",
        "source_start": 0,
        "source_end": 2,
        "speech_end": 1.2,
        "title": "Synthetic demo",
        "footer": "Test fixture",
        "layout": "wide",
        "chapters": chapters,
        "font_file": str(font),
        "font_family": family,
        "palette": {"accent_color": "#70C8E7", "reason": "Synthetic fixture"},
        "tail": {"target_pause": 1, "caption_hold": 0.5},
    }
    clip = {
        "id": "01",
        "theme_id": "demo",
        "series_order": 1,
        "theme_basis": "Synthetic fixture",
        "topic_id": "synthetic",
        "title": spec["title"],
        "source_windows": [{"start": 0, "end": 2}],
        "speakers": ["synthetic"],
        "selection_basis": "topic_and_dialogue_unit",
        "selection_reason": "Toolchain fixture only",
        "layout": "wide",
        "composition": {"interaction_visible": True, "evidence": "Generated bars"},
        "chapters": chapters,
        "copy_status": "draft",
        "machine_qc": "pending",
        "human_review": dict.fromkeys(["identity", "audio", "semantic", "visual"], "pending"),
    }
    plan = {
        "stage": "preview",
        "themes": [{"id": "demo", "name": "Synthetic checks"}],
        "identity_map": [{"person_id": "synthetic", "status": "pending"}],
        "source_registry": [
            {
                "source_ref": "source.mp4",
                "sha256": hashlib.sha256((work / "source.mp4").read_bytes()).hexdigest(),
            }
        ],
        "clips": [clip],
        "state": {"status": "preview"},
    }
    for name, value in [("spec.json", spec), ("plan.json", plan)]:
        (work / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return work


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, required=True)
    p.add_argument("--font", type=Path, required=True)
    p.add_argument("--font-family", required=True)
    args = p.parse_args()
    print(create(args.work, args.font, args.font_family))


if __name__ == "__main__":
    main()
