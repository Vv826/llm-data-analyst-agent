from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import chardet
import hashlib
import json
import math
import pandas as pd
import os
import requests
import tempfile
from pypdf import PdfReader
from docx import Document as DocxDocument
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
# 把嵌入模型缓存放进项目目录，而不是用户目录 ~/.cache/chroma
# （受限环境下用户目录不可写；放项目里也让整个项目自成一体）
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_chroma import Chroma             
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from langgraph.checkpoint.memory import InMemorySaver
from pathlib import Path
from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ONNXMiniLM_L6_V2.DOWNLOAD_PATH = (
    Path(BASE_DIR) / "models" / "onnx_models" / ONNXMiniLM_L6_V2.MODEL_NAME
)

# ==================== 基础配置 ====================
load_dotenv()
app = FastAPI(title="AI智能应用平台")

# 跨域配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 上传目录与大小限制
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

# DataFrame 缓存：避免每次 /analyze 都重新解析大文件（uploads 里有 178MB 的 CSV）
DF_CACHE_MAX = int(os.getenv("DF_CACHE_SIZE", "3"))
_df_cache = {}  # abspath -> (mtime, size, DataFrame)

# ==================== 基础接口 ====================
@app.get("/")
def hello():
    return {"message": "后端启动成功！"}

# ==================== 文件上传接口（Agent模块用） ====================
@app.post("/upload")
def upload_file(file: UploadFile = File(...)):
    filename = safe_filename(file.filename)
    file_path = os.path.join(UPLOAD_DIR, filename)

    # 分块落盘：大文件不再一次性读进内存，超限立即中止
    size = 0
    too_large = False
    with open(file_path, "wb") as f:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                too_large = True
                break
            f.write(chunk)

    if too_large:
        try:
            os.remove(file_path)
        except OSError:
            pass
        return {"success": False, "error": f"文件超过 {MAX_UPLOAD_MB}MB 上限，请压缩或抽样后再上传"}

    try:
        df = load_dataframe(file_path)
    except Exception as e:
        return {"success": False, "error": f"文件解析失败：{str(e)[:120]}"}

    # 二进制/空文件常常不会抛异常，而是被解析成 0 行的空表，
    # 这种"成功"会让前端显示一份毫无意义的报告，直接拦掉
    if len(df) == 0 or len(df.columns) == 0:
        return {"success": False, "error": "文件里没有解析到任何数据行，请检查文件内容"}

    missing = df.isnull().sum().to_dict()
    missing_rate = (df.isnull().sum() / len(df) * 100).round(2).to_dict()

    return {
        "success": True,
        "filename": filename,
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": df.columns.tolist(),
        "missing_count": to_native(missing),
        "missing_rate": to_native(missing_rate)
    }

# ==================== 工具函数 ====================
def safe_filename(filename):
    """只取文件名，挡住 ../../ 这类路径穿越"""
    return os.path.basename((filename or "").replace("\\", "/")).strip() or "upload.csv"


def read_csv_auto(file_path):
    """自动检测编码并读取CSV文件"""
    with open(file_path, 'rb') as f:
        raw_data = f.read(10000)
        detect_result = chardet.detect(raw_data)
        encoding = detect_result['encoding']

    if encoding and encoding.lower() in ['gb2312', 'gbk', 'cp936']:
        encoding = 'gbk'

    try:
        return pd.read_csv(file_path, encoding=encoding)
    except Exception:
        try:
            return pd.read_csv(file_path, encoding='utf-8')
        except Exception:
            return pd.read_csv(file_path, encoding='gbk')


def read_table_auto(file_path):
    """按后缀分流：CSV 走编码探测，Excel 走 openpyxl"""
    lower = file_path.lower()
    if lower.endswith((".xlsx", ".xlsm")):
        return pd.read_excel(file_path)
    if lower.endswith(".xls"):
        # 老式 .xls 需要额外的 xlrd，这里给出比栈信息更清楚的提示
        try:
            return pd.read_excel(file_path)
        except ImportError:
            raise ValueError("不支持老式 .xls 格式，请用 Excel 另存为 .xlsx 后重试")
    return read_csv_auto(file_path)


