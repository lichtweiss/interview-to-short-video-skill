#!/usr/bin/env python3
"""Render one approved interview span. No ASR, semantic selection, or publishing."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

SKILL = Path(__file__).resolve().parents[1]


def run(cmd, **kwargs):
    return subprocess.run(cmd, check=True, **kwargs)


def probe(path):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def stamp(t, srt=False):
    unit = 1000 if srt else 100
    n = round(t * unit)
    return (f'{n // (3600*unit):02}:{n // (60*unit) % 60:02}:'
            f'{n // unit % 60:02}' + (f',{n % unit:03}' if srt else f'.{n % unit:02}'))


def srt_read(path, duration):
    cues = []
    for block in re.split(r'\n\s*\n', path.read_text(encoding='utf-8-sig').strip()):
        lines = block.splitlines()
        if len(lines) < 3:
            raise ValueError(f'Malformed SRT block: {block!r}')
        pair = re.findall(r'(\d+):(\d{2}):(\d{2}),(\d{3})', lines[1])
        if len(pair) != 2:
            raise ValueError(f'Malformed SRT time: {lines[1]}')
        start, end = [int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000 for h,m,s,ms in pair]
        text = '\n'.join(lines[2:]).strip()
        if not text or not (0 <= start < end <= duration + .001):
            raise ValueError(f'Subtitle outside content span or empty: {block!r}')
        if cues and start < cues[-1]['end'] - .0001:
            raise ValueError('Overlapping captions: correct timing before rendering')
        if round(end*100) <= round(start*100):
            raise ValueError('Caption is too short for ASS centisecond timing')
        if any(c in text for c in '{}\\'):
            raise ValueError('Subtitle contains ASS control characters; normalize explicitly')
        cues.append(dict(start=start, end=end, text=text))
    if not cues:
        raise ValueError('No captions')
    return cues


def ass_color(color):
    color = color.lstrip('#')
    return '&H' + color[4:6] + color[2:4] + color[:2] + '&'


def make_layers(spec, style, font_path, duration, total, cues, out):
    def font(size):
        return ImageFont.truetype(str(font_path), size)

    canvas = style['canvas']
    image = Image.new('RGBA', tuple(canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    top, bottom = style['top_fade'], style['bottom_fade']
    for y in range(canvas[1]):
        if y < top['start']:
            alpha = 255
        elif y < top['end']:
            alpha = round(255 * (1-(y-top['start'])/(top['end']-top['start']))**top['exponent'])
        elif y > bottom['start']:
            alpha = round(255 * min(1, (y-bottom['start'])/(bottom['end']-bottom['start']))**bottom['exponent'])
        else:
            alpha = 0
        draw.line((0, y, canvas[0]-1, y), fill=(*style['background'], alpha))
    bounds = []
    for kind, color in [('title','white'), ('subtitle','gold'), ('descriptor','muted'), ('footer','footer_color')]:
        text = spec.get(kind, '')
        if not text:
            continue
        cfg = style[kind]
        box = draw.textbbox((540, cfg['y']), text, font=font(cfg['size']), anchor='mt')
        if box[0] < 36 or box[2] > 1044:
            raise ValueError(f'{kind} exceeds safe width: {text}')
        draw.text((540, cfg['y']), text, font=font(cfg['size']), fill=style[color], anchor='mt')
        bounds.append(dict(layer=kind, text=text, box=box))
    nav = style['navigation']
    chapters = spec['chapters']
    stride = 960 / len(chapters)
    width = round(stride - 32)
    for i in range(len(chapters)):
        x = round(76 + stride*i)
        draw.rounded_rectangle((x, nav['bar_y'], x+width, nav['bar_y']+nav['bar_height']),
                               radius=2, fill=style['track_color'])
    image.save(out/'overlay.png')

    cap = style['caption']
    family = spec['font_family']
    if any(c in family for c in ',\r\n'):
        raise ValueError('Invalid font family')
    lines = ['[Script Info]', 'ScriptType: v4.00+', 'PlayResX: 1080', 'PlayResY: 1920',
             'WrapStyle: 2', 'ScaledBorderAndShadow: yes', '', '[V4+ Styles]',
             'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
             f'Style: Cap,{family},{cap["size"]},&H00F1F8FA,&H00F1F8FA,&H80131412,&HC0131412,0,0,0,0,100,100,0,0,1,{cap["outline"]},{cap["shadow"]},2,84,84,255,1',
             f'Style: Nav,{family},{nav["size"]},&H0090948C,&H0090948C,&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1',
             '', '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']

    def event(start, end, text, name='Nav', layer=1):
        if round(end*100) > round(start*100):
            lines.append(f'Dialogue: {layer},{stamp(start)},{stamp(end)},{name},,0,0,0,,{text}')

    gold = ass_color(style['gold'])
    for i, chapter in enumerate(chapters):
        start = chapter['start']
        end = chapters[i+1]['start'] if i+1 < len(chapters) else duration
        label = f'{i+1:02}  {chapter["label"]}'
        if any(c in label for c in '{}\\\r\n') or font(nav['size']).getlength(label) > width:
            raise ValueError(f'Chapter label too wide or invalid: {label}')
        x = round(76 + stride*i)
        pos = rf'\pos({x+width/2:g},{nav["text_y"]})'
        event(0, start, '{'+pos+'}'+label)
        event(start, end, '{'+pos+rf'\c{gold}'+'}'+label)
        # The final chapter stays active through the breathing tail.
        event(end, total, '{'+pos+(rf'\c{gold}' if i == len(chapters)-1 else '')+'}'+label)
        y, h = nav['bar_y'], nav['bar_height']
        path = f'm 0 0 l {width} 0 {width} {h} 0 {h}'
        prefix = rf'\an7\pos({x},{y})\p1\bord0\shad0\c{gold}'
        tween = rf'\clip({x},{y},{x},{y+h+1})\t(0,{round((end-start)*1000)},\clip({x},{y},{x+width},{y+h+1}))'
        event(start, end, '{'+prefix+tween+'}'+path, layer=2)
        event(end, total, '{'+prefix+'}'+path, layer=2)

    def wrap(text):
        rows = text.splitlines()
        f = font(cap['size'])
        if len(rows) <= 2 and max(map(f.getlength, rows)) <= cap['max_width']:
            return r'\N'.join(rows)
        text = ''.join(rows)
        points = [i for i in range(1, len(text)) if not
                  (text[i-1].isascii() and text[i-1].isalnum() and text[i].isascii() and text[i].isalnum())]
        if not points:
            raise ValueError(f'Caption cannot fit: {text}')
        split = min(points, key=lambda i: max(f.getlength(text[:i]), f.getlength(text[i:])))
        if max(f.getlength(text[:split]), f.getlength(text[split:])) > cap['max_width']:
            raise ValueError(f'Caption needs shorter cues: {text}')
        return text[:split]+r'\N'+text[split:]

    for cue in cues:
        text = wrap(cue['text'])
        for key in spec.get('highlight_terms', []):
            if not isinstance(key,str) or not key or any(c in key for c in '{}\\\r\n'):
                raise ValueError('Invalid highlight term')
            if key in text:
                text = text.replace(key, '{'+rf'\c{gold}'+'}'+key+r'{\c&HF1F8FA&}', 1)
                break
        event(cue['start'], cue['end'], rf'{{\an2\pos({cap["x"]},{cap["y"]})}}'+text, 'Cap', 3)
    (out/'captions.ass').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (out/'captions.srt').write_text('\n\n'.join(
        f'{i+1}\n{stamp(c["start"],True)} --> {stamp(c["end"],True)}\n{c["text"]}' for i,c in enumerate(cues))+'\n', encoding='utf-8')
    return bounds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', type=Path)
    parser.add_argument('--id', help='Select a clip ID when the specification is an array')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--encoder', choices=['libx264', 'h264_videotoolbox'], default='libx264')
    args = parser.parse_args()
    spec_path = args.spec.resolve()
    spec = json.loads(spec_path.read_text())
    if isinstance(spec,list):
        selected = [s for s in spec if isinstance(s,dict) and str(s.get('id',s.get('no',''))) == args.id]
        if len(selected) != 1:
            raise ValueError('For a specifications array, pass --id with exactly one matching clip ID')
        spec = selected[0]
    if not isinstance(spec, dict):
        raise ValueError('Specification must be an object or an array of objects')
    if spec.get('copy_sheet'):
        sheet = (spec_path.parent / Path(spec['copy_sheet']).expanduser()).resolve()
        if hashlib.sha256(sheet.read_bytes()).hexdigest() != spec.get('copy_sheet_sha256'):
            raise ValueError('Copy sheet changed; apply it again before rendering')
        if spec.get('copy_confirmation') != 'confirmed':
            raise ValueError('Copy sheet has not been user-confirmed; formal rendering is blocked')
    def resolve(value):
        return (spec_path.parent / Path(value).expanduser()).resolve()
    if spec.get('srt_sha256') and hashlib.sha256(resolve(spec['srt']).read_bytes()).hexdigest() != spec['srt_sha256']:
        raise ValueError('SRT changed; review it and apply the copy sheet again before rendering')
    source = resolve(spec['source'])
    audio_source = resolve(spec.get('audio_source', spec['source']))
    style = json.loads((resolve(spec['style']) if spec.get('style') else SKILL/'assets/style.json').read_text())
    if not spec.get('style') and not spec.get('palette'):
        raise ValueError('Choose a palette from reference/material/brand first; gold is not a universal default')
    palette = spec.get('palette', {})
    if palette:
        accent = palette.get('accent_color', '')
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', accent) or not palette.get('reason'):
            raise ValueError('palette requires #RRGGBB accent_color and a selection reason')
        style['gold'] = accent
    for kind, size in spec.get('font_sizes', {}).items():
        if kind not in ['title','subtitle','descriptor','footer','caption','navigation'] or not isinstance(size,int) or not 12 <= size <= 120:
            raise ValueError('Invalid font_sizes setting')
        style[kind]['size'] = size
    if style['canvas'] != [1080,1920]:
        raise ValueError('This renderer uses the 1080x1920 template; adapt geometry for other sizes')
    font_path = resolve(spec['font_file'])
    if not font_path.is_file() or not spec.get('font_family'):
        raise ValueError('Provide a real font_file and matching font_family')
    for tool in ['ffmpeg', 'ffprobe']:
        if not shutil.which(tool):
            raise ValueError(f'Missing {tool}')
    start, end = float(spec['source_start']), float(spec['source_end'])
    duration = end-start
    fps = int(style['fps'])
    speech_end = float(spec['speech_end'])
    if not (0 <= start < end and 0 < speech_end <= duration):
        raise ValueError('Invalid source or speech times')
    if abs(duration*fps-round(duration*fps)) > .001:
        raise ValueError('Choose source duration on the output frame grid')
    source_info = probe(source)
    vs = next(s for s in source_info['streams'] if s['codec_type']=='video')
    source_duration = float(vs.get('duration') or source_info['format']['duration'])
    if end > source_duration + .001:
        raise ValueError('source_end exceeds source video')
    audio_info = probe(audio_source)
    audio = next(s for s in audio_info['streams'] if s['codec_type']=='audio')
    audio_start = float(spec.get('audio_start', start))
    if audio_start < 0 or audio_start+duration > float(audio.get('duration') or audio_info['format']['duration']) + .05:
        raise ValueError('Audio source does not cover the requested span')
    tail = spec.get('tail', {})
    target_pause = float(tail.get('target_pause', 1.0))
    caption_hold = float(tail.get('caption_hold', .5))
    if not (0 <= target_pause <= 3 and 0 <= caption_hold <= 3):
        raise ValueError('Tail settings must be between 0 and 3 seconds')
    extra = math.ceil(max(0., target_pause-(duration-speech_end))*fps-1e-8)/fps
    total = duration+extra
    cues = srt_read(resolve(spec['srt']), duration)
    cues[-1]['end'] = min(total, max(cues[-1]['end'], speech_end+caption_hold))
    chapters = spec['chapters']
    if not 1 <= len(chapters) <= 3 or chapters[0]['start'] != 0:
        raise ValueError('Provide 1-3 chapters, beginning at zero')
    if any(not str(c['label']).strip() or not 0 <= c['start'] < duration for c in chapters):
        raise ValueError('Invalid chapter label or time')
    if any(a['start'] >= b['start'] for a,b in zip(chapters, chapters[1:])):
        raise ValueError('Chapter starts must strictly increase')
    if not spec.get('title', '').strip():
        raise ValueError('Main title must be nonempty')
    if not spec.get('footer', '').strip() and spec.get('footer_policy') != 'explicitly_omitted':
        raise ValueError('Footer is empty; fill the maintained copy sheet or explicitly mark [留空]')
    layout = spec.get('layout', 'wide')
    if layout not in ['portrait','wide']:
        raise ValueError('layout must be portrait or wide')
    crop = ''
    if 'crop' in spec:
        x,y,w,h = spec['crop']
        if not all(isinstance(v,int) for v in (x,y,w,h)) or min(x,y)<0 or min(w,h)<=0 or x+w>vs['width'] or y+h>vs['height']:
            raise ValueError('crop is outside source dimensions')
        crop = f'crop={w}:{h}:{x}:{y},'
    x,y,w,h = style[layout+'_picture']
    bg = '0x'+''.join(f'{v:02x}' for v in style['background'])
    if layout == 'portrait':
        picture = f'scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}'
    else:
        picture = f'scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={bg}'
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    bounds = make_layers(spec, style, font_path, duration, total, cues, out)
    # A local filename prevents user paths from becoming FFmpeg filter syntax.
    (out/'fonts').mkdir()
    (out/'fonts'/font_path.name).symlink_to(font_path)
    video_filter = spec.get('video_filter', '').strip()
    extra_filter = f'{video_filter},' if video_filter else ''
    filt = (f'[0:v]trim=duration={duration},setpts=PTS-STARTPTS,{crop}{extra_filter}{picture},'
            f'pad=1080:1920:{x}:{y}:color={bg},setsar=1,fps={fps},'
            f'tpad=stop_mode=clone:stop_duration={extra}[picture];'
            '[picture][1:v]overlay=0:0:format=auto,format=yuv420p,'
            "ass=filename=captions.ass:fontsdir=fonts[v];"
            f'[2:a]atrim=duration={duration},asetpts=PTS-STARTPTS,apad=pad_dur={extra},atrim=duration={total}[a]')
    cmd = ['ffmpeg','-hide_banner','-nostdin','-n','-ss',str(start),'-i',str(source),
           '-i','overlay.png','-ss',str(audio_start),'-i',str(audio_source),
           '-filter_complex_threads','2','-filter_complex',filt,'-map','[v]','-map','[a]',
           '-c:v',args.encoder]
    cmd += ['-crf','18','-preset','fast'] if args.encoder=='libx264' else ['-b:v','12M','-maxrate','18M','-bufsize','24M']
    cmd += ['-pix_fmt','yuv420p','-r',str(fps),'-c:a','aac','-b:a','192k','-ar','48000',
            '-ac','2','-t',str(total),'-movflags','+faststart','video.mp4']
    (out/'spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2))
    with (out/'render.log').open('w') as log:
        run(cmd, cwd=out, stdout=log, stderr=log)
    info = probe(out/'video.mp4')
    video = next(s for s in info['streams'] if s['codec_type']=='video')
    encoded_audio = next(s for s in info['streams'] if s['codec_type']=='audio')
    if [video['width'],video['height']] != [1080,1920] or abs(float(video['duration'])-total)>1/fps+.001:
        raise RuntimeError('Export dimensions or duration mismatch')
    if video['r_frame_rate'] != f'{fps}/1' or abs(float(encoded_audio['duration'])-total)>.07:
        raise RuntimeError('Export frame rate or audio duration mismatch')
    result = run(['ffmpeg','-v','error','-xerror','-i',str(out/'video.mp4'),'-f','null','-'],capture_output=True,text=True)
    if result.stderr.strip():
        raise RuntimeError(result.stderr)
    frames = []
    for name,t in [('opening',0),('middle',duration/2),('tail',max(0,total-1/fps))]:
        run(['ffmpeg','-v','error','-nostdin','-n','-ss',str(t),'-i',str(out/'video.mp4'),
             '-frames:v','1','-threads','1',str(out/f'{name}.jpg')])
        frames.append(dict(file=f'{name}.jpg',time=t))
    with (out/'video.mp4').open('rb') as handle:
        digest = hashlib.sha256()
        for block in iter(lambda:handle.read(1024*1024), b''):
            digest.update(block)
    report = dict(machine_checks='passed',full_decode=True,width=1080,height=1920,fps=fps,
                  content_duration=duration,speech_end=speech_end,existing_pause=duration-speech_end,
                  added_freeze_seconds=extra,output_duration=float(video['duration']),
                  post_speech_pause=total-speech_end,caption_end=cues[-1]['end'],
                  audio_mode='AAC reencoded; added portion silence padded',
                  source=str(source),source_start=start,source_end=end,
                  audio_source=str(audio_source),audio_start=audio_start,
                  source_spec=str(spec_path),style_sha256=hashlib.sha256(json.dumps(style,sort_keys=True).encode()).hexdigest(),
                  font_file=str(font_path),sha256=digest.hexdigest(),
                  captions_sha256=hashlib.sha256((out/'captions.srt').read_bytes()).hexdigest(),
                  text_bounds=bounds,frames=frames,
                  visual_review='pending',listening_review='pending',semantic_review='pending')
    (out/'qc.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(dict(output=str(out/'video.mp4'),duration=total,added_tail=extra),ensure_ascii=False))


if __name__ == '__main__':
    main()
