# Skill design review · 技能设计诊断

Reviewed: 2026-11-13. Scope: the public skill, supporting contracts, helper scripts, tests, and landing pages. This is a maintenance diagnosis, not a claim that the open items below are implemented.

**Finding:** local rendering and file validation have useful automated evidence. Editorial quality and approval depend on a trusted operator, and the current template has narrower limits than the overall editing goal. Neither a static score nor passing synthetic tests establishes complete interview-editing reliability.

**Priority:** add a consented real-interview behavioral evaluation; bind review records to actual source/output artifacts; then simplify renderer code. Keep project facts separate from reusable instructions. The bilingual README is an entry point; detailed instructions and tool labels currently remain mainly Chinese.

## 判断依据

用四个问题检查当前实现：目标是否清楚；成功是否可判断；资源和边界是否明确；输出是否有可检查的合同。过程约束只在确实影响结果时保留，模板偏好不能升级为普遍编辑规律。

本轮主要读者是想判断是否采用、如何接入现有转写，以及如何审阅成片的编辑者和技术协作者。首页因此从片段是否完整、用户能得到什么和需提供什么开始，再引导到环境、命令与详细合同，不以作者的迭代历史开场。

设计参考（不是依赖或背书）：

- [Yage context-infrastructure](https://github.com/grapeot/context-infrastructure/tree/6811a4f69fe7ee5a86bd4ee8cb06ab00572bfb2c)：借鉴可复用基础与个人上下文分工的表达。
- [Lizheng Open Context](https://github.com/sunyuzheng/lizheng-open-context/tree/cb1c821a023840141f72e4297ce8ea2871d911b9)：借鉴来源归属和派生判断分层，尤其是[回答协议](https://github.com/sunyuzheng/lizheng-open-context/blob/cb1c821a023840141f72e4297ce8ea2871d911b9/docs/answering-contract.md)。

另对照维护者自己的 Skill 写作原则（结果确定性、enabling 而非过度 SOP），Skill Creator 的范围控制与渐进披露原则，以及 Reader-Oriented Writing 的读者问题、代价、收益与证据顺序。私人上下文原文不随此报告公开。

## 潜在问题与处理优先级

| 优先级 | 现有证据 | 风险与建议 | 本轮状态 |
|---|---|---|---|
| P1 | [tests](../tests/test_workflow.py) 使用彩条、提示音和预设主题，不含真实采访语义任务 | 测试能证明渲染和合同，不能证明独立助手选段、分组、命名及保持限定条件的能力。用已获许可的真实采访做盲评：给助手素材和任务，不给预期答案；人工核对时间窗、人物归属、删掉的限定条件和主题理由 | 首页已明确未验证范围；行为评估待做 |
| P1 | [校验器](../scripts/validate_editorial_plan.py) 的 `_promotion` 只检查 source_ref/sha256/manifest 字段非空与声明状态；合成探针把源文件改为不存在、指纹写成 `not-a-real-hash`、清单写成不存在，formal 仍通过 | 结构一致不等于实际文件已核实。增加单独的产物审计：打开清单，核对源片与输出指纹、实际 QC、审阅版本。不要把 `valid=true` 描述为端到端验收 | 明确工具边界；强绑定待实施 |
| P1 | [渲染器](../scripts/render_interview.py) 仅在规格含 copy_sheet 时检查编订记录；合成示例可无确认直接渲染。`--approval` 接受调用者提供的文本 | 这是可信助手流程，无法验证是谁真正确认。提供工作流入口可减少误跳，但不要以新入口冒充身份认证。需要正式/预览模式时必须显式区分，仍保留原样例用途 | 双语首页说明；统一入口待评估 |
| P2 | [SKILL.md](../SKILL.md) 把 1–3 章节写在硬门槛；[renderer](../scripts/render_interview.py) 固定 1080×1920，层位置也与画布绑定 | 当前实现限制容易被读成语义规则。通用目标应是完整意群；现模板不适合时说明限制并改模板，不为满足段数改写内容 | 首页与技能入口已标注模板范围；可配置渲染器未实施 |
| P2 | [copy_sheet](../scripts/copy_sheet.py) 的编译结果保存 `copy_approval` 和文件指纹；编辑计划另用 copy_confirmation.status/revision_id；[export_review](../scripts/export_review.py) 核对部分规格字段和 QC，但不核对全部审阅依据 | 同一确认有多个状态载体，容易遗漏同步。后续可让同一份版本化证据生成确认和清单；旧用户文件需迁移方案，不能本轮静默改 schema | 记录为维护优先项 |
| P2 | [create_demo](../scripts/create_demo.py) 生成 plan 时没有 render_dir；渲染输出与主题导出之间需额外关联 | 新用户照抄不完整命令会卡住。文档必须讲明绑定哪条渲染结果；后续可增加显式 attach 命令或演示编排，不隐式猜目录 | 两份 README 已加入精确字段操作并实际试跑 |
| P2 | [renderer](../scripts/render_interview.py) 此前有大函数与多个文档重复描述流程；Plugin Eval 本轮 68/D → 77/C | 降低修改可控性；把实质责任拆开，每次保持输出行为和拒绝条件。静态预算将脚本/参考整体计入，不等于每次调用真的消耗这些 token，不应删掉必要依赖说明来提分 | 已拆分渲染、导出、配色和示例的职责，消除长函数/长行告警；静态预算及复杂度告警仍保留 |
| P2 | 公开首页此前仍有“尚未上传”“待批准”；原目录/安装副本与公开仓库并存 | 发布状态可能过时；维护者可能修改错版本。用仓库和 commit 标识当前公开版本，更新时同步语言入口，勿把旧本机副本自动覆盖成新安装 | 本轮移除陈旧首页状态，增加维护声明和文档路由 |

P1 表示可能误导交付判断，P2 表示可用性与维护风险；此处不是安全漏洞严重性评级。已存在的机器/人工状态分离、用户纠错优先、源时间窗、尾音和原声约束值得保留，不因为精简文档而删除。

## 验证与后续验收

本轮实际运行了上述合成 formal 探针，以及 README 的示例渲染和主题导出，结果与边界说明一致。探针仅用于验证结构校验的能力边界，不是真实用户确认。现有回归扩为 13 项，增加无效渲染设置与 QC 后产物被修改时拒绝导出两类行为，继续作为工具层证据。

后续改进的验收应看行为：真实采访评估需给出源时间与人工审阅差异；产物审计需在缺源片、改字幕、过期 QC 或错版本时明确失败；渲染器重构需保留导出及拒绝行为。中英文首页互链、示例步骤和能力边界应保持一致。缺少这些证据时，不能声称上述维护项已解决。

## Plugin Eval 优化记录

下表是 `dd4e6b0` 重构检查点的对比；后续增加转写前提提示及沙盒复现资料，预算估算会随文件内容变化。

使用同一 Plugin Eval 0.1.0 实现（本机插件版本 d420d130）、默认规则、同一仓库根目录复跑，没有修改评分器或排除文件来提高分数。

| 项目 | 改前 | 改后 |
|---|---|---|
| 静态分数 | 68 / D | 77 / C |
| SKILL.md 调用估算 | 1,049 tokens | 668 tokens（减少约 36%） |
| Python 超过 120 字符的行 | 48 | 0 |
| 最长函数（评分器启发式） | 159 行 | 79 行 |
| 渲染器最长函数（同一启发式） | 159 行 | 64 行 |

入口保留目标、结果标准、确认门槛和验收，按任务跳转到字段与命令合同。渲染器将固定画面、ASS 字幕、时间线、编码、抽帧和 QC 分开；导出器先检查再复制，配色把采样与选色分开。没有改文字确认授权、晋级规则或输出合同。

验证使用四组合成规格，包括横画面、竖画面裁切、1/2/3 章节、非零源起点、独立音源起点、字体覆盖、高亮、滤镜和不同尾部设置；每组重构前后的 MP4、PNG、SRT、ASS、三张抽帧字节一致，QC JSON 相等。导出器与配色工具的合成输出目录也一致。此结果限定于这些合成条件，不代表真实采访的语义评估。

仍有三项扣分：

- **全部支持文件的静态预算（14 分）**：包括脚本源码、测试、双语首页等，并非一次实际调用；本轮格式化和职责拆分使该总估算增加。不要把移动到 references 当成能减少这个指标，评分器仍会遍历它。后续若提供精简安装包，要真实维护安装与源码发布两种产物并分别验证，不能用临时裁掉文件的目录冒充同口径提分。
- **复杂度启发式（4.5 分）**：评分器的 Python 实现用整份文件的分支总数初始化“最大函数复杂度”，所以即使职责已经拆开仍报告 221。它提示进一步审阅，不是可靠的单函数复杂度测量。修改评分器应单独报告版本与口径，不能和本次分数直接比较。
- **发布文档（4.5 分）**：README 和 CONTRIBUTING 触发通用的“技能附带额外文档”警告。本仓库明确用于 GitHub 公开分发，保留这两份必要入口。另有缺少覆盖率产物的信息项，扣 0.25 分；未为提分伪造覆盖率。

本轮得分增加来自两项各 4.5 分的真实可读性改进。下一阶段更有价值的验收是获准真实素材的选段/主题行为评估，以及计划、源片、字幕、QC、审阅版本与实际产物的绑定；这两项不能由静态分数代替。当前评分器仍将风险标为 high（静态预算失败），未宣称评估全绿。

已安装 Plugin Eval 的维护者可在仓库根目录复跑，报告放在仓库之外，以免把报告自身计入下一次预算（此版本遍历器不读取 .gitignore）：

```bash
eval_dir="$(mktemp -d)"
plugin-eval analyze . --format json > "$eval_dir/before.json"
# 完成改进后，用同一版本、同一路径与默认规则复跑：
plugin-eval analyze . --format json > "$eval_dir/after.json"
plugin-eval compare "$eval_dir/before.json" "$eval_dir/after.json" --format markdown
```
