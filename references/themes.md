# 整批主题、系列与输出

语义分类由读取完整采访及项目上下文的编辑助手执行。默认自动提出分类，并让用户在中途文字审阅环节调整；这不是按人物数量或词频硬分组。整个素材只有一个成立的主题时使用一组，不能为了“不同主题”强行拆碎对话。

编辑计划顶层 `themes`：`[{"id":"learning","name":"学习方法"}]`。每条 clips 记录：`theme_id: "learning"`、`series_order: 1`、`theme_basis: "为什么属于这一主题"`。原有 `topic_id` 标识该条具体论题，`chapters` 是该条内部转折，不替代批次主题。series_order 在同主题内必须唯一且为正整数。可增加 secondary_tags，但不重复统计同一条片。

渲染规格同样带 theme_id / series_order，copy_sheet 导出时显示。修改主题归属要先更新编辑计划和规格，再重新导出编订文档，使主题、系列标签和观看顺序同时对齐。

每条渲染完成后，在编辑计划 clips 条目增加 `render_dir`（相对编辑计划目录），指向含 video.mp4、captions.srt、qc.json 的渲染目录。随后：

```bash
python3 /path/to/skill/scripts/export_review.py /project/plan.json --out /project/review_by_theme
```

工具校验计划、机器解码状态与 MP4 指纹，然后生成编号主题目录、系列内序号子目录、index.html 观看页与 manifest.json 清单。每条 MP4 和字幕只复制到其主主题；中文名称可用，HTML 会转义标题。输出目录必须不存在。预览保留 preview 状态与 pending 人工项，不自动宣称 formal 或 delivered。

正式交付前需把实际机器与人工结果更新回同一份计划，再做 formal 校验。主题输出是文件组织功能，不能证明归类语义正确、片段内容完整或已获得发布许可。

导出器会核对渲染规格中的 id/theme_id/series_order/title、QC 源起止点、MP4 和字幕指纹。连续单窗应直接对应 source_windows；多窗预剪为中间片时，clips 中显式增加 `intermediate_mapping: {"render_window": {"start": 0, "end": 42}, "evidence": "时间映射表路径与人工核对记录"}`，原 source_windows 仍保留原片窗口。工具只能检查中间片时间是否一致，映射语义和回源准确性仍需人工核对。
