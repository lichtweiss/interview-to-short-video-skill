# 贡献与问题复现

先运行 doctor、`python -m unittest discover -s tests -v`。修改渲染或模板后，用 create_demo 跑一次完整渲染、解码与抽帧；涉及真实对话语义时另做人工听审。

提 issue 时提供操作系统、Python/Pillow/FFmpeg 版本、命令、最小匿名规格、错误与预期。不要上传客户录音、姓名、密钥或私人绝对路径。优先用生成的彩条/音频复现。新依赖需说明用途、平台与许可；ASR 与渲染依赖保持隔离。
