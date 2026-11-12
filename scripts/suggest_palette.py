#!/usr/bin/env python3
"""Sample raw footage and propose readable accent colors. Requires visual choice."""
import argparse
import colorsys
import io
import json
import math
import re
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw, ImageFont


def rgb(value):
    return tuple(int(value.lstrip('#')[i:i+2],16) for i in (0,2,4))


def luminance(color):
    channels = [x/255 for x in color]
    return sum(w*(x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4)
               for w,x in zip((.2126,.7152,.0722), channels))


def contrast(a,b):
    x,y=sorted((luminance(a),luminance(b)))
    return (y+.05)/(x+.05)


def readable(color, background):
    h,s,v=colorsys.rgb_to_hsv(*(x/255 for x in color))
    if contrast(color,background)>=4.5:
        return color
    # Keep hue while moving lightness toward the opposite side of the text base.
    light=luminance(background)<.4
    for i in range(1,101):
        t=i/100
        candidate=tuple(round(x*255) for x in colorsys.hsv_to_rgb(h,s*(1-.6*t),v+(1-v)*t if light else v*(1-t)))
        if contrast(candidate,background)>=4.5:
            return candidate
    return (255,255,255) if light else (0,0,0)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('--start',type=float,default=0)
    p.add_argument('--end',type=float,required=True)
    p.add_argument('--background',default='#121413')
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if not math.isfinite(args.start) or not math.isfinite(args.end) or not 0<=args.start<args.end:
        p.error('Choose a valid source interval')
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", args.background):
        p.error("background must be #RRGGBB")
    if args.out.exists():
        p.error("output directory already exists; choose a fresh path")
    info=json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_format", "-of", "json", str(args.source.resolve())]))
    if args.end > float(info["format"]["duration"]) + .001:
        p.error("end exceeds source duration")
    background=rgb(args.background)
    frames=[]
    times=[args.start+(args.end-args.start)*x for x in (.1,.3,.5,.7,.9)]
    for t in times:
        data=subprocess.check_output(['ffmpeg','-v','error','-ss',str(t),'-i',str(args.source.resolve()),'-frames:v','1','-vf','scale=320:-2','-threads','1','-f','image2pipe','-c:v','png','-'])
        frames.append(Image.open(io.BytesIO(data)).convert('RGB'))
    montage=Image.new('RGB',(320,frames[0].height*len(frames)))
    for i,im in enumerate(frames): montage.paste(im,(0,i*frames[0].height))
    quantized=montage.quantize(colors=32,method=Image.Quantize.MEDIANCUT)
    palette=quantized.getpalette()
    ranked=[]
    for count,index in quantized.getcolors():
        color=tuple(palette[index*3:index*3+3])
        h,s,v=colorsys.rgb_to_hsv(*(x/255 for x in color))
        if s<.15 or not .12<v<.98: continue
        ranked.append((count*s,color,h))
    choices=[]
    for _,color,h in sorted(ranked,reverse=True):
        if any(min(abs(h-c['_h']),1-abs(h-c['_h']))<.08 for c in choices):continue
        adjusted=readable(color,background)
        choices.append(dict(_h=h,source_color='#' + ''.join(f'{x:02X}' for x in color),
                            accent_color='#' + ''.join(f'{x:02X}' for x in adjusted),
                            contrast=round(contrast(adjusted,background),2),adjusted_for_readability=color!=adjusted))
        if len(choices)==3:break
    if not choices:
        color=readable((160,160,160),background)
        choices=[dict(source_color=None,accent_color='#'+''.join(f'{x:02X}' for x in color),contrast=round(contrast(color,background),2),adjusted_for_readability=True)]
    for c in choices:c.pop('_h',None)
    args.out.mkdir(parents=True,exist_ok=False)
    montage.save(args.out/'source_samples.jpg',quality=90)
    board=Image.new('RGB',(640,150*len(choices)),background)
    d=ImageDraw.Draw(board); f=ImageFont.load_default(size=25)
    for i,c in enumerate(choices):
        y=i*150
        d.rectangle((24,y+28,114,y+120),fill=c['accent_color'])
        d.text((140,y+35),c['accent_color'],font=f,fill=c['accent_color'])
        d.text((140,y+80),f"Contrast {c['contrast']}:1",font=f,fill='white' if luminance(background)<.4 else 'black')
    board.save(args.out/'palette.png')
    result=dict(source=str(args.source.resolve()),sample_times=times,background=args.background,candidates=choices,
                status='candidates_require_visual_selection',note='Pixel clustering does not distinguish skin, clothing or set. Review source frames and an encoded preview before choosing.')
    (args.out/'palette.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
