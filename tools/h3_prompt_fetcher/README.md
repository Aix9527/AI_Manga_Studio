# H3 Prompt Fetcher

在线抓取 tryminimax.asia 作者原创提示词全文（150 条，license review_required）。

## 状态

- `library.json` v2.0.0：222 条（72 条重构 MIT 全文 + 150 条作者索引）
- 150 条作者条目：`fulltext_status: pending`，含 `gallery_id` / `summary` / 来源链接
- 全文补充流程：`online_raw/`（raw）→ review → `approved` → 合并入 `library.json`

## 使用

```bash
python tools/h3_prompt_fetcher/fetch.py
```

分页说明：tryminimax 分页为客户端 JS 渲染（URL 参数无效），
第 2-10 页需用浏览器自动化逐页点击"下一页"后调用 `parse_page` 提取。

## 许可

- 72 条重构提示词：MIT（仓库 xianyu110/awesome-minimax-h3-prompts）
- 150 条作者原创：版权归原作者，使用前需 license 确认（线上图库索引 + 原帖链接见 `source`）
