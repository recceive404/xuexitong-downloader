"""
轻量 RAG 模块 — 纯文本搜索 + DeepSeek Chat API

流程：
  ① 扫描 courses/ 下所有 .txt 文件 → 建立文本索引
  ② 用户提问 → 关键词匹配搜索 → 取最相关文本
  ③ 上下文 + 问题 → DeepSeek API → 生成回答

无需 ChromaDB / sentence-transformers / PyTorch / EasyOCR
"""
import os
import json
import re
from pathlib import Path

COURSES_DIR = Path(__file__).parent / "courses"
INDEX_FILE = Path(__file__).parent / "course_index.json"


class RAGEngine:
    """轻量级 RAG 引擎：文件索引 + 关键词搜索 + API 问答"""

    def __init__(self):
        self.documents: dict[str, str] = {}  # {文件名: 全文}
        self._initialized = False

    # ── 知识库构建 ─────────────────────────────────────

    def build_or_update(self):
        """扫描 courses/ 下所有 txt 文件，建立文本索引"""
        if not COURSES_DIR.exists():
            print("[WARN] courses/ 目录不存在，请先下载课件")
            return

        txt_files = sorted(COURSES_DIR.rglob("*.txt"))
        if not txt_files:
            print("[WARN] 未找到任何 txt 课件文件")
            return

        print(f"[SCAN] 找到 {len(txt_files)} 个 txt 文件")

        new_docs = {}
        for fp in txt_files:
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
                if len(text.strip()) > 20:
                    # 用相对路径作为 key
                    key = str(fp.relative_to(COURSES_DIR)).replace("\\", "/")
                    new_docs[key] = text
            except Exception as e:
                print(f"  [WARN] 读取失败 {fp.name}: {e}")

        self.documents = new_docs
        self._initialized = True

        # 保存索引到磁盘（JSON）
        INDEX_FILE.write_text(
            json.dumps(self.documents, ensure_ascii=False), encoding="utf-8"
        )
        total_chars = sum(len(v) for v in self.documents.values())
        print(f"[OK] 索引完成：{len(self.documents)} 个文件，共 {total_chars:,} 字")

    def load(self):
        """加载已有索引"""
        if INDEX_FILE.exists():
            try:
                self.documents = json.loads(
                    INDEX_FILE.read_text(encoding="utf-8")
                )
                self._initialized = True
                total_chars = sum(len(v) for v in self.documents.values())
                print(f"[OK] 已加载索引：{len(self.documents)} 个文件，{total_chars:,} 字")
            except Exception:
                print("[WARN] 索引文件损坏，请重新 build-rag")
        else:
            print("[WARN] 尚未构建索引，请先运行 build-rag")

    # ── 问答 ──────────────────────────────────────────

    def ask(self, question: str) -> str:
        """搜索 + 问答"""
        if not self._initialized or not self.documents:
            return "知识库为空，请先运行 build-rag 消化课件。"

        # 1. 关键词搜索
        ranked = self._search(question)
        if not ranked:
            return "未找到与问题相关的课件内容。"

        # 2. 构建上下文（最多 8000 字）
        context_parts = []
        total_len = 0
        max_context = 8000
        for filename, score in ranked[:10]:
            text = self.documents[filename]
            # 提取包含关键词的段落
            snippet = self._extract_relevant(text, question, max(max_context - total_len, 1000))
            context_parts.append(f"【{filename}】\n{snippet}")
            total_len += len(snippet)
            if total_len >= max_context:
                break

        context = "\n\n---\n\n".join(context_parts)
        print(f"  [SEARCH] 匹配 {len(ranked)} 个文件，上下文 {total_len:,} 字")

        # 3. 调用 API
        return self._generate_answer(question, context)

    def _search(self, question: str) -> list[tuple[str, int]]:
        """关键词匹配搜索，返回 [(文件名, 匹配分数), ...]"""
        # 提取关键词：连续的中文字或英文词
        keywords = []
        # 中文词：Unicode 范围 一-鿿，连续 2 字以上
        cn_words = re.findall(r'[一-鿿]{2,}', question)
        keywords.extend(cn_words)
        # 英文/数字词：连续 3 字符以上
        en_words = re.findall(r'[a-zA-Z0-9]{3,}', question)
        keywords.extend(en_words)
        if not keywords:
            # 退化为单字搜索
            keywords = [question]

        scored = []
        for filename, text in self.documents.items():
            score = 0
            text_lower = text.lower()
            for kw in keywords:
                # 完全匹配 +3，部分匹配 +1
                count = text_lower.count(kw.lower())
                if count > 0:
                    score += 3 + count  # 基础分 + 出现次数
                # 文件名匹配加倍
                if kw.lower() in filename.lower():
                    score += 10
            if score > 0:
                scored.append((filename, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _extract_relevant(self, text: str, question: str, max_len: int) -> str:
        """从文本中提取与问题最相关的片段"""
        if len(text) <= max_len:
            return text

        keywords = re.findall(r'[一-鿿]{2,}|[a-zA-Z]{3,}', question)
        if not keywords:
            return text[:max_len]

        # 找到第一个关键词匹配位置，取前后文
        best_pos = 0
        for kw in keywords:
            pos = text.lower().find(kw.lower())
            if pos >= 0:
                best_pos = pos
                break

        start = max(0, best_pos - max_len // 4)
        end = min(len(text), start + max_len)
        snippet = text[start:end]

        if start > 0:
            snippet = "…" + snippet
        if end < len(text):
            snippet += "…"

        return snippet

    # ── API 调用 ──────────────────────────────────────

    def _get_api_config(self):
        """获取 API 配置（.env → 环境变量 → ~/.claude/settings.json）"""
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).parent / ".env")
        except Exception:
            pass

        api_url = os.environ.get("ANTHROPIC_BASE_URL")
        api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN")
        model = os.environ.get("ANTHROPIC_MODEL")

        if not api_key:
            settings_path = Path.home() / ".claude" / "settings.json"
            if settings_path.exists():
                try:
                    settings = json.loads(settings_path.read_text(encoding="utf-8"))
                    env = settings.get("env", {})
                    api_url = api_url or env.get("ANTHROPIC_BASE_URL")
                    api_key = env.get("ANTHROPIC_AUTH_TOKEN")
                    model = model or env.get("ANTHROPIC_MODEL")
                except Exception:
                    pass

        return (
            api_url or "https://api.deepseek.com/anthropic",
            api_key or "",
            model or "deepseek-v4-pro[1m]"
        )

    def _generate_answer(self, question: str, context: str) -> str:
        """调用 DeepSeek V4"""
        import requests

        api_url, api_key, model = self._get_api_config()

        if not api_key:
            return (
                "⚠️ 未配置 API Key。\n\n"
                "以下是与问题相关的课件片段：\n\n"
                + context[:2000]
            )

        prompt = f"""你是一个学习助手，根据以下课件内容回答用户的问题。

课件内容：
{context}

用户问题：{question}

请基于课件内容回答。如果课件内容不足以回答，请明确说明。
用中文回答，简洁清晰。"""

        try:
            resp = requests.post(
                f"{api_url}/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=60
            )
            if resp.status_code == 200:
                return self._parse_response(resp.text)
            else:
                return (
                    f"[API 错误 {resp.status_code}]\n\n"
                    f"以下是与问题相关的课件片段：\n\n{context[:2000]}"
                )
        except Exception as e:
            return f"[API 异常：{e}]\n\n课件片段：\n{context[:2000]}"

    def _parse_response(self, raw: str) -> str:
        """解析 DeepSeek API 返回（兼容多种格式）"""
        # 尝试 JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            try:
                import ast
                data = ast.literal_eval(raw)
            except Exception:
                return raw[:2000]

        # DeepSeek 列表格式：[{type:'text', text:'...'}, ...]
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("type") == "text":
                    return item.get("text", "")
            return str(data)[:500]

        # OpenAI 格式
        if isinstance(data, dict):
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            # Anthropic 格式
            content = data.get("content", "")
            if isinstance(content, list) and content:
                return content[0].get("text", str(content))
            if isinstance(content, str):
                return content

        return raw[:2000]

    # ── 工具方法 ──────────────────────────────────────

    def list_courses(self) -> list[str]:
        """列出已下载的课程"""
        if not COURSES_DIR.exists():
            return []
        return [
            d.name for d in COURSES_DIR.iterdir()
            if d.is_dir() and any(d.iterdir())
        ]

    def persist(self):
        """显式保存索引"""
        if self.documents:
            INDEX_FILE.write_text(
                json.dumps(self.documents, ensure_ascii=False),
                encoding="utf-8"
            )
            print(f"[SAVE] 索引已保存（{len(self.documents)} 个文件）")
