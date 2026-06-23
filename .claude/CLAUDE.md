# 学习通课件下载器

## 项目信息
- **技术栈**：Python + Playwright + PyMuPDF + python-pptx + ChromaDB + DeepSeek V4
- **创建日期**：2026-06-22
- **当前阶段**：开发中

## 关键决策
- 登录方式：Playwright 模拟浏览器，手动扫码，cookie 持久化
- 课件格式：PDF / PPT / HTML 网页文本
- RAG 向量化：sentence-transformers 本地模型（免费）
- LLM：DeepSeek V4（你已配置的 API）
- 命令行工具，不带界面

## 已知注意事项
- 学习通页面结构可能变化，爬虫选择器可能需要调整
- cookie 有时效（7-30天），过期需重新 login
- PPT 图片中的文字无法提取（需要 OCR，暂未实现）
