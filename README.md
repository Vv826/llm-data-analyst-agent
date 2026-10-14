# AI 智能应用平台

基于大模型的一站式 AI 应用平台，包含「自然语言数据分析智能体」与「RAG 知识库问答」两大模块。
后端 FastAPI，前端 React，智能体编排基于 LangChain / LangGraph。

## 界面预览

**数据分析（Agent 模式）**

![数据分析](docs/screenshot-1-data.png)

**知识库问答（RAG）**

![知识库问答](docs/screenshot-2-rag.png)

## 核心功能

### 模块一：AI 自助数据分析（Agent 模式）
- 支持 CSV / Excel(.xlsx) 上传，自动生成数据质量报告（行列数、字段列表、缺失率）
- 自然语言提问，智能体自主规划步骤并调用工具完成分析
- 内置 5 个工具：数据概览、统计计算、分组聚合、条件过滤、排序
- 自动生成可视化图表（柱状图 / 折线图 / 饼图）
- 完整展示执行链路：每步的推理摘要、调用的工具、传入的参数

### 模块二：RAG 知识库问答
- 支持 PDF / Word(.docx) / TXT / MD / CSV 上传，自动切片写入本地向量库
- **检索器工具化**：Agent 自主决定何时检索、用什么查询检索
- **检索范围可控**：可限定只在某一份文档内检索，避免多文档之间"串味"
- **多轮对话**：基于 LangGraph checkpointer，按 session_id 记忆上下文
- 回答附带检索到的原文片段，支持溯源

## 技术栈

| 层次 | 技术选型 |
| --- | --- |
| 后端框架 | FastAPI 0.142 + Uvicorn |
| 智能体编排 | LangChain 1.4 + LangGraph 1.2（`create_agent` + 原生 tool calling） |
| 大模型 | 字节豆包（火山方舟，OpenAI 兼容接口），通过 `langchain-openai` 的 `ChatOpenAI` 接入 |
| 向量库 | ChromaDB 1.5（本地持久化），`langchain-chroma` 集成 |
| 嵌入模型 | ONNX 版 all-MiniLM-L6-v2（384 维，本地推理，无需外部 API） |
| 数据处理 | pandas 3.0 + numpy + openpyxl + chardet（自动探测 CSV 编码） |
| 文档解析 | pypdf（PDF）、python-docx（Word） |
| 前端 | React 19 + Vite 8 + Ant Design 6 + ECharts 6（黑白灰单色主题，CSS 变量驱动） |

## 架构

```
数据分析链路
  浏览器
    └─ POST /upload     pandas 解析 + chardet 探测编码 → 数据质量报告
    └─ POST /analyze    create_agent（LangGraph）循环：
                          推理摘要 → 调用工具 → 观察结果 → 再推理
                          （原生 tool calling，非手写 JSON 协议）
                        工具：get_overview / get_stats / group_agg / filter / sort
        返回            final_answer + chart + tool_history + result

RAG 知识库链路
  浏览器
    └─ POST /rag/upload  文档解析 → RecursiveCharacterTextSplitter 切片
                         → ONNX 本地嵌入 → Chroma upsert（ID 含内容摘要，重传幂等）
    └─ POST /rag/chat    create_agent + 检索工具 + checkpointer(thread_id = session_id)
                         → 向量召回 top10 → LLM 重排取 top3 → 基于原文生成回答
        返回            answer + related_docs
```

## 技术亮点

