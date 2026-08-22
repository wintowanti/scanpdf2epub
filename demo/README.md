# Demo: 合成扫描 PDF

`make_demo_pdf.py` 生成**合成扫描版 PDF**——真实印刷的中文文字被烧进带扫描噪声的图片页面
(轻微歪斜 + 感光噪声 + 斑点),行为和复印书页完全一致,用来端到端测试整条管线,不需要任何有版权的书。

内容为原创示例散文,可以放心提交到仓库。

```bash
# 生成 6 页示例
python demo/make_demo_pdf.py

# 更多页 / 更高 DPI / 固定随机种子
python demo/make_demo_pdf.py --pages 12 --dpi 200 --seed 7
```

生成结果默认写到 `demo/output/`(已 gitignore,不会进仓库)。然后跑管线:

```bash
# 先转 1 页试水
python main.py demo/output/demo_6p.pdf --skip-epub --max-pages 1

# 全书 + EPUB
python main.py demo/output/demo_6p.pdf
```

> 仓库内也附带一个小样例 `demo/demo_4p.pdf`,克隆后可直接 `python main.py demo/demo_4p.pdf` 体验,
> 不用先装字体生成。
