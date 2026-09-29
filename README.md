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
$env:GH_TOKEN = '<GitHub Token>' # 可选；建议设置以提高 API 配额
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
