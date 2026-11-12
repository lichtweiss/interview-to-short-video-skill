#!/usr/bin/env python3
"""Export/apply one maintained Markdown sheet for every fixed on-screen text."""

import argparse
import copy
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import quote

LABELS = {
    "title": "主标题",
    "subtitle": "副标题",
    "descriptor": "中间小字说明",
    "footer": "底部角标",
    "palette.accent_color": "强调色（十六进制）",
    "palette.reason": "选色依据",
    "font_sizes.title": "主标题字号",
    "font_sizes.subtitle": "副标题字号",
    "font_sizes.descriptor": "说明字号",
    "font_sizes.footer": "角标字号",
    "font_sizes.caption": "口述字幕字号",
    "font_sizes.navigation": "章节字号",
}
DEFAULTS = {
    "title": 66,
    "subtitle": 72,
    "descriptor": 29,
    "footer": 27,
    "caption": 56,
    "navigation": 29,
}
MEDIA_PATHS = ("source", "srt", "audio_source", "style", "font_file")


def items(data):
    return data if isinstance(data, list) else [data]


def identifier(spec):
    return str(spec.get("id", spec.get("no", "01")))


def fields(spec):
    result = {key: spec.get(key, "") for key in ("title", "subtitle", "descriptor", "footer")}
    if spec.get("footer_policy") == "explicitly_omitted" and not result["footer"]:
        result["footer"] = "[留空]"
    for i, chapter in enumerate(spec.get("chapters", [])):
        result[f"chapter.{i+1}"] = chapter["label"] if isinstance(chapter, dict) else chapter
    result["palette.accent_color"] = spec.get("palette", {}).get("accent_color", "")
    result["palette.reason"] = spec.get("palette", {}).get("reason", "")
    for key, default in DEFAULTS.items():
        result["font_sizes." + key] = spec.get("font_sizes", {}).get(key, default)
    return result


def encode(text):
    return html.escape(str(text), quote=False).replace("|", "&#124;").replace("\n", "<br>")


def load_specs(path):
    raw = path.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, (dict, list)) or not items(data):
        raise ValueError("Specifications must be a nonempty object or array of objects")
    if not all(isinstance(spec, dict) for spec in items(data)):
        raise ValueError("Specifications must be a nonempty object or array of objects")
    ids = [identifier(spec) for spec in items(data)]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate clip IDs")
    return data, hashlib.sha256(raw).hexdigest()


def sheet_header(digest):
    return [
        "# 画面文字编订",
        "",
        "这是正式制作前的文案确认单。先修改表格最后一列，确认后再把下方状态改为 user-confirmed，才允许 apply 和正式渲染。"
        "主标题和底部角标默认必填；只有用户明确要求不显示底部角标时，才填写 [留空]。每条编号对应一条视频。",
        "字号按 1080×1920 画布像素填写；强调色填写 #RRGGBB。大改字号后重新检查遮挡与溢出。",
        "这是文字与字幕控制的中途审阅入口：表内修改影响固定标题、章节、角标与字幕字号；逐字字幕内容和时间请打开下面的 SRT 链接修改。"
        "修改后必须重新 apply 并渲染，已有 MP4 不会自动更新。",
        "现在等待用户编辑并确认；只有用户明确接受初稿并授权生产，才可使用 --accept-default，"
        "同时以 --approval 记录实际确认来源。沉默不是同意。",
        "",
        f"<!-- base-sha256: {digest} -->",
        "<!-- copy-status: needs-user-review -->",
        "",
    ]


def clip_sheet_lines(spec, specs_path):
    no = identifier(spec)
    lines = [
        f"## {no}",
        "",
        "| 编号 | 字段（请保留） | 用途 | 内容 / 数值（修改此列） |",
        "|---|---|---|---|",
    ]
    for key, value in fields(spec).items():
        label = LABELS.get(key, "章节" + key.split(".")[-1])
        lines.append(f"| {encode(no)} | {key} | {label} | {encode(value)} |")
    if spec.get("srt"):
        subtitle = (specs_path.resolve().parent / Path(spec["srt"]).expanduser()).resolve()
        link = quote(str(subtitle), safe="/:")
        lines += [
            "",
            f"逐字口述字幕：[{encode(no)} SRT](<{link}>)。"
            "请同时校订内容与时间；本表控制字幕字号，不代写逐字字幕。",
        ]
    if spec.get("theme_id"):
        lines += [
            "",
            f'主题归属：{encode(spec["theme_id"])}；'
            f'系列内顺序：{encode(spec.get("series_order", "未指定"))}。'
            "归属如需调整，应先更新源规格，再重新导出编订表。",
        ]
    return lines + [""]


def export_sheet(data, digest, specs_path, sheet_path):
    if sheet_path.exists():
        raise FileExistsError("Keep editing the existing sheet, or choose a new filename")
    lines = sheet_header(digest)
    for spec in items(data):
        lines.extend(clip_sheet_lines(spec, specs_path))
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_path.write_text("\n".join(lines), encoding="utf-8")


