#!/usr/bin/env python3
"""Check the renderer environment without downloading models or changing files."""
import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--font', type=Path, required=True)
    args = p.parse_args()
    checks = {'python_3_10_plus': sys.version_info >= (3, 10)}
    details = {'python': platform.python_version(), 'platform': platform.platform()}
    try:
        from PIL import ImageFont, __version__
        ImageFont.truetype(str(args.font), 32)
        checks['pillow_and_font'] = True
        details['pillow'] = __version__
    except (ImportError, OSError) as exc:
        checks['pillow_and_font'] = False
        details['font_error'] = str(exc)
    for tool in ('ffmpeg', 'ffprobe'):
        checks[tool] = bool(shutil.which(tool))
    if checks['ffmpeg']:
        try:
            filters = subprocess.check_output(['ffmpeg', '-hide_banner', '-filters'], stderr=subprocess.STDOUT, text=True)
            encoders = subprocess.check_output(['ffmpeg', '-hide_banner', '-encoders'], stderr=subprocess.STDOUT, text=True)
            checks['ass_filter'] = any(line.split()[1:2] == ['ass'] for line in filters.splitlines())
            checks['libx264'] = 'libx264' in encoders
            details['ffmpeg'] = subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0]
        except subprocess.SubprocessError as exc:
            checks['ffmpeg_query'] = False
            details['ffmpeg_error'] = str(exc)
    print(json.dumps({'passed': all(checks.values()), 'checks': checks, 'details': details}, ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