1. **原生 tool calling，而非手写协议**：工具用 `@tool` 装饰器定义，参数 JSON Schema 由**函数签名与 docstring 自动生成**，无需在提示词里手写参数说明，改代码不会出现"文档漂移"。
2. **参数隔离**：`df` 等运行时对象通过闭包注入，**对模型完全不可见**，模型只能填它该填的参数（线程安全，无全局状态）。
3. **确定性图表推导**：图表字段从工具调用参数推导（`group_agg` 的分组列/聚合列），而不是让模型猜 x/y 字段 —— 修掉了"图与结论对不上"的问题。
4. **服务端多轮记忆**：`InMemorySaver` checkpointer + `thread_id`，会话隔离，不依赖前端传历史。
5. **检索范围可限定**：`/rag/chat` 支持按文档过滤检索（Chroma metadata filter）。在嵌入模型对中文区分度有限的情况下，这把"问 A 文档却答成 B 文档"从概率问题变成了确定性问题。
6. **零重依赖的本地嵌入**：用自定义 `Embeddings` 包装 Chroma 自带的 ONNX 函数，复用已下载的模型（86MB），避免引入 `sentence-transformers + torch`（约 2GB）。
7. **工程健壮性**：分块落盘 + 上传大小限制、DataFrame 缓存（按 mtime 校验）、路径穿越防御、NaN/Inf 归一化为 `null`、大模型调用超时与自动重试、docx 解析重名防御。
8. **两阶段检索（向量宽召回 + LLM 重排）**：先召回 top-10，再由大模型重排取 top-3。关键是提示词设计 —— 要求模型"**给所有候选排序**"而不是"**筛选出前 3 段**"，后者会让模型丢掉相关片段；并对排序任务**关闭思考链**，单次重排从 94.8 秒降到 2.1 秒，答案完全一致。
9. **大模型调用可观测性**：用 LangChain callback 捕获每一次底层模型调用的耗时与 token，聚合出调用次数 / 总 token / 平均与 P95 延迟 / 估算成本，经 `/metrics` 暴露并在前端展示，按 `analyze` / `rag` / `rerank` 分类统计；重排的回退分支也会上报失败指标，避免"静默降级"。

## 效果评测

RAG 检索质量用 `eval/run_eval.py` 在 14 条人工标注问答上评测（知识库 23 个片段、召回 top-10）：

| 阶段 | Hit@1 | Hit@3 | MRR | 单次重排耗时 |
| --- | --- | --- | --- | --- |
| 纯向量检索（基线） | 28.6% | 92.9% | 0.571 | — |
| + LLM 重排（初版） | 92.9% | 100% | 0.952 | 94.8s |
| **+ 关闭思考链 + 全量排序（最终）** | **100.0%** | **100.0%** | **1.000** | **2.1s** |

> **Hit@1** = 正确文档排在第一位的比例；**Hit@k** = 正确文档出现在前 k 条的比例；**MRR** = 平均倒数排名（排第 1 得 1 分，排第 3 得 0.33 分）。

评测还揭示了两点：召回数从 5 提到 10 后 **Recall@10 达到 100%**（Recall@5 只有 85.7%）；关闭思考链后重排从 94.8s 降到 2.5s，但"筛选前 3 段"的提示词会让 Hit@1 掉到 64.3% —— 说明**瓶颈在任务设计，不在模型的推理能力**。

## 快速开始

### 环境要求
- Python 3.10+（开发环境 3.12）
- Node.js 18+
- 豆包大模型 API Key（火山方舟）

### 后端

```bash
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt

# 配置密钥：复制模板并填入自己的 Key
copy .env.example .env

# 启动（必须在项目根目录）
venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

- 接口文档：http://127.0.0.1:8000/docs
- ⚠️ 必须在**项目根目录**启动：`uploads/`、`chroma_db/`、`models/`、`.env` 都按当前工作目录解析
- ⚠️ 首次使用知识库问答时，会自动下载约 80MB 的嵌入模型到 `models/`（已 gitignore）

### 前端

```bash
cd frontend
npm install
npm run dev
```

页面地址：http://localhost:5173

## 配置项

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ARK_API_KEY` | 无（必填） | 火山方舟 API Key |
| `ARK_MODEL` | 内置默认值 | 推理接入点 ID |
| `MAX_UPLOAD_MB` | `200` | 单文件上传大小上限 |
| `DF_CACHE_SIZE` | `3` | DataFrame 内存缓存条数 |

## 项目结构

