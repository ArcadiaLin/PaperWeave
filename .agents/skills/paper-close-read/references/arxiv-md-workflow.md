# arXiv Markdown Workflow

## Goal

用户提供 arXiv ID 或 arXiv URL 时，用仓库里的 arxiv2md（`packages/arxiv2md`）把论文直接抓成 Markdown 精读工作目录，不经过 PDF。

## Usage

```bash
scripts/prepare_arxiv_md.sh <arxiv-id-or-url> <output-dir>/
```

产出：

```text
paper-workdir/
├── source.md          # 必备：arxiv2md 转换的论文全文
├── images/            # 下载的论文图片（可能不存在，见下）
│   └── index.md
├── evidence_map.md    # 必备（后续步骤建立）
└── analysis.md        # 必备（最终成品）
```

脚本内部在仓库共享 uv 环境里运行 `arxiv2md <id> -o source.md --download-images`，然后把 `source.images/` 规范化为 `images/` 并改写图片链接。抓取结果缓存在仓库根的 `.arxiv2md_cache/`，重复运行不会重复请求。

## source.md 的结构

- 文件头有 Title / ArXiv / Authors / Sections 摘要行。
- 章节标题上方带 `<a id="S3.SS2">` 锚点；正文里的 `[12](#bib.bib12)` 这类链接指向文内锚点（参考文献、章节、图、表、公式）。
- 公式为 `$$...$$` 块（编号转 `\tag{n}`），表格为 Markdown 表格（合并单元格已按网格展开），代码 / 算法为围栏代码块，图片为 `![图注](images/...)`。

## 定位与引用方式

arXiv 路径**没有页码**。claim 回指改用：

- 图号 / 表号 / 公式编号（Fig. 2、Table 3、Eq. (4)）
- 章节锚点（如 `#S3`、`#S3.SS2`）

## 图片注意事项

- 下载失败的单张图保留远程 URL 并记 warning，不中断转换；写正文前先核对 `images/` 里的图是否齐全。
- 有些论文的图是 HTML 内嵌 SVG（`<svg class="ltx_picture">`，多为 TikZ 矢量图），**没有外部图片文件可下载**。此时脚本不生成 `images/` 并给出 warning，`source.md` 里只保留 SVG 的文字内容（坐标轴标签、框内文字会散落成段落）。这种情况：
  - 在 `evidence_map.md` 里记录“图仅有内嵌 SVG，图形信息不可用”
  - 正文用 SVG 文字段落还原图的内容结构，并明确说明图缺失的局限
  - 正文必须展示原图时，改走 PDF 分支（arXiv 页面可下载 PDF）用整页渲染裁图

## 何时仍选 PDF 分支

- 需要精确页码引用
- 论文图片是内嵌 SVG 且正文必须展示原图
- arXiv 没有该论文的 HTML 版本（脚本会自动回退 ar5iv；ar5iv 也没有时会失败）
