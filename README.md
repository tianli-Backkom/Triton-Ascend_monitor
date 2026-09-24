# Triton-Ascend 门禁效率监控

采集 [triton-lang/triton-ascend](https://github.com/triton-lang/triton-ascend) 最近 72 小时的 PR 门禁任务，生成可离线打开的单文件看板。

看板展示：

- 每次 PR 提交或手动重跑对应的 E2E 时长趋势
- NPU Job 最长排队时长趋势
- 所选时间范围的平均值、P50、P90 和有效样本数
- 合入分支、状态和时间范围联动筛选
- PR、GitHub Actions、重点 NPU Job 的直达链接

## 自动更新与发布

工作流 [Refresh dashboard and deploy Pages](.github/workflows/refresh-pages.yml) 每天北京时间 08:00 重新采集最近 72 小时数据并发布到 GitHub Pages，也支持在 Actions 页面手动运行。

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
