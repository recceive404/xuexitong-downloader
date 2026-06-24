# 学习通课件下载器

一键下载超星学习通课程的全部课件（章节+资料区），支持 AI 问答。

> ⚠️ 仅限个人学习使用，请勿分发课件或绕过付费。

## ✨ 功能

- **自动下载** — 模拟浏览器自动遍历章节和资料区，包括子文件夹
- **多格式支持** — PDF、PPT、Word、Excel、MP4 视频、HTML 网页
- **OCR 识别** — 图片类课件自动文字识别，生成可搜索的 PDF
- **增量更新** — 已下载的文件自动跳过，支持断点续传
- **RAG 知识库** — 本地向量数据库 + DeepSeek AI 问答（可选）

## 📋 前提条件

- **Python 3.10+**（[下载](https://www.python.org/downloads/)）
- **Git**（[下载](https://git-scm.com/downloads)，或直接下载 ZIP）
- 一个**学习通账号**

## 🚀 三步快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/recceive404/xuexitong-downloader.git
cd xuexitong-downloader

# 2. 一键安装
setup.bat        # Windows
# 或
bash setup.sh    # Mac / Linux

# 3. 开始使用
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Mac / Linux

python main.py login             # 扫码登录
python main.py courses           # 查看课程列表
python main.py download "课程名"  # 下载课件
```

下载的课件在 `courses/课程名/` 目录下。

## 📖 命令说明

| 命令 | 说明 |
|------|------|
| `python main.py login` | 打开浏览器，扫码登录学习通（Cookie 保存 7-30 天） |
| `python main.py courses` | 列出所有课程 |
| `python main.py download "课程名"` | 下载课程的全部课件（章节 + 资料区） |
| `python main.py build-rag` | 将课件消化到本地知识库（需要 API Key） |
| `python main.py ask` | 交互问答模式 |
| `python main.py ask "问题"` | 单次提问 |

### 模糊匹配

课程名支持模糊匹配，只需输入关键词：

```bash
python main.py download "植物保护学"
python main.py download "园艺"
```

## 🤖 AI 问答（可选）

如果只想下载课件，跳过这一步即可。

1. 注册 [DeepSeek](https://platform.deepseek.com)，获取 API Key
2. 复制配置模板：`cp .env.example .env`
3. 编辑 `.env`，填入 API Key：
   ```
   ANTHROPIC_AUTH_TOKEN=sk-xxxxxxxxxxxxxxxx
   ```
4. 构建知识库并提问：
   ```bash
   python main.py build-rag
   python main.py ask "病虫害防治有哪些方法"
   ```

## 📁 项目结构

```
xuexitong-downloader/
├── main.py              # CLI 入口
├── auth.py              # 登录 + Cookie 持久化
├── crawler.py           # 课程列表 + 章节遍历 + 资料区爬取
├── downloader.py        # 文件下载 + OCR + PDF 合成
├── rag_engine.py        # RAG 知识库 + AI 问答
├── requirements.txt     # 依赖清单
├── setup.bat / setup.sh # 一键安装脚本
├── .env.example         # API Key 配置模板
├── courses/             # 下载的课件（按课程分文件夹）
│   └── 园艺植物栽培学/
│       ├── 课件/               # 资料区子文件夹
│       ├── 学习视频/
│       └── 学习资料/
├── chroma_db/           # 向量数据库
└── cookies.json         # 登录态（自动生成，勿分享）
```

## 🔧 技术栈

| 组件 | 技术 |
|------|------|
| 浏览器自动化 | Playwright |
| OCR 文字识别 | EasyOCR（中文 + 英文） |
| 向量化 | sentence-transformers |
| 向量数据库 | ChromaDB |
| LLM | DeepSeek V4 |
| PDF/PPT 解析 | PyMuPDF / python-pptx |

## ❓ 常见问题

### Cookie 过期了怎么办？
重新运行 `python main.py login` 扫码即可。

### 下载速度慢？
学习通服务器限速，大文件（视频）可能较慢。已下载的文件会自动跳过，可以多次运行。

### OCR 模型下载慢？
国内用户已默认使用 HuggingFace 镜像 (`hf-mirror.com`)，首次加载模型约需 100MB。

### 章节区没有课件？
部分课程课件放在「资料」区而非「章节」区，程序会自动扫描两个区域。

### 资料区文件夹没下载？
已支持资料区子文件夹遍历（v1.1+）。如果你用的是旧版，请 `git pull` 更新。

### 提示 "未找到资料 iframe"？
学习通页面结构可能已更新，请提 Issue 附上截图和课程名。

### "我没有 DeepSeek API Key"
不影响课件下载！API Key 仅用于 AI 问答。跳过 `build-rag` 和 `ask` 命令即可。

## 📄 License

MIT — 仅供学习研究使用