```
ai-data-project/
├── main.py                  # 后端全部接口（上传 / Agent 分析 / RAG 问答）
├── observability.py         # 大模型调用指标（token / 延迟 / 成本）
├── eval/                    # 检索评测：qa_set.json 评测集 + run_eval.py
├── requirements.txt
├── .env.example             # 配置模板（复制为 .env 后填密钥）
├── README.md
├── docs/                    # README 截图
├── models/                  # 本地嵌入模型缓存（gitignore，约 86MB）
├── chroma_db/               # 向量库持久化目录（gitignore）
├── uploads/                 # 上传的表格文件（gitignore）
└── frontend/
    ├── src/
    │   ├── App.jsx          # 数据分析页 + 模块切换
    │   ├── RagPanel.jsx     # 知识库问答页
    │   ├── App.css
    │   └── index.css        # 设计变量与全局样式
    └── package.json
```

## 已知限制

- **嵌入模型是英文模型**（all-MiniLM-L6-v2），对中文的语义区分度很低。实测：不同主题的中文句向量余弦相似度全部挤在 **0.47 ~ 0.60**（连"今天天气怎么样"与"就业人口"都有 0.47），而同内容用英文时分布为 **0.003 ~ 0.26**。结果是**跨文档检索结果不稳定**。当前通过"限定检索范围"规避；要根本解决需换成中文嵌入模型（如 `bge-small-zh-v1.5`，或火山方舟的 embedding 接入点）并重建向量库。
- 会话记忆存于进程内存，**重启服务后丢失**（可换 `SqliteSaver` 持久化）。
- 单次 RAG 问答耗时约 30 秒：Agent 模式需要两次模型调用（决定检索 + 生成答案），且该模型每轮输出较多推理 token；重排本身只占约 2 秒。若追求低延迟可改为固定"检索 → 生成"链。
- 不支持老式 `.xls`（需 `xlrd`），请用 Excel 另存为 `.xlsx`。

## 开发笔记

迁移到 LangChain 过程中踩到并记录的坑，供参考：

1. **`chromadb-client` 与 `chromadb` 共用同一个 `chromadb/` 命名空间**。装了前者会写入 `chromadb/is_thin_client.py`，使完整版误判为瘦客户端，`PersistentClient` 直接抛 `http-only client mode`，**整个后端在 import 阶段就崩**。且不能用 `pip uninstall chromadb-client` 修复（它会连带删除完整版也需要的文件），正确做法是删掉那个标记文件。
2. **Python 的 import 是静默覆盖的**：`from docx import Document` 被后写的 `from langchain_core.documents import Document` 覆盖，导致 Word 解析报 `'Document' object has no attribute 'paragraphs'`。此类重名必须显式起别名。
3. **提示词的措辞会直接决定工具调用率**：早期提示词写了"若用户指代之前对话内容则直接结合上下文回答"，结果"这份文件讲了什么"这种模糊指代被判定为"指代对话"而**跳过检索并反问用户**。改为显式定义"‘这份文档’= 知识库里的文档，必须检索、不得反问"后，工具调用率从 1/2 提升到 2/2。
4. **不要用多个进程同时写同一个 Chroma 库**：嵌入式向量库是单写入者模型，跨进程创建/删除集合会让运行中的服务持有失效句柄，表现为检索结果为空。
5. **英文嵌入模型对中文几乎无区分度**：知识库存了 4 份文档后，问"就业人口"却检索到了"电力运营"的片段。用余弦相似度量化后定位到原因——不同主题的中文句向量相似度全挤在 0.47~0.60，而同内容英文的分布是 0.003~0.26，说明该模型对中文的语义区分能力基本失效。**修复分两步**：先加"按文档限定检索范围"，把问题从概率问题变成确定性问题；再考虑替换中文嵌入模型。
6. **"让模型筛选"不如"让模型排序"；而兜底逻辑必须留痕**：LLM 重排初版提示词是"挑出最能回答的前 3 段"，结果模型会**主动丢掉相关片段**（正确文档 100% 在候选池里，Hit@1 却只有 64.3%）；改成"给所有候选排序、由代码取前 3"后达到 100%。另外，重排里写了 `except Exception: 回退到向量排序` 的兜底，一次参数笔误造成的 `NameError` 被它静默吞掉 —— 表面一切正常，实际早已退化成纯向量检索（Hit@3 从 100% 掉到 57.1%）。**教训：兜底分支必须上报指标或日志，否则它会成为 bug 的隐身衣。**

## License

本项目采用 [MIT License](LICENSE) 授权，Copyright (c) 2026 Miki。