def check_confirmation(text, digest, approval, accept_default):
    if f"<!-- base-sha256: {digest} -->" not in text:
        raise ValueError(
            "Source specs changed since sheet export; reconcile timing/spec changes before applying copy"
        )
    if not approval or not approval.strip():
        raise ValueError(
            "apply requires --approval with the actual user confirmation or its reference"
        )
    if not accept_default and "<!-- copy-status: user-confirmed -->" not in text:
        raise ValueError(
            "文案尚未确认：请先由用户校定画面文字，再将 copy-status 改为 user-confirmed"
        )


def read_rows(text, specs):
    expected = {(identifier(spec), key) for spec in specs for key in fields(spec)}
    rows = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [
            html.unescape(cell.strip()).replace("<br>", "\n") for cell in line.strip("|").split("|")
        ]
        if len(cells) != 4:
            raise ValueError("Use &#124; for literal | inside a cell")
        no, key, _, value = cells
        if no == "编号" or no.startswith("---"):
            continue
        if (no, key) in rows or (no, key) not in expected:
            raise ValueError(f"Duplicate or unknown row: {no}/{key}")
        rows[no, key] = value
    if set(rows) != expected:
        raise ValueError("Missing rows; blank optional text rather than deleting its row")
    return rows


def set_chapter(spec, key, value):
    if not value.strip():
        raise ValueError(f"{identifier(spec)}: empty chapter label")
    index = int(key.split(".")[1]) - 1
    if isinstance(spec["chapters"][index], dict):
        spec["chapters"][index]["label"] = value
    else:
        spec["chapters"][index] = value


def set_palette_value(spec, key, value):
    field = key.split(".")[1]
    if value:
        spec.setdefault("palette", {})[field] = value
    elif "palette" in spec:
        spec["palette"].pop(field, None)


def apply_value(spec, key, value):
    if key == "title" and not value.strip():
        raise ValueError(f"{identifier(spec)}: title is empty")
    if key.startswith("chapter."):
        set_chapter(spec, key, value)
    elif key.startswith("font_sizes."):
        if not value.isdigit() or not 12 <= int(value) <= 120:
            raise ValueError("Font size must be integer 12..120")
        spec.setdefault("font_sizes", {})[key.split(".")[1]] = int(value)
    elif key.startswith("palette."):
        set_palette_value(spec, key, value)
    elif key == "footer" and value == "[留空]":
        spec[key] = ""
        spec["footer_policy"] = "explicitly_omitted"
    else:
        spec[key] = value
        if key == "footer":
            spec["footer_policy"] = "provided"


def validate_palette(spec):
    palette = spec.get("palette")
    if palette and (
        not re.fullmatch("#[0-9A-Fa-f]{6}", palette.get("accent_color", ""))
        or not palette.get("reason")
    ):
        raise ValueError("Provide both accent color and selection reason")


def record_compiled_inputs(spec, args):
    # Resolve against the original specs, not the compiled output directory.
    for key in MEDIA_PATHS:
        if key in spec:
            spec[key] = str((args.specs.resolve().parent / Path(spec[key]).expanduser()).resolve())
    spec["copy_sheet"] = str(args.sheet.resolve())
    spec["copy_sheet_sha256"] = hashlib.sha256(args.sheet.read_bytes()).hexdigest()
    spec["copy_confirmation"] = "confirmed"
    spec["copy_approval"] = {
        "mode": "default-accepted" if args.accept_default else "edited-confirmed",
        "evidence": args.approval.strip(),
    }
    if spec.get("srt"):
        spec["srt_sha256"] = hashlib.sha256(Path(spec["srt"]).read_bytes()).hexdigest()


def apply_sheet(data, digest, args):
    if args.out.resolve() == args.specs.resolve() or args.out.exists():
        raise ValueError("Write compiled specifications to a fresh path; preserve source specs")
    text = args.sheet.read_text(encoding="utf-8")
    check_confirmation(text, digest, args.approval, args.accept_default)
    rows = read_rows(text, items(data))
    result = copy.deepcopy(data)
    for spec in items(result):
        no = identifier(spec)
        for key in fields(spec):
            apply_value(spec, key, rows[no, key])
        validate_palette(spec)
        record_compiled_inputs(spec, args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["export", "apply"])
    parser.add_argument("specs", type=Path)
    parser.add_argument("sheet", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--approval", help="Actual user confirmation quote or message reference; required for apply"
    )
    parser.add_argument(
        "--accept-default",
        action="store_true",
        help="Use only after the user explicitly accepts the first draft and authorizes production",
    )
    return parser


def main():
    parser = argument_parser()
    args = parser.parse_args()
    data, digest = load_specs(args.specs)
    if args.command == "export":
        export_sheet(data, digest, args.specs, args.sheet)
        print(args.sheet.resolve())
    else:
        if args.out is None:
            parser.error("apply requires --out")
        apply_sheet(data, digest, args)
        print(args.out.resolve())


if __name__ == "__main__":
    main()
