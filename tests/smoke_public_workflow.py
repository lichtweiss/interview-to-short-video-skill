#!/usr/bin/env python3
"""Exercise documented public commands with generated media and fixture approvals.

This checks the reviewed-SRT route. It never installs or claims to test ASR.
Use a fresh --work directory; source media and confirmations are synthetic.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def run(script, *args, error=None):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *map(str, args)],
        capture_output=True,
        text=True,
        env=env,
    )
    if error is None:
        if result.returncode:
            raise RuntimeError(f"{script}: {result.stderr[-2000:]}")
    elif result.returncode == 0 or error not in result.stderr:
        raise RuntimeError(f"{script}: expected rejection {error!r}; got {result.stderr[-2000:]}")
    return result


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def compile_copy(work):
    spec, sheet = work / "spec.json", work / "画面文字编订.md"
    run("copy_sheet.py", "export", spec, sheet)
    rejected = work / "rejected.json"
    common = ["apply", spec, sheet, "--out", rejected]
    run("copy_sheet.py", *common, error="requires --approval")
    run("copy_sheet.py", *common, "--approval", "Synthetic fixture", error="文案尚未确认")
    assert not rejected.exists(), "Unconfirmed copy produced a compiled specification"
    default = work / "default.json"
    run(
        "copy_sheet.py",
        "apply",
        spec,
        sheet,
        "--out",
        default,
        "--accept-default",
        "--approval",
        "SYNTHETIC TEST ONLY: accept fixture default",
    )
    assert read(default)["copy_approval"]["mode"] == "default-accepted"
    sheet.write_text(
        sheet.read_text(encoding="utf-8")
        .replace("Synthetic demo", "Reviewed demo")
        .replace("needs-user-review", "user-confirmed"),
        encoding="utf-8",
    )
    compiled = work / "build" / "compiled.json"
    run(
        "copy_sheet.py",
        "apply",
        spec,
        sheet,
        "--out",
        compiled,
        "--approval",
        "SYNTHETIC TEST ONLY: edited fixture confirmation",
    )
    assert read(compiled)["title"] == "Reviewed demo"
    return compiled


def check_preview(work, compiled):
    out = work / "reviewed-preview"
    run("render_interview.py", compiled, "--out", out)
    qc = read(out / "qc.json")
    assert qc["full_decode"] and qc["machine_checks"] == "passed"
    assert qc["sha256"] == hashlib.sha256((out / "video.mp4").read_bytes()).hexdigest()
    assert all(qc[k] == "pending" for k in ("visual_review", "listening_review", "semantic_review"))
    original = (work / "captions.srt").read_bytes()
    try:
        (work / "captions.srt").write_bytes(original.replace(b"Synthetic", b"Changed"))
        run("render_interview.py", compiled, "--out", work / "stale", error="SRT changed")
        assert not (work / "stale").exists()
    finally:
        (work / "captions.srt").write_bytes(original)
    return out


def export_preview(work):
    plan = read(work / "plan.json")
    plan["clips"][0].update(render_dir="reviewed-preview", title="Reviewed demo")
    (work / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    out = work / "theme review"
    run("export_review.py", work / "plan.json", "--out", out)
    manifest = read(out / "manifest.json")
    assert manifest["stage"] == "preview"
    assert len(manifest["clips"]) == 1
    assert manifest["dashboard"] == "index.html"
    assert manifest["clips"][0]["human_review"]["audio"] == "pending"
    dashboard = (out / "index.html").read_text()
    assert 'data-dashboard="interview-clip-review"' in dashboard
    assert "Source window" in dashboard
    assert "Machine QC" in dashboard
    for link in re.findall(r'(?:src|href)="([^"]+)"', (out / "index.html").read_text()):
        assert (out / unquote(link)).is_file(), f"Broken review page link: {link}"
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--font-family", required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    run("doctor.py", "--font", args.font)
    run("create_demo.py", "--work", work, "--font", args.font, "--font-family", args.font_family)
    run("validate_editorial_plan.py", work / "plan.json", "--stage", "preview", "--json")
    compiled = compile_copy(work)
    preview = check_preview(work, compiled)
    review = export_preview(work)
    report = {
        "passed": True,
        "fixture": "generated bars/tone and supplied SRT",
        "asr_tested": False,
        "human_review": "pending",
        "checks": [
            "dependency doctor",
            "preview plan",
            "missing approval rejected",
            "unconfirmed sheet rejected",
            "explicit default route",
            "edited copy route",
            "MP4 decode and hash",
            "changed SRT rejected",
            "HTML dashboard links and summary",
        ],
        "preview": str(preview / "video.mp4"),
        "review": str(review / "index.html"),
    }
    (work / "smoke-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
