# Triton-Ascend 门禁效率监控

采集 [triton-lang/triton-ascend](https://github.com/triton-lang/triton-ascend) 最近 72 小时的 PR 门禁任务，生成可离线打开的单文件看板。

看板展示：

- 每次 PR 提交或手动重跑对应的 E2E 时长趋势
- NPU Job 最长排队时长趋势
- 所选时间范围的平均值、P50、P90 和有效样本数
- 合入分支、状态和时间范围联动筛选
- PR、GitHub Actions、重点 NPU Job 的直达链接

## 自动更新与发布

工作流 [Refresh dashboard and deploy Pages](.github/workflows/refresh-pages.yml) 每天北京时间 08:00、13:00、18:00、20:00 重新采集最近 72 小时数据并发布到 GitHub Pages，也支持在 Actions 页面手动运行。

工作流每次从空证据目录重新采集。采集证据会作为 Actions artifact 保存 7 天，页面只发布 `index.html` 和 `batches.csv`。

## 本地生成

```powershell
$env:GH_TOKEN = '<GitHub Token>' # 强制推送历史的 GraphQL 查询需要认证
python dashboard.py --hours 72
```

仅使用已保存证据重新生成：

```powershell
python dashboard.py --from-evidence
```

## 测试

```powershell
node tests/test_ui.js
python -m unittest discover -s tests -v
```

## 数据质量保护

每次生成页面前，`quality.py` 校验 Jobs 分页完整性、NPU 识别覆盖、已完成任务时间戳及批次最大排队时长。校验失败写入 `evidence/quality-report.json` 并终止发布，保留上一份已发布页面。合法的零 NPU 样本不会被误判为失败。

GitHub 源时间戳倒置的任务显式标记异常，相关批次不参与排队统计，并写入质量报告 warnings；不再将负值截成零。仍排队、跳过及取消前未启动的任务允许没有最终排队值。

每次构建产生 `manifest.json`，发布后 `verify_deployment.py` 对公开页面的完整内嵌数据计算 SHA-256 并与构建结果比对，最多重试 8 次。失败会使 Actions 运行失败并生成错误注释及运行摘要；此检查发生在部署后，不自动回滚。

页面每分钟检查数据新鲜度。按北京时间 08:00、13:00、18:00、20:00 的计划及 90 分钟采集发布宽限期显示更新延迟提醒。Actions 失败的外部邮件通知由仓库订阅者的 GitHub 通知设置控制，本项目不配置邮件收件人。

## PR 关联证据

Fork PR 的 workflow `pull_requests` 和 commit 关联接口可能同时返回空数组。采集器优先使用 run 显式 PR 关联；回退以来源仓库、分支、真实 head SHA 或 PR 提交历史校验候选，查询包括已关闭 PR，并完整分页和缓存。PR 编号、标题、链接及目标分支均从 PR 元数据获取，不以运行标题或时间接近猜测关联，也不再按最近 run 覆盖 `pull_request_target` 的 SHA。

强制推送后，旧 SHA 可能从 PR 当前提交列表中消失。采集器完整分页读取 GraphQL `HeadRefForcePushedEvent`，使用 `beforeCommit`、`afterCommit` 和事件发生时间恢复历史 head；不使用 commit 作者时间替代事件时间。重跑保留原 run 创建时间及 SHA。

关联依据和强制推送事件写入 `evidence/pr-associations/`。无法唯一关联或 API 查询失败会保存 `pr-association-errors.json`，阻止本次发布；质量检查同时验证关联证据及聚合前后 PR/SHA 一致性。未知运行按 run ID 隔离，避免相同 SHA 被误并。

强推端点之间的普通追加提交也可能从当前 PR 提交列表消失。采集器通过 GitHub Compare API 证明旧 run SHA 是 run 创建之后某个 `beforeCommit` 的祖先，同时排除基础分支共同祖先；保留旧 SHA，避免把 `pull_request_target` 的基础 SHA 误认为 PR head。比较证据不完整、接口失败或多个 PR 同时匹配时仍阻止发布。

PR 上的 `Dashboard quality gate` 运行 python-tests、frontend-tests、collector-contracts 和 workflow-lint，全部成功才通过汇总门禁。可在修复分支手动运行 Refresh 工作流验证完整采集及构建；仅 main 分支部署 Pages。真实失败运行 38546744486 的 34 条历史记录保存在测试 fixture 中，作为离线回归样本。
