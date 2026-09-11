# 从 Markdown 导出科研报告

目标是将已完成的文档可靠导出，不开展检索、不改变科学状态。输入为用户指定的 Markdown、输出路径和覆盖字符集的字体；输出为内容对应的 PDF。用户要求改文后再导出时，先完成 Markdown 修订，再转换同一版本。

## 内容与视觉原则

保持正文、顺序、公式、表格及来源链接；不自动添加封面、目录、摘要或改写版。不把内部证据注释印入成稿。视觉层级服务阅读：稳定的正文行距、克制的标题颜色、适度留白、表头重复、标题避免孤立页尾。不要用整章强制分页制造大片空白，也不要把每个结论装进强调框。

默认正文采用“背景与动机—方法—结论—启发”的内容组织。构造例子融入方法并说明场景，不印内部“教学样本链”标签。导出器负责排版，不负责改正文用词。

## 可调用实现

`agent/runtime/documents/export-pdf.cjs` 使用 Markdown-it、KaTeX 和 Chromium，样式保存在同目录 `print.css`。依赖独立于科研运行时的 Python 依赖，版本见 `package.json`。首次使用安装至独立工具缓存；已有依赖直接复用。无需或无权限安装时明确阻碍，不声称已经导出。

```bash
npm install --prefix /tmp/research-document-tools playwright@1.63.0 markdown-it@15.0.1 markdown-it-texmath@1.0.0 katex@0.18.7
/tmp/research-document-tools/node_modules/.bin/playwright install chromium
NODE_PATH=/path/to/tools/node_modules node agent/runtime/documents/export-pdf.cjs \
  /path/to/report.md /path/to/report.pdf --font /path/to/font.ttf
```

使用前通过已安装的 Playwright CLI 安装 Chromium；非标准浏览器可传 `--browser /path/to/chromium`。需要的系统动态库按环境提供。不要把工具缓存、下载的浏览器或字体包放进课题输出目录。中文字体必须实际加载；若浏览器不支持TTC，可用fontTools从所需字形集合导出TTF，不将字体文件改名冒充转换。

公式由KaTeX直接排版，使用其字体和上下标/分式布局；不把公式替换为按正文高度压缩的图片。渲染时检查解析错误、公式序列、字体、图像加载及源文件哈希。失败不覆盖既有PDF；成功才原子替换。脚本禁用原始HTML执行，复杂HTML、特殊TeX宏或扩展Markdown需先核验支持；不默默删去或改写不支持的内容。

## 导出后验收

先核对当前源文件版本、正文起止和引用；检查无残留数学分隔符、解析错误或缺字。渲染含长表格、分式、乘积、上下标、行内数学和中英文混排的实际PDF页面，检查溢出、遮挡、裁切、孤立标题及异常空白。DOM公式一致和字体加载成功不代替PDF视觉核验。

至少保存可复现调用和源文件哈希到现有维护记录，避免重复建立独立交付报告。只生成用户要的PDF；HTML及预览置于临时目录。报告的证据审计与排版验收相互独立，任何一个都不能代替另一个。

## 原文配图与图注

Markdown使用相对图片路径；紧随图片的独立斜体段落作为图注，包含来源链接、版本、物理页码与原图号。当前导出器将这种图片和图注组合成figure，保持同页和原宽高比。读图说明放在图注后，用正常正文解释机制或证据；不把大段论文解读缩进小字号图注。

图片应由原始PDF裁切得到，保留坐标、图例和必要图注。保存来源与裁切记录，逐张查看原页及截取结果；导出后查看实际PDF的缩放可读性和分页。重要文字过小就调整布局或选更合适子图，不裁掉反例或不利结果，不以生成图替代作者证据。
