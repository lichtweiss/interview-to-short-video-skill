# 生产规格与命令

## 输入合同

附带渲染器面向**已经选好并校订的连续片段**，不自动选题或转写。样片前先完成 [编辑计划合同](editorial_plan.md) 并以 preview 校验，实际听看与 QC 完成后再以 formal 校验晋级；渲染器本身不会替你判断人物身份、对话关系或章节是否有语义。使用 Python 3.10+、Pillow，以及支持 `ass` 滤镜的 FFmpeg 和 ffprobe。字体提供同一个真实字体文件和它的字体家族名称，保证 Pillow 与 libass 使用一致字体；字体变更后必须重新检查模板。示例使用占位字体路径；运行时必须替换为本机真实字体文件与 family。建议使用支持中文的 Noto Sans CJK；不随本仓库分发字体。

配置文件路径以 JSON 文件所在目录为基准，输出目录由命令指定且必须不存在，以防覆盖旧片。示例：

```json
{
  "id": "01",
  "theme_id": "learning",
  "series_order": 1,
  "source": "source/interview.mp4",
  "source_start": 83.88,
  "source_end": 187.56,
  "speech_end": 103.40,
  "srt": "captions/01.srt",
  "title": "AI课程",
  "subtitle": "为什么要边做边改？",
  "layout": "portrait",
  "crop": [520, 0, 880, 1080],
  "chapters": [
    {"label": "小课程", "start": 0},
    {"label": "快速迭代", "start": 47.20},
    {"label": "AI时代", "start": 76.40}
  ],
  "tail": {"target_pause": 1.0, "caption_hold": 0.5},
  "palette": {"accent_color": "#E7C86F", "reason": "此示例沿用用户认可的旧模板，其他素材重新提取或沿用品牌色"},
  "font_file": "/path/to/NotoSansCJK-Regular.ttc",
  "font_family": "Noto Sans CJK SC"
}
```

示例的切点、口述结束和章节时间只展示字段意义，不能直接当作当前项目已听审结果。

| 字段 | 语义 |
|---|---|
| `source_start/source_end` | 原文件秒数；end 应保留完整语音，允许包含已检查的自然停顿 |
| `speech_end` | 最后实际语音结束在**片内**的秒数；通过听审核对，不从最后一个 SRT end 自动猜测 |
| `srt` | 从片内 0 开始的字幕文件；连续源片段时，字幕源时间减去 source_start |
| `layout` | `portrait` 填满人物区域，`wide` 完整保留横画面；都有 1080×1920 外画布 |
| `crop` | 可选原图裁切 `[x,y,width,height]`；先目检人物位置再填写，并在上游编辑计划写 `crop_evidence`；portrait 未提供时居中填充只适合候选检查，正式片应明确裁切依据 |
| `chapters` | 1–3 段，严格递增，首段从 0 开始；更多段应简化或换模板，不能静默截掉 |
| `tail.target_pause` | 最后实际语音结束到成片结束的目标停顿秒数，默认 1；已有自然停顿计入其中 |
| `tail.caption_hold` | 末句字幕最晚可显示到 speech_end 后多少秒，默认 0.5；不缩短已校订字幕 |
| `audio_source/audio_start` | 可选独立声音来源及其对应起点；用 M4A 修复缺声时先建立同步偏移，不直接套视频时间 |
| `descriptor/footer` | 可选固定文字，默认空；不自动添加标语或访谈身份 |
| `highlight_terms` | 可选关键词列表，每条字幕最多高亮其中一个词；由内容决定，默认不随机高亮 |
| `style` | 可选 style JSON 路径，缺省采用附带模板 |
| `palette` | 强调色 accent_color 与选择理由 reason；未指定已确认 style 时必须填写，禁止无条件套金色 |
| `font_sizes` | 从文案表编译的各层字号，渲染时覆盖对应模板值 |

