# XueXiTong Downloader — 学习通课件下载 + 本地 RAG 问答

一个基于 Python 的学习通课件自动下载工具，支持 OCR 文字识别和本地 RAG 知识库问答。

## ✨ 功能

- **自动下载** — Playwright 模拟浏览器，扫码登录后自动遍历章节下载课件
- **多格式支持** — PDF、PPT、HTML 网页文本，以及图片类课件（CDN 懒加载图片）
- **OCR 识别** — 基于 EasyOCR 对图片课件进行中文文字识别
- **PDF 合成** — 同一章节的图片自动合成 PDF，便于离线阅读
- **RAG 知识库** — ChromaDB + sentence-transformers 构建本地向量数据库
- **AI 问答** — 接入 DeepSeek V4，基于课件内容进行智能问答
- **去重增量** — 已下载的课件自动跳过，知识库增量更新

## 📦 安装

```bash
# 1. 克隆仓库
git clone https://github.com/YOUR_USERNAME/xuexitong-downloader.git
cd xuexitong-downloader

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装 Playwright 浏览器
python -m playwright install chromium
```

## 🚀 快速开始

```bash
# 1. 登录学习通（浏览器弹窗，扫码即可）
python main.py login

# 2. 查看所有课程
python main.py courses

# 3. 下载课件（自动 OCR + 合成 PDF + 去重）
python main.py download "植物保护学"

# 4. 构建 RAG 知识库（首次较慢，后续增量更新）
python main.py build-rag

# 5. 基于课件内容问答
python main.py ask "病虫害防治有哪些方法"
```

## 📁 项目结构

```
xuexitong-downloader/
├── main.py              # CLI 入口（login / courses / download / build-rag / ask）
├── auth.py              # Playwright 模拟登录 + cookie 持久化
├── crawler.py           # 课程列表获取 + 章节遍历 + 网络拦截
├── downloader.py        # 课件下载 + 图片去重 + OCR + PDF 合成
├── rag.py               # RAG 知识库构建 + DeepSeek 问答
├── requirements.txt     # 依赖清单
├── courses/             # 下载的课件（按课程分文件夹）
│   └── 植物保护学/
│       ├── 1.1 新建目录.pdf
│       ├── 1.1 新建目录.txt    # OCR 识别文字
│       └── ...
├── chroma_db/           # ChromaDB 向量数据库
├── cookies.json         # 登录态（自动生成，勿提交）
└── diagnose.py          # 诊断调试脚本
```

## 🔧 技术栈

| 组件 | 技术 |
|------|------|
| 浏览器自动化 | Playwright |
| PDF 解析 | PyMuPDF |
| PPT 解析 | python-pptx |
| OCR 文字识别 | EasyOCR（中文 + 英文） |
| 文本分块 | langchain-text-splitters |
| 向量化 | sentence-transformers（paraphrase-multilingual-MiniLM-L12-v2） |
| 向量数据库 | ChromaDB |
| LLM | DeepSeek V4（Anthropic 兼容 API） |
| CLI | argparse + rich |

## ⚠️ 注意事项

- **仅限个人学习使用**，请勿用于分发课件内容或绕过付费
- 学习通页面结构可能变化，如爬取失败请检查浏览器中实际 DOM 结构
- Cookie 有时效（通常 7-30 天），过期后需重新 `login`
- 图片类课件（未学习章节）需要在浏览器中滚动浏览激活后才能下载
- OCR 模型首次加载需下载约 100MB，请耐心等待
- HuggingFace 国内访问需设置镜像 `HF_ENDPOINT=https://hf-mirror.com`

## 📄 License

MIT — 仅供学习研究使用