def load_dataframe(file_path):
    """带缓存地读取表格：同一文件（mtime + 大小未变）不重复解析"""
    key = os.path.abspath(file_path)
    stat = os.stat(file_path)
    cached = _df_cache.get(key)
    if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
        return cached[2]

    df = read_table_auto(file_path)

    if len(_df_cache) >= DF_CACHE_MAX:
        _df_cache.pop(next(iter(_df_cache)), None)
    _df_cache[key] = (stat.st_mtime, stat.st_size, df)
    return df


def read_text_auto(file_path):
    """按探测到的编码读文本，避免 GBK 文档被 errors='ignore' 吃掉中文"""
    with open(file_path, 'rb') as f:
        raw = f.read()
    encoding = chardet.detect(raw[:10000]).get('encoding') or 'utf-8'
    try:
        return raw.decode(encoding, errors='ignore')
    except (LookupError, UnicodeDecodeError):
        return raw.decode('utf-8', errors='ignore')

# 模块级缓存：ChatModel 只创建一次，复用底层 HTTP 连接池
_llm = None


def get_llm():
    """懒加载大模型客户端（LangChain ChatOpenAI，对接火山方舟 OpenAI 兼容接口）"""
    global _llm
    if _llm is None:
        api_key = os.getenv("ARK_API_KEY")
        if not api_key:
            raise RuntimeError("未配置 ARK_API_KEY，请在项目根目录的 .env 中填写后重启后端")
        _llm = ChatOpenAI(
            model=os.getenv("ARK_MODEL", "ep-20261008111305-gwhdt"),
            api_key=api_key,
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            temperature=0.1,
            timeout=120,
            max_retries=2,
        )
    return _llm


def call_ai(prompt: str):
    """调用豆包聊天大模型"""
    try:
        response = get_llm().invoke(prompt)
    except Exception as e:
        raise RuntimeError(f"调用大模型失败：{str(e)[:200]}")
    return response.content

    try:
        # (连接超时, 读取超时)：上游不响应时不至于把请求永久挂住
        response = requests.post(url, headers=headers, json=data, timeout=(10, 120))
    except requests.exceptions.Timeout:
        raise RuntimeError("调用大模型超时，请稍后重试")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"调用大模型失败：{str(e)[:120]}")

    if response.status_code != 200:
        raise RuntimeError(f"大模型接口返回 {response.status_code}：{response.text[:200]}")

    try:
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise RuntimeError(f"大模型返回格式异常：{response.text[:200]}")


