#!/usr/bin/env python3
"""Arrange rendered clips into the agent's semantic themes and a review page.

Does not infer themes from pixels/text or promote delivery states. Use the same
plan as the editorial validator; every clip additionally needs render_dir.
"""

import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
from urllib.parse import quote

from validate_editorial_plan import read_plan, validate


def format_seconds(value):
    """Format a finite source/output duration for the dashboard."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return "—"
    if seconds < 0:
        return "—"
    whole = round(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def source_windows_text(windows):
    parts = []
    for window in windows or []:
        if not isinstance(window, dict):
            continue
        parts.append(
            f'{format_seconds(window.get("start"))}–{format_seconds(window.get("end"))}'
        )
    return "、".join(parts) or "—"


def check_rendered_clip(clip, plan_path, out):
    if not isinstance(clip.get("render_dir"), str) or not clip["render_dir"].strip():
        raise ValueError(f'{clip["id"]}: provide render_dir')
    src = (plan_path.parent / clip["render_dir"]).resolve()
    if out == src or src in out.parents or out in src.parents:
        raise ValueError("Output and rendered input directories must be separate")
    rendered_spec = json.loads((src / "spec.json").read_text(encoding="utf-8"))
    for key in ("id", "theme_id", "series_order", "title"):
        value = (
            rendered_spec.get(key)
            if key != "id"
            else rendered_spec.get("id", rendered_spec.get("no"))
        )
        if value != clip.get(key):
            raise ValueError(
                f'{clip["id"]}: rendered {key} does not match editorial plan; recompile and render'
            )
    qc = json.loads((src / "qc.json").read_text(encoding="utf-8"))
    windows = clip["source_windows"]
    if len(windows) == 1 and not clip.get("intermediate_mapping"):
        render_window = windows[0]
    else:
        mapping = clip.get("intermediate_mapping")
        if (
            not isinstance(mapping, dict)
            or not isinstance(mapping.get("evidence"), str)
            or not mapping["evidence"].strip()
        ):
            raise ValueError(
                f'{clip["id"]}: multi-window edits require intermediate_mapping with render_window and evidence'
            )
        render_window = mapping.get("render_window", {})
        if not isinstance(render_window, dict):
            raise ValueError(f'{clip["id"]}: intermediate render_window must be an object')
    for plan_key, qc_key in [("start", "source_start"), ("end", "source_end")]:
        a, b = render_window.get(plan_key), qc.get(qc_key)
        if type(a) not in (int, float) or type(b) not in (int, float) or not abs(a - b) <= 0.001:
            raise ValueError(f'{clip["id"]}: rendered source window does not match plan')
    if qc.get("machine_checks") != "passed" or qc.get("full_decode") is not True:
        raise ValueError(f'{clip["id"]}: machine checks have not passed')
    digest = hashlib.sha256((src / "video.mp4").read_bytes()).hexdigest()
    if digest != qc.get("sha256"):
        raise ValueError(f'{clip["id"]}: rendered video changed after QC')
    if not (src / "captions.srt").is_file():
        raise ValueError(f'{clip["id"]}: captions missing')
    if hashlib.sha256((src / "captions.srt").read_bytes()).hexdigest() != qc.get("captions_sha256"):
        raise ValueError(f'{clip["id"]}: captions changed after QC')
    return src, digest


def export(plan_path, out):
    plan_path = Path(plan_path).resolve()
    out = Path(out).resolve()
    plan = read_plan(plan_path)
    errors = validate(plan)
    if errors:
        raise ValueError("; ".join(f"{e.path}: {e.message}" for e in errors))
    if out.exists():
        raise FileExistsError("Choose a fresh output directory")
    if out == plan_path.parent or out in plan_path.parents:
        raise ValueError("Output must not contain the input plan")
    themes = {t["id"]: t for t in plan["themes"]}
    records = []
    # Validate all inputs before copying anything.
    for clip in plan["clips"]:
        src, digest = check_rendered_clip(clip, plan_path, out)
        records.append((clip, src, digest))
    out.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "stage": plan.get("stage", "preview"),
        "dashboard": "index.html",
        "themes": plan["themes"],
        "clips": [],
    }
    sections = [
        '<!doctype html><html lang="zh-CN" data-dashboard="interview-clip-review">',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta name="description" content="Interview short-video review dashboard">',
        (
            "<title>Interview clip review dashboard</title><style>"
            ":root{color-scheme:light dark;--bg:#f4f5f7;--card:#fff;--ink:#17202a;"
            "--muted:#5c6874;--line:#d9dee5;--accent:#b36b28}"
            "*{box-sizing:border-box}body{max-width:1180px;margin:auto;padding:28px;"
            "font:16px/1.55 system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
            "background:var(--bg);color:var(--ink)}h1{margin:0 0 6px;font-size:30px}"
            "h2{margin:34px 0 8px;border-bottom:2px solid var(--line);padding-bottom:6px}"
            "h3{margin:0 0 8px;font-size:19px}.lede,.theme-basis{color:var(--muted)}"
            ".summary{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:10px;margin:22px 0}"
            ".metric,.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}"
            ".metric strong{display:block;font-size:26px}.metric span{color:var(--muted);font-size:13px}"
            "table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);"
            "border-radius:12px;overflow:hidden}th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);"
            "vertical-align:top}th{font-size:13px;color:var(--muted);font-weight:600}tr:last-child td{border-bottom:0}"
            ".cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}"
            ".card video{width:100%;aspect-ratio:9/16;background:#111;border-radius:8px;margin:8px 0}"
            ".meta{margin:6px 0;color:var(--muted);font-size:14px}.status{font-weight:600;color:var(--accent)}"
            ".links a{margin-right:12px}.chapter{display:inline-block;margin:3px 5px 0 0;padding:2px 7px;"
            "border:1px solid var(--line);border-radius:999px;font-size:12px;color:var(--muted)}"
            "@media(max-width:700px){body{padding:16px}.summary{grid-template-columns:repeat(2,1fr)}"
            "table{font-size:13px;display:block;overflow-x:auto;white-space:nowrap}}"
            "@media(prefers-color-scheme:dark){:root{--bg:#11151a;--card:#1b222a;--ink:#eef2f5;"
            "--muted:#a8b3bd;--line:#35414d;--accent:#e0a365}}</style>"
        ),
        (
            f'<main><h1>Interview clip review dashboard</h1>'
            f'<p class="lede">State: <span class="status">{html.escape(manifest["stage"])}</span>. '
            'This page collects the batch videos, subtitles, source windows, chapters and review states. '
            'Machine QC does not replace human review.</p>'
        ),
    ]
    machine_passed = 0
    pending_human = 0
    for clip, src, digest in records:
        qc = json.loads((src / "qc.json").read_text(encoding="utf-8"))
        machine_passed += int(qc.get("machine_checks") == "passed")
        pending_human += sum(
            value == "pending" for value in clip.get("human_review", {}).values()
        )
    sections.append(
        '<div class="summary">'
        f'<div class="metric"><strong>{len(records)}</strong><span>clips in batch</span></div>'
        f'<div class="metric"><strong>{len(themes)}</strong><span>themes</span></div>'
        f'<div class="metric"><strong>{machine_passed}/{len(records)}</strong><span>machine QC passed</span></div>'
        f'<div class="metric"><strong>{pending_human}</strong><span>pending human checks</span></div>'
        '</div>'
        '<p class="links"><a href="manifest.json">Open manifest.json</a></p>'
    )
    sections.append(
        '<table><thead><tr><th>Series</th><th>Theme</th><th>Title</th>'
        '<th>Source window</th><th>Duration</th><th>Machine QC</th><th>Human review</th></tr></thead><tbody>'
    )
    for group_index, (tid, theme) in enumerate(themes.items(), 1):
        slug = re.sub(r"[^\w-]+", "_", theme["name"], flags=re.UNICODE).strip("_")[:60] or "theme"
        folder = f"{group_index:02}_{slug}"
        sections.append(
            f'<tr><td colspan="7"><strong>{html.escape(theme["name"])}</strong>'
            f'<div class="theme-basis">{html.escape(theme.get("basis", theme.get("theme_basis", "")))}</div>'
            '</td></tr>'
        )
        for clip, src, digest in sorted(
            (r for r in records if r[0]["theme_id"] == tid), key=lambda r: r[0]["series_order"]
        ):
            relative = Path(folder) / f'{clip["series_order"]:02}'
            target = out / relative
            target.mkdir(parents=True)
            for filename in ("video.mp4", "captions.srt", "qc.json", "spec.json"):
                shutil.copy2(src / filename, target / filename)
            video = (relative / "video.mp4").as_posix()
            subtitles = (relative / "captions.srt").as_posix()
            spec = json.loads((src / "spec.json").read_text(encoding="utf-8"))
            qc = json.loads((src / "qc.json").read_text(encoding="utf-8"))
            human = clip.get("human_review", {})
            human_text = ", ".join(
                f'{html.escape(key)}={html.escape(str(value))}' for key, value in human.items()
            ) or "—"
            chapters = " ".join(
                f'<span class="chapter">{html.escape(str(ch.get("label", "")))}</span>'
                for ch in spec.get("chapters", []) if isinstance(ch, dict)
            )
            manifest["clips"].append(
                {
                    "id": clip["id"],
                    "theme_id": tid,
                    "series_order": clip["series_order"],
                    "title": clip["title"],
                    "video": video,
                    "srt": subtitles,
                    "spec": (relative / "spec.json").as_posix(),
                    "source_windows": clip.get("source_windows", []),
                    "duration_s": qc.get("output_duration"),
                    "machine_qc": qc.get("machine_checks"),
                    "sha256": digest,
                    "human_review": human,
                }
            )
            sections.append(
                f'<tr><td>{html.escape(str(clip["series_order"]))}</td>'
                f'<td>{html.escape(theme["name"])}</td>'
                f'<td><a href="{quote(video)}">{html.escape(clip["title"])}</a></td>'
                f'<td>{html.escape(source_windows_text(clip.get("source_windows")))}</td>'
                f'<td>{html.escape(format_seconds(qc.get("output_duration")))}</td>'
                f'<td>{html.escape(str(qc.get("machine_checks", "—")))}</td>'
                f'<td>{human_text}</td></tr>'
            )
    sections.append('</tbody></table>')
    for group_index, (tid, theme) in enumerate(themes.items(), 1):
        slug = re.sub(r"[^\w-]+", "_", theme["name"], flags=re.UNICODE).strip("_")[:60] or "theme"
        folder = f"{group_index:02}_{slug}"
        sections.append(f'<section><h2>{html.escape(theme["name"])}</h2>')
        sections.append(f'<p class="theme-basis">{html.escape(theme.get("basis", theme.get("theme_basis", "")))}</p><div class="cards">')
        for clip, src, digest in sorted(
            (r for r in records if r[0]["theme_id"] == tid), key=lambda r: r[0]["series_order"]
        ):
            relative = Path(folder) / f'{clip["series_order"]:02}'
            video = (relative / "video.mp4").as_posix()
            subtitles = (relative / "captions.srt").as_posix()
            spec = json.loads((src / "spec.json").read_text(encoding="utf-8"))
            qc = json.loads((src / "qc.json").read_text(encoding="utf-8"))
            chapters = " ".join(
                f'<span class="chapter">{html.escape(str(ch.get("label", "")))}</span>'
                for ch in spec.get("chapters", []) if isinstance(ch, dict)
            )
            sections.append(
                f'<article class="card"><h3>{html.escape(clip["title"])}</h3>'
                f'<p class="meta">Series {html.escape(str(clip["series_order"]))} · '
                f'Source {html.escape(source_windows_text(clip.get("source_windows")))} · '
                f'{html.escape(format_seconds(qc.get("output_duration")))}</p>'
                f'<video controls preload="metadata" src="{quote(video)}"></video>'
                f'<p>{chapters}</p><p class="links">'
                f'<a href="{quote(video)}">MP4</a>'
                f'<a href="{quote(subtitles)}">SRT</a>'
                f'<a href="{quote((relative / "spec.json").as_posix())}">Spec</a></p></article>'
            )
        sections.append('</div></section>')
    sections.append('</main></html>')
    (out / "index.html").write_text("\n".join(sections), encoding="utf-8")
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("plan", type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    result = export(args.plan, args.out)
    print(json.dumps({"clips": len(result["clips"]), "output": str(args.out.resolve())}))


if __name__ == "__main__":
    main()
