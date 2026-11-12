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


def export(plan_path, out):
    plan_path = Path(plan_path).resolve()
    out = Path(out).resolve()
    plan = read_plan(plan_path)
    errors = validate(plan)
    if errors:
        raise ValueError('; '.join(f'{e.path}: {e.message}' for e in errors))
    if out.exists():
        raise FileExistsError('Choose a fresh output directory')
    if out == plan_path.parent or out in plan_path.parents:
        raise ValueError('Output must not contain the input plan')
    themes = {t['id']: t for t in plan['themes']}
    records = []
    # Validate all inputs before copying anything.
    for clip in plan['clips']:
        if not isinstance(clip.get('render_dir'), str) or not clip['render_dir'].strip():
            raise ValueError(f'{clip["id"]}: provide render_dir')
        src = (plan_path.parent / clip['render_dir']).resolve()
        if out == src or src in out.parents or out in src.parents:
            raise ValueError('Output and rendered input directories must be separate')
        rendered_spec = json.loads((src/'spec.json').read_text(encoding='utf-8'))
        for key in ('id', 'theme_id', 'series_order', 'title'):
            value = rendered_spec.get(key) if key != 'id' else rendered_spec.get('id', rendered_spec.get('no'))
            if value != clip.get(key):
                raise ValueError(f'{clip["id"]}: rendered {key} does not match editorial plan; recompile and render')
        qc = json.loads((src/'qc.json').read_text(encoding='utf-8'))
        windows = clip['source_windows']
        if len(windows) == 1 and not clip.get('intermediate_mapping'):
            render_window = windows[0]
        else:
            mapping = clip.get('intermediate_mapping')
            if not isinstance(mapping, dict) or not isinstance(mapping.get('evidence'), str) or not mapping['evidence'].strip():
                raise ValueError(f'{clip["id"]}: multi-window edits require intermediate_mapping with render_window and evidence')
            render_window = mapping.get('render_window', {})
            if not isinstance(render_window, dict):
                raise ValueError(f'{clip["id"]}: intermediate render_window must be an object')
        for plan_key, qc_key in [('start', 'source_start'), ('end', 'source_end')]:
            a, b = render_window.get(plan_key), qc.get(qc_key)
            if type(a) not in (int, float) or type(b) not in (int, float) or not abs(a - b) <= .001:
                raise ValueError(f'{clip["id"]}: rendered source window does not match plan')
        if qc.get('machine_checks') != 'passed' or qc.get('full_decode') is not True:
            raise ValueError(f'{clip["id"]}: machine checks have not passed')
        digest = hashlib.sha256((src/'video.mp4').read_bytes()).hexdigest()
        if digest != qc.get('sha256'):
            raise ValueError(f'{clip["id"]}: rendered video changed after QC')
        if not (src/'captions.srt').is_file():
            raise ValueError(f'{clip["id"]}: captions missing')
        if hashlib.sha256((src/'captions.srt').read_bytes()).hexdigest() != qc.get('captions_sha256'):
            raise ValueError(f'{clip["id"]}: captions changed after QC')
        records.append((clip, src, digest))
    out.mkdir(parents=True, exist_ok=False)
    manifest = {'stage': plan.get('stage', 'preview'), 'themes': plan['themes'], 'clips': []}
    sections = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8">',
                '<meta name="viewport" content="width=device-width,initial-scale=1">',
                '<title>Interview clip review</title><style>body{max-width:1000px;margin:auto;padding:24px;font:16px sans-serif}video{width:260px;max-width:100%}article{display:inline-block;vertical-align:top;width:300px;padding:12px}h2{clear:both}</style>',
                f'<h1>Interview clip review</h1><p>State: {html.escape(manifest["stage"])}. Machine QC does not replace human review.</p>']
    for group_index, (tid, theme) in enumerate(themes.items(), 1):
        slug = re.sub(r'[^\w-]+', '_', theme['name'], flags=re.UNICODE).strip('_')[:60] or 'theme'
        folder = f'{group_index:02}_{slug}'
        sections.append(f'<section><h2>{html.escape(theme["name"])}</h2>')
        for clip, src, digest in sorted((r for r in records if r[0]['theme_id'] == tid), key=lambda r: r[0]['series_order']):
            relative = Path(folder)/f'{clip["series_order"]:02}'
            target = out/relative
            target.mkdir(parents=True)
            for filename in ('video.mp4', 'captions.srt', 'qc.json'):
                shutil.copy2(src/filename, target/filename)
            video = (relative/'video.mp4').as_posix()
            subtitles = (relative/'captions.srt').as_posix()
            manifest['clips'].append({'id': clip['id'], 'theme_id': tid, 'series_order': clip['series_order'],
                                      'title': clip['title'], 'video': video, 'srt': subtitles,
                                      'sha256': digest, 'human_review': clip['human_review']})
            sections.append(f'<article><h3>{html.escape(clip["title"])}</h3><video controls preload="metadata" src="{quote(video)}"></video><p><a href="{quote(subtitles)}">SRT</a></p></article>')
        sections.append('</section>')
    sections.append('</html>')
    (out/'index.html').write_text('\n'.join(sections), encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('plan', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    result = export(args.plan, args.out)
    print(json.dumps({'clips': len(result['clips']), 'output': str(args.out.resolve())}))


if __name__ == '__main__':
    main()