字幕从源时间转换到片内时间：`t_out = t_source - source_start`。多段拼接时，每段为 `t_out = 前面保留片段总长 + t_source - 当前段起点`。字幕跨删段边界时重分句，不能只减一个统一偏移。分块转写回源时间还需要先加分块偏移，避免混淆三套时间。

## 收尾实现

定义 `content_duration = source_end - source_start`，`existing_pause = content_duration - speech_end`，额外停留为 `max(0, target_pause - existing_pause)`。以帧向上取整，默认 25 fps。它避免给本来已有一秒停顿的片段再机械加一秒。

若源片还有自然表情和环境声，先在听审后增加 source_end，让它成为内容片的一部分；渲染器补足的部分采用末帧定格和静音。它不自动寻找末句、不识别下一句、不修复已切掉的尾音。片尾处理详情写入检查记录。

渲染顺序为：截取与人物构图 → **对干净画面 tpad 定格延长** → 固定 PNG → ASS。把 tpad 放在字幕合成之后会连最后一帧字幕一起永久定格，字幕就无法按时消失。末句阅读停留属于字幕时间，不是语音时间。章节进度在内容段结束时完成，额外收尾期间保持最后章节状态。

音频先按实际内容长度截取，`apad` 补足静音，不在尾音上做淡出。附带渲染器输出 AAC，会重新编码音频，不能声称音频数据完全没变。对现有成片只加定格尾巴时，可复制已有 AAC，让音轨自然早于视频结束；此模式以音频数据哈希相等作检查，不能强求音视频流时长完全相同。

## 运行

```bash
python3 /path/to/interview-to-short-video-skill/scripts/render_interview.py \
  /project/cuts/01.json --out /project/staging/01
```

`--encoder libx264` 是默认软件编码；当前 Mac 可显式选 `--encoder h264_videotoolbox` 加速。脚本生成 `video.mp4`、`captions.srt`、`captions.ass`、`overlay.png`、`spec.json`、`qc.json`、三个抽帧和 `render.log`。`qc.json` 只宣称机器可测事实，身份、内容听审、语义和视觉人工验收保持 pending，后续按实际结果更新。不要把 `machine_checks=passed` 复制成正式交付状态；交付清单应引用一个 canonical manifest，并把候选、正式和已交付数量分开。

初次选色：`python3 /path/to/skill/scripts/suggest_palette.py /project/source.mp4 --start 20 --end 80 --out /project/palette_review`。查看 source_samples.jpg 和 palette.png 后，选定色填入固定文字文档。输出对比度依据所填承托底色，只是可读性初筛；生成片段目检后才锁定。

语音识别已由本机已有 Qwen 脚本承接时直接复用；没有该环境时先查看可用 Qwen 安装及用户授权的数据处理方式。渲染器不捆绑模型、不自动下载模型、不上传素材。

## 本次返工揭示的几个检查点

- 标题缺失要在**最终 MP4**上检查。JSON 有字不等于 PNG 画了字，PNG 有字也不等于合成后可见。
- 同一文字应只有一个所有者。固定标题在 PNG，口述字幕与动态章节在 ASS；不能让旧片自带字幕与新字幕同时存在。
- ASS 的位置和动画参数使用单个反斜杠，不把 JSON 转义后的双反斜杠原样写入 ASS。
- 外接盘恢复后，抽取源片与缓存同一时刻的画面对照，确认缓存没有错片或错时间。
- 自动解码通过不能证明意群完整、人物身份正确或字幕听写准确。验收记录不能把未做的听审写成通过。
- 正式交付目录与候选池数量分开登记。小修走当前清单，避免导入带顶层批处理副作用的旧渲染脚本。
- 若多人源片使用 `crop`，在编码前核对 `identity_map` 的画面位置和 `crop_evidence`；不能把“左侧/右侧”当成跨素材通用映射。
- 章节数组是动态角标和进度段的唯一输入。渲染后抽查每个章节切换点；如果整批规格都只有一个章节，先回到编辑计划逐条说明原因。
