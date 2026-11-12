# 环境与依赖

从原始音视频开始，需要独立配置语音转文字（ASR）模型或获准的转写服务，再经校订与时间检查生成 SRT。本仓库负责后续编辑、文字确认与渲染，不包含 ASR 推理入口。已有可靠 SRT 可以直接接入；合成 demo 自带字幕，不能用于证明模型可用。

## 三层环境

| 层 | 需要什么 | 是否必需 | 本仓库做什么 |
|---|---|---|---|
| 编辑助手 | 可读取 SKILL.md 并执行本地命令的 Codex 或同类助手 | 自动辅助编辑时需要；脚本本身可独立使用 | 提供编辑约束与工具，不绑定特定 LLM/API |
| 渲染 | Python 3.10+、Pillow 12.1.0、FFmpeg、ffprobe、libass、libx264、可读字体文件及正确 family | 必需 | 截取连续片段，PNG/ASS 合成，AAC 重编码，抽帧与解码检查 |
| 转写与对齐 | Qwen3-ASR 或经许可的已有转写软件；必要时 Forced Aligner / 说话人分离 | 仅无可靠字幕时需要 | 不捆绑、不下载、不直接调用模型，消费校订后的 SRT |

CPU（中央处理器）足以运行默认 libx264 渲染；不要求 GPU（图形处理器）。macOS 可显式选择 h264_videotoolbox，但它不是默认路径，也不等于 CUDA。模型速度与内存取决于模型、片长和硬件；没有完成本项目的内存/实时率测量，不给出虚构最低内存保证。首次模型下载需要网络与磁盘空间，后续是否能离线取决于依赖与模型缓存。

## Qwen 名称与本机配置

核对日期：2026-11-12。[Qwen 官方项目](https://github.com/QwenLM/Qwen3-ASR) 发布 Qwen3-ASR-1.7B / 0.6B，以及 Qwen3-ForcedAligner-0.6B。ASR 是识别；Forced Aligner 是时间对齐，两者不能互换。这里没有将“千问 3.7”作为已证实型号。

作者现有本机 ASR 技能声明采用 Apple Silicon + MLX 的 Qwen/Qwen3-ASR-1.7B，并以 nvidia/Nemotron-3-Diarization 在 CPU 上做说话人分离。2026-11-13 已在现有独立 ASR 环境中，以离线缓存实际运行生成语音的 smoke：返回 3 条带时间转写记录。该测试发现一句听写错误；按已知合成台词校订后，SRT 已接入渲染器生成 MP4。这验证了这台机器的缓存链路，不验证全新模型安装、真实采访准确率或其他平台。

可选集成：[grapeot/asr-skill](https://github.com/grapeot/asr-skill)。这是独立项目，按其 README 在持久 checkout 内建立 Python 3.12 主环境及独立声学子环境，运行其 `init` / `doctor`；`doctor --no-load` 只查依赖，不证明模型能加载。不要把它的 torch / transformers / MLX 依赖安装进本仓库 .venv。安装前核对上游当时的平台、版本和许可；本仓库没有锁定整个 ASR 环境。

ASR 的 CSV/JSON 输出不是渲染器输入：需另行按源时间窗生成 SRT。本仓库没有通用 CSV→SRT 转换器；必须理解导出字段后显式转换，不能仅改扩展名。多人簇标签不是人物姓名，换文件后重新确认映射。

## 其他转写软件

已由软件导出的可追溯、经用户许可且校订后的 SRT 可以直接接入，不要求某个商业软件。若源文件已有全文字幕，连续切片需减去 source_start；有分块识别还需加回分块偏移。当前作者本机使用偏好是 Qwen3，本项目不自动改用 Whisper 或云转写。

输入必须为 UTF-8/UTF-8-BOM SRT、非空字幕、时间递增不交叠、落在片段内；不得包含 ASS 控制符 `{ } \`。字幕使用实际字体测量宽度。专业词、名字和最后尾音需听审。纯文本逐字稿缺少时间轴，不能直接交给渲染器。

## 字体与平台

提供真实 `.ttf` / `.otf` / `.ttc` 文件与匹配的 font_family。Pillow 用字体文件，libass 按 family 匹配，二者都要验证。推荐自行安装 [Noto CJK](https://github.com/notofonts/noto-cjk)，不复制 macOS 系统字体进仓库。doctor 验证文件可加载，不能证明所有汉字覆盖或 family 匹配正确；以实际编码画面为准。

配置中的源片/SRT/style/字体相对路径以规格 JSON 所在目录为基准，输出目录必须不存在。含空格与中文路径有自动回归测试。规格与文案表是可信本地输入，`video_filter` 是直接传给 FFmpeg 的高级参数；不要执行来源不明的规格。渲染依赖源片有视频与音频轨，无声片需显式提供同步音频。

## 排错

| 问题 | 检查和处理 |
|---|---|
| No module named PIL | 用当前虚拟环境 Python 安装 requirements.txt；不要混用系统解释器 |
| ass 滤镜缺失 | 更换启用 libass 的 FFmpeg，运行 doctor |
| 字体方框/样式错 | 核对中文覆盖与 family；重新查看编码抽帧 |
| 输出目录已存在 | 使用新版本目录，保留原输出，不直接覆盖 |
| 文案表指纹改变 | 再次 apply 到新规格，再导出；不绕过指纹 |
| 时间不在帧网格 | 当前模板 25 fps，source_end-source_start 应为 0.04 秒整数倍 |
| 转写/模型不可用 | 可继续登记与选题；无可靠字幕时不冒充已经对齐或听审 |
| 渲染中断 | 保留 render.log；修复原因后换新输出目录，未生成 qc.json 不算通过 |