def to_native(data):
    """numpy类型转Python原生类型，解决JSON序列化问题"""
    if isinstance(data, dict):
        return {k: to_native(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [to_native(item) for item in data]
    # NaN / Inf 不是合法 JSON（会害前端 JSON.parse 直接抛错），统一转成 null
    if isinstance(data, float):
        return None if (math.isnan(data) or math.isinf(data)) else data
    if hasattr(data, 'item'):
        try:
            return to_native(data.item())
        except (ValueError, AttributeError):
            return data
    return data

# ==================== Agent工具库 ====================
def tool_get_overview(df):
    info = {
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": df.columns.tolist(),
        "dtypes": df.dtypes.astype(str).to_dict()
    }
    info = to_native(info)
    text = f"数据概览：\n{json.dumps(info, ensure_ascii=False, indent=2)}"
    return text, info


def tool_get_stats(df, columns):
    result = to_native(df[columns].describe().round(2).to_dict())
    text = f"统计结果（列：{columns}）：\n{json.dumps(result, ensure_ascii=False, indent=2)}"
    return text, result


def tool_group_agg(df, group_col, agg_col, method="mean"):
    if method == "mean":
        res = df.groupby(group_col)[agg_col].mean().round(2)
    elif method == "sum":
        res = df.groupby(group_col)[agg_col].sum()
    elif method == "count":
        res = df.groupby(group_col)[agg_col].count()
    elif method == "max":
        res = df.groupby(group_col)[agg_col].max()
    elif method == "min":
        res = df.groupby(group_col)[agg_col].min()
    else:
        return "错误：不支持的聚合方法", None

    data = []
    for k, v in res.items():
        data.append({group_col: k, agg_col: v})
    data = to_native(data)

    text = f"分组聚合结果（按{group_col}统计{agg_col}的{method}）：\n{json.dumps(data, ensure_ascii=False, indent=2)}"
    return text, data


def tool_filter(df, column, operator, value):
    try:
        if operator == ">":
            filtered = df[df[column] > value]
        elif operator == "<":
            filtered = df[df[column] < value]
        elif operator == "==":
            filtered = df[df[column] == value]
        elif operator == ">=":
            filtered = df[df[column] >= value]
        elif operator == "<=":
            filtered = df[df[column] <= value]
        elif operator == "!=":
            filtered = df[df[column] != value]
        else:
            return "错误：不支持的运算符", None

        data = to_native(filtered.head(20).to_dict(orient="records"))
        text = f"过滤结果（{column} {operator} {value}）：共{len(filtered)}条数据\n前20行：\n{filtered.head(20).to_string()}"
        return text, data
    except Exception as e:
        return f"过滤执行失败：{str(e)}", None


def tool_sort(df, column, ascending=True):
    sorted_df = df.sort_values(by=column, ascending=ascending)
    data = to_native(sorted_df.head(20).to_dict(orient="records"))
    text = f"排序结果（按{column}，升序={ascending}）：\n前20行：\n{sorted_df.head(20).to_string()}"
    return text, data

def derive_chart(action, args, data):
    """从最后一次工具调用推导图表配置。

    比"让模型自己猜 x/y 字段"可靠：工具参数里本来就有真实的列名。
    返回 None 时前端会自动隐藏图表卡片。
    """
    if action == "group_agg":
        return {"type": "bar", "x_field": args.get("group_col"), "y_field": args.get("agg_col")}

    if action in ("filter", "sort") and isinstance(data, list) and data:
        keys = list(data[0].keys())
        x_field = keys[0]
        y_field = next(
            (k for k in keys
             if isinstance(data[0].get(k), (int, float)) and not isinstance(data[0].get(k), bool)),
            keys[-1],
        )
        return {"type": "bar", "x_field": x_field, "y_field": y_field}

    # get_overview / get_stats 是元信息和统计量，画图没有意义
    return None

# ==================== Agent数据分析接口 ====================
@app.post("/analyze")
def analyze_data(filename: str, question: str):
    file_path = os.path.join(UPLOAD_DIR, safe_filename(filename))
    if not os.path.exists(file_path):
        return {"success": False, "error": "文件不存在，请重新上传"}

    try:
        df = load_dataframe(file_path)
    except Exception as e:
        return {"success": False, "error": f"文件解析失败：{str(e)[:120]}"}

    captured = {"data": None}
    tools = build_tools(df, captured)

    agent = create_agent(
        model=get_llm(),
        tools=tools,
        system_prompt=(
            "你是专业的数据分析智能体，可以调用工具完成用户的数据分析任务。\n"
            "重要：每次调用工具之前，必须先用一句话（不超过 30 字）说明你接下来打算做什么、为什么，"
            "然后再调用工具。这句话会展示给用户看。\n"
            "1. 列名或数据类型不明确时，先调用 get_overview 了解数据结构\n"
            "2. 所有结论必须基于工具返回的真实结果，不要编造数据\n"
            "3. 任务完成后用中文给出简洁结论\n"
        ),
    )

    try:
        result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    except Exception as e:
        return {"success": False, "error": f"智能体执行失败：{str(e)[:200]}"}

    messages = result["messages"]

    # 把 LangGraph 的消息链路还原成前端需要的 tool_history
    tool_history = []
    last_action, last_input = None, {}
    for msg in messages:
        for call in (getattr(msg, "tool_calls", None) or []):
            tool_history.append({
                "step": len(tool_history) + 1,
                "thought": msg.content or "",
                "action": call["name"],
                "input": call["args"],
            })
            last_action, last_input = call["name"], call["args"]

    # 最后一条"有内容"的 AIMessage 就是最终结论
    final_answer = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            final_answer = msg.content
            break

    return {
        "success": True,
        "final_answer": final_answer,
        "chart": derive_chart(last_action, last_input, captured["data"]),
        "result": captured["data"],
        "tool_history": tool_history,
        "steps": len(tool_history),
    }
def build_tools(df, captured):
    """把工具绑定到当前 df，返回 LangChain Tool 列表。

    - df 不能交给模型，所以用闭包固定住，只暴露模型该填的参数
    - 工具返回值是给模型看的文本；结构化数据走 captured["data"] 旁路带出，供前端画图
    """

    @tool("get_overview", parse_docstring=True)
    def get_overview_tool() -> str:
        """获取数据概览：行数、列数、列名以及每列的数据类型。不需要参数。"""
        text, data = tool_get_overview(df)
        captured["data"] = data
        return text

    @tool("get_stats", parse_docstring=True)
    def get_stats_tool(columns: list[str]) -> str:
        """获取指定数值列的统计量（计数、均值、标准差、最小值、四分位数、最大值）。

        Args:
            columns: 要统计的列名列表，例如 ["2023年"]
        """
        text, data = tool_get_stats(df, columns)
        captured["data"] = data
        return text

    @tool("group_agg", parse_docstring=True)
    def group_agg_tool(group_col: str, agg_col: str, method: str = "mean") -> str:
        """按某列分组，对另一列做聚合计算。

        Args:
            group_col: 分组依据的列名
            agg_col: 被聚合的数值列名
            method: 聚合方法，可选 mean/sum/count/max/min
        """
        text, data = tool_group_agg(df, group_col, agg_col, method)
        captured["data"] = data
        return text

    @tool("filter", parse_docstring=True)
    def filter_tool(column: str, operator: str, value: str) -> str:
        """按条件过滤数据，返回符合条件的记录数与前 20 行。

        Args:
            column: 用于判断的列名
            operator: 运算符，可选 > < == >= <= !=
            value: 对比值
        """
        text, data = tool_filter(df, column, operator, value)
        captured["data"] = data
        return text

    @tool("sort", parse_docstring=True)
    def sort_tool(column: str, ascending: bool = True) -> str:
        """按指定列排序，返回前 20 行。

        Args:
            column: 排序依据的列名
            ascending: True 升序，False 降序
        """
        text, data = tool_sort(df, column, ascending)
        captured["data"] = data
        return text

    return [get_overview_tool, get_stats_tool, group_agg_tool, filter_tool, sort_tool]

CHROMA_PATH = "./chroma_db"
os.makedirs(CHROMA_PATH, exist_ok=True)


class ChromaONNXEmbeddings(Embeddings):
    """把 Chroma 自带的 ONNX 嵌入函数包装成 LangChain 的 Embeddings 接口。

    好处：直接复用已经下载到 models/ 的本地模型，不必再引入
    sentence-transformers + torch 那套重依赖。
    """

    def __init__(self):
        self._ef = ONNXMiniLM_L6_V2()

    def embed_documents(self, texts):
        return [[float(x) for x in v] for v in self._ef(list(texts))]

    def embed_query(self, text):
        return [float(x) for x in self._ef([text])[0]]


_kb_init_error = ""
try:
    vectorstore = Chroma(
        collection_name="knowledge_base",
        embedding_function=ChromaONNXEmbeddings(),
        persist_directory=CHROMA_PATH,
    )
except Exception as e:
    vectorstore = None
    _kb_init_error = str(e)

# 会话记忆：必须放在模块级，跨请求共享，否则每次请求都"失忆"
_rag_checkpointer = InMemorySaver()


def kb_unavailable():
    return {"success": False, "error": f"知识库初始化失败：{_kb_init_error}"}


def split_text(text, chunk_size=500, chunk_overlap=50):
    """文本切片（LangChain RecursiveCharacterTextSplitter 实现）"""
    if not text:
        return []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", "。", "！", "？", " ", ""],
    )
    return splitter.split_text(text)


# ==================== RAG接口：文档上传入库 ====================
@app.post("/rag/upload")
def rag_upload(file: UploadFile = File(...)):
    if vectorstore is None:
        return kb_unavailable()
    try:
        suffix = os.path.splitext(file.filename)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file.file.read())
            tmp_path = tmp.name

        # 解析文档文本
        text = ""
        if suffix == ".pdf":
            reader = PdfReader(tmp_path)
            for page in reader.pages:
                text += page.extract_text() + "\n\n"
        elif suffix == ".docx":
            doc = DocxDocument(tmp_path)      
            for para in doc.paragraphs:
                text += para.text + "\n"
        elif suffix in [".txt", ".md", ".csv"]:
            text = read_text_auto(tmp_path)
        else:
            return {"success": False, "error": f"不支持的文件格式：{suffix}"}

        # 切片并存库
        chunks = split_text(text)
        if not chunks:
            return {"success": False, "error": "文档中没有提取到可用文本（扫描版 PDF 常见）"}

        digest = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()[:8]
        ids = [f"{file.filename}-{digest}-{i}" for i in range(len(chunks))]
        vectorstore.add_documents(
            documents=[
                Document(page_content=c, metadata={"source": file.filename})
                for c in chunks
            ],
            ids=ids,
        )

        return {
            "success": True,
            "filename": file.filename,
            "chunks": len(chunks)
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if 'tmp_path' in dir():
            try:
                os.unlink(tmp_path)
            except:
                pass


# ==================== RAG接口：列出知识库文档 ====================
@app.get("/rag/documents")
def rag_documents():
    """列出知识库里已有的文档（按来源聚合片段数）"""
    if vectorstore is None:
        return kb_unavailable()
    try:
        data = vectorstore.get()
        counts = {}
        for meta in data.get("metadatas") or []:
            src = (meta or {}).get("source")
            if src:
                counts[src] = counts.get(src, 0) + 1
        docs = [{"source": s, "chunks": n} for s, n in sorted(counts.items())]
        return {
            "success": True,
            "documents": docs,
            "total_chunks": sum(counts.values()),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


class RagChatRequest(BaseModel):
    question: str
    session_id: str = "default"
    # 限定只在某个文档里检索；None 表示在整个知识库检索
    source: str | None = None


_rag_system_prompt = (
    "你是知识库问答助手。\n"
    "1. 知识库里已经上传了文档。用户问“这份文档/这份文件/这个项目讲了什么”时，"
    "“这份/这个”指的就是知识库里的文档（若系统限定了检索范围，就是那份文档），"
    "必须直接调用 search_knowledge_base 检索，然后基于检索结果回答；不要反问“是哪份文档”。\n"
    "2. 只要问题涉及知识库内容，都先检索，再严格基于检索结果回答，不要编造。\n"
    "3. 检索到的资料必须与问题主题相关才可使用。如果检索结果与用户问的主题**无关**"
    "（例如问的是 A 主题、检索到的却是 B 主题的资料），直接回答“知识库中没有与 XXX 相关的内容”，"
    "**绝不能用无关资料拼凑答案**。\n"
    "4. 只有用户明确询问对话本身（如“我刚才问的是什么”）时才不检索，直接结合上下文回答。\n"
    "5. 回答用中文。\n"
)


@app.post("/rag/chat")
def rag_chat(req: RagChatRequest):
    if vectorstore is None:
        return kb_unavailable()
    try:
        # 知识库为空时先给友好提示，省掉两次模型调用
        if vectorstore._collection.count() == 0:
            return {"success": False, "error": "知识库还是空的，请先上传文档"}

        # 按需限定检索范围：指定文档时只在该文档的片段里检索，
        # 从根本上避免"问 A 文档却答成 B 文档"
        search_kwargs = {"k": 3}
        if req.source:
            search_kwargs["filter"] = {"source": req.source}
        retriever = vectorstore.as_retriever(search_kwargs=search_kwargs)

        collected = {"docs": []}

        @tool("search_knowledge_base", parse_docstring=True)
        def search_knowledge_base(query: str) -> str:
            """在本地知识库中检索与问题最相关的资料片段。

            Args:
                query: 检索用的自然语言问题
            """
            docs = retriever.invoke(query)
            collected["docs"] = [d.page_content for d in docs]
            if not docs:
                return "知识库中没有检索到相关内容。"
            return "\n\n".join(d.page_content for d in docs)

        agent = create_agent(
            model=get_llm(),
            tools=[search_knowledge_base],
            checkpointer=_rag_checkpointer,
            system_prompt=_rag_system_prompt,
        )

        result = agent.invoke(
            {"messages": [{"role": "user", "content": req.question}]},
            # thread_id 就是会话 ID：同一个 session_id 的多次提问共享上下文
            config={"configurable": {"thread_id": req.session_id}},
        )

        return {
            "success": True,
            "answer": result["messages"][-1].content,
            "related_docs": collected["docs"],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}