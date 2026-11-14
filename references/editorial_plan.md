# 编辑计划合同

`validate_editorial_plan.py` 面向“选题完成、正式渲染之前”的 JSON 编辑计划。它检查证据是否齐全、状态是否自洽，不读取视频像素，也不替代人工听看。

## 最小结构

```json
{
  "stage": "preview",
  "themes": [{"id": "learning", "name": "学习方法"}],
  "name_corrections": [
    {"wrong": "旧称", "correct": "已确认名称", "source": "user correction"}
  ],
  "source_registry": [
    {"source_ref": "source/interview.mp4", "sha256": "source-fingerprint"}
  ],
  "identity_map": [
    {
      "person_id": "speaker-a",
      "public_name": "讲者甲",
      "status": "confirmed",
      "confirmed_by": "user",
      "evidence": {
        "voice": "source 00:12-00:18",
        "visual": "group frame left"
      }
    }
  ],
  "clips": [
    {
      "id": "I-01",
      "theme_id": "learning",
      "series_order": 1,
      "theme_basis": "片段围绕学习方法展开",
      "topic_id": "topic-03",
      "title": "一个可独立理解的判断",
      "source_windows": [{"start": 12.0, "end": 48.5}],
      "speakers": ["speaker-a"],
      "dialogue_relation": "question_response",
      "interaction_summary": "问题、回应和限定条件仍在同一个片段里",
      "selection_basis": "topic_and_dialogue_unit",
      "selection_reason": "保留回应对问题的直接推进",
      "layout": "wide",
      "interaction_visible": true,
      "composition": {
        "interaction_visible": true,
        "evidence": "opening/middle frame review"
      },
      "chapters": [
        {"start": 0, "label": "问题", "semantic_basis": "提出核心问题"},
        {"start": 18.4, "label": "回应", "semantic_basis": "回应给出判断"}
      ],
      "copy_status": "draft",
      "machine_qc": "pending",
      "human_review": {
        "identity": "pending",
        "audio": "pending",
        "semantic": "pending",
        "visual": "pending"
      }
    }
  ],
  "batch_audit": {"chapter_reviewed": true},
  "state": {"status": "preview", "canonical_manifest": "plans/20261016.json"}
}
```

## 字段规则

- `identity_map[].person_id` 是规格里唯一使用的人物键；显示名不能从镜头在场自动推断。确认身份要有 `confirmed_by` 和至少一种原声、画面或源时间证据。用户改名时在人物条目记录 `correction` 与 `correction_note`，旧 ASR 名称不能继续作为显示名。
- `clips[].speakers` 只填人物键。两人及以上必须有 `dialogue_relation`、`interaction_summary` 和选段理由；`person_quota`、`person_first`、`speaker_quota` 不能作为选段依据。
- `layout` 使用 `solo`、`two_shot` 或 `wide`。`solo` 必须写当前说话人、居中证据和为何不损失互动；双人或全景必须确认互动仍在画面中。存在 `crop` 时必须同时有 `crop_evidence`。
- `chapters` 默认必须为 2–3 段，首段 `start` 为 0，随后严格递增；每段有真实语义标签和 `semantic_basis`，并对应原声中的实际语义转折。若内容确实无法形成两个独立转折，只能停留在候选阶段并写明原因，不能作为正式交付。
- `copy_status`、`machine_qc` 和 `human_review` 分开记录。`formal` 或 `delivered` 还要求 `copy_confirmation.status=user-confirmed`、非空 `revision_id`、所有机器 QC 为 `passed`、四项人工审阅均为 `approved`，并有一个 `state.canonical_manifest`。
- `source_registry` 在正式阶段必须包含源文件引用和指纹；`state.status` 必须与当前阶段一致，`state.conflicting_manifests` 必须为空。交付说明、审阅索引和正式清单若出现数量或状态冲突，应先合并为一个 canonical manifest，再继续渲染。

运行：

```bash
python3 /path/to/interview-to-short-video-skill/scripts/validate_editorial_plan.py plan.json --stage preview
python3 /path/to/interview-to-short-video-skill/scripts/validate_editorial_plan.py plan.json --stage formal --json
```

整批必须提供 themes，并让每条 theme_id 引用其中一项，series_order 在同主题内唯一，theme_basis 说明语义归属。完整输出见 [主题输出](themes.md)。

## 选段与画面判断

先建立整段采访的主题地图，再确定候选窗口。每条候选应有发言顺序、选段理由和计划布局；检查“这、他、所以”等指代能否脱离长片理解。时长不机械按 60 或 90 秒截断，最后一个字幕词的 end 也不是天然片尾，应听审尾音、呼吸和下一句是否闯入。

多人片至少记录两种构图方案；solo 说明当前说话人及为何不破坏问答关系，two_shot/wide 确认互动仍在画面内。开头让观众看清当前说话者，用声音、口型和镜头相互印证，不继承其他项目人名或左右位置。

章节表是动态顶部角标和进度条的语义来源，每个转折前后抽帧核对实际切换。每条短视频至少拆成两个章节；不把模板最大段数当作每条段数。
