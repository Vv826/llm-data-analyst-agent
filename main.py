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
import chromadb
from pypdf import PdfReader
from docx import Document
from pydantic import BaseModel
from dotenv import load_dotenv

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


def call_ai(prompt: str):
    """调用豆包聊天大模型"""
    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        raise RuntimeError("未配置 ARK_API_KEY，请在项目根目录的 .env 中填写后重启后端")

    url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": os.getenv("ARK_MODEL", "ep-20261008111305-gwhdt"),
        "messages": [
            {"role": "system", "content": "你是一个数据分析专家，严格按照要求的格式输出。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }

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


TOOLS = {
    "get_overview": tool_get_overview,
    "get_stats": tool_get_stats,
    "group_agg": tool_group_agg,
    "filter": tool_filter,
    "sort": tool_sort
}

# ==================== Agent数据分析接口 ====================
@app.post("/analyze")
def analyze_data(filename: str, question: str):
    system_prompt = """
你是专业的数据分析智能体，你可以通过调用工具来完成用户的数据分析任务。
## 可用工具列表
1. get_overview：获取数据概览，包括行数、列数、列名、数据类型
   参数：无
2. get_stats：获取数值列的统计量（均值、中位数、最大值、最小值、标准差）
   参数：columns（列表，要统计的列名）
3. group_agg：按某列分组，对另一列做聚合计算
   参数：group_col（分组列名）、agg_col（聚合列名）、method（聚合方法，可选mean/sum/count/max/min）
4. filter：按条件过滤数据
   参数：column（列名）、operator（运算符，可选> < == >= <= !=）、value（对比值）
5. sort：按指定列排序
   参数：column（列名）、ascending（布尔值，True升序False降序）
## 执行规则
1. 先思考用户的需求，拆解成分析步骤，再逐步调用工具
2. 每次只调用一个工具，拿到结果后再决定下一步
3. 如果数据结构不明确，先调用get_overview了解数据
4. 不要自己编造数据，所有结论必须基于工具返回的结果
5. 任务完成后，给出最终结论，同时判断最适合的图表类型
## 输出格式要求
严格以JSON格式输出，不要任何其他文字、markdown、解释，必须包含以下字段：
- thought：你的思考过程，分析下一步该做什么
- action：要调用的工具名，任务完成则填"finish"
- action_input：工具参数字典，不需要参数则填{}
- is_finish：布尔值，任务完成填true，否则填false
- final_answer：任务完成时填写最终结论文字
- chart：任务完成时填写，包含type（图表类型bar/line/pie）、x_field、y_field
"""

    file_path = os.path.join(UPLOAD_DIR, safe_filename(filename))
    if not os.path.exists(file_path):
        return {"success": False, "error": "文件不存在，请重新上传"}

    try:
        df = load_dataframe(file_path)
    except Exception as e:
        return {"success": False, "error": f"文件解析失败：{str(e)[:120]}"}

    context = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"数据已加载。用户问题：{question}"}
    ]

    max_steps = 5
    tool_history = []
    last_result_data = None

    for step in range(max_steps):
        prompt = ""
        for msg in context:
            if msg["role"] == "system":
                prompt += msg["content"] + "\n\n"
            elif msg["role"] == "user":
                prompt += f"用户：{msg['content']}\n"
            elif msg["role"] == "assistant":
                prompt += f"你：{msg['content']}\n"
            elif msg["role"] == "tool":
                prompt += f"工具返回结果：\n{msg['content']}\n"

        try:
            ai_response = call_ai(prompt)
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tool_history": tool_history
            }

        ai_response = ai_response.strip()
        if ai_response.startswith("```json"):
            ai_response = ai_response[7:]
        if ai_response.endswith("```"):
            ai_response = ai_response[:-3]
        ai_response = ai_response.strip()

        try:
            action_data = json.loads(ai_response)
        except Exception as e:
            context.append({"role": "assistant", "content": ai_response})
            context.append({"role": "user", "content": f"输出格式错误，请严格按照JSON格式输出。错误信息：{str(e)}"})
            continue

        tool_history.append({
            "step": step + 1,
            "thought": action_data.get("thought", ""),
            "action": action_data.get("action", ""),
            "input": action_data.get("action_input", {})
        })

        if action_data.get("is_finish", False) or action_data.get("action") == "finish":
            return {
                "success": True,
                "final_answer": action_data.get("final_answer", "分析完成"),
                "chart": action_data.get("chart"),
                "result": last_result_data,
                "tool_history": tool_history,
                "steps": step + 1
            }

        tool_name = action_data.get("action")
        tool_input = action_data.get("action_input", {})

        if tool_name not in TOOLS:
            result_text = f"错误：不存在工具 {tool_name}"
            result_data = None
        else:
            try:
                tool_func = TOOLS[tool_name]
                result_text, result_data = tool_func(df, **tool_input)
                if result_data is not None:
                    last_result_data = result_data
            except Exception as e:
                result_text = f"工具执行失败：{str(e)}"
                result_data = None

        context.append({"role": "assistant", "content": ai_response})
        context.append({"role": "tool", "content": result_text})

    return {
        "success": False,
        "error": "超出最大执行步数，任务未完成",
        "tool_history": tool_history
    }

# ==================== RAG知识库模块 ====================
CHROMA_PATH = "./chroma_db"
os.makedirs(CHROMA_PATH, exist_ok=True)

# 向量库初始化失败（例如离线时下不动嵌入模型）不应该拖垮整个应用：
# 数据分析模块要照常可用，所以降级为 None，真正用到 RAG 时再报错
_kb_init_error = ""
try:
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    # 使用Chroma内置本地嵌入函数，无需外部接口
    kb_collection = chroma_client.get_or_create_collection(
        name="knowledge_base",
        embedding_function=chromadb.utils.embedding_functions.DefaultEmbeddingFunction()
    )
except Exception as e:
    chroma_client = None
    kb_collection = None
    _kb_init_error = str(e)


def kb_unavailable():
    return {"success": False, "error": f"知识库初始化失败：{_kb_init_error}"}


def split_text(text, chunk_size=500, chunk_overlap=50):
    """原生文本切片，保留上下文重叠"""
    chunks = []
    text_len = len(text)
    if text_len == 0:
        return chunks
    if chunk_overlap >= chunk_size:
        chunk_overlap = chunk_size // 5

    start = 0
    separators = ["\n\n", "\n", "。", "！", "？", " ", ""]

    while start < text_len:
        end = min(start + chunk_size, text_len)
        for sep in separators:
            pos = text.rfind(sep, start, end)
            if pos != -1 and pos > start:
                end = pos + len(sep)
                break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # 已经切到文末，收工
        if end >= text_len:
            break

        # 保底前进：否则当 end 被夹在同一个分隔符上时 start 会原地打转，
        # 导致 while 永远退不出来（原来的死循环就在这里）
        next_start = end - chunk_overlap
        start = next_start if next_start > start else end

    return chunks


# ==================== RAG接口：文档上传入库 ====================
@app.post("/rag/upload")
def rag_upload(file: UploadFile = File(...)):
    if kb_collection is None:
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
            doc = Document(tmp_path)
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

        # ID 里带上内容摘要：同一文件重传走 upsert 覆盖，内容变了则生成新 ID。
        # 原来用 文件名+序号，同名文件重传 ID 冲突，新内容根本进不去
        digest = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()[:8]
        ids = [f"{file.filename}-{digest}-{i}" for i in range(len(chunks))]
        kb_collection.upsert(
            ids=ids,
            documents=chunks,
            metadatas=[{"source": file.filename} for _ in chunks]
        )

        return {
            "success": True,
            "filename": file.filename,
            "chunks": len(chunks)
        }

    except Exception as e:
        msg = str(e)
        low = msg.lower()
        if (isinstance(e, PermissionError) or ".cache" in msg
                or "timeout" in low or "timed out" in low or "onnx" in low or "download" in low):
            msg += ("（Chroma 首次使用需要把约 80MB 的嵌入模型下载到用户目录 ~/.cache/chroma，"
                    "需保证该目录可写且能联网；网络慢时可能超时，重试一次即可）")
        return {"success": False, "error": msg}
    finally:
        if 'tmp_path' in dir():
            try:
                os.unlink(tmp_path)
            except:
                pass


# ==================== RAG接口：知识库问答 ====================
class RagChatRequest(BaseModel):
    question: str
    history: list = []


@app.post("/rag/chat")
def rag_chat(req: RagChatRequest):
    if kb_collection is None:
        return kb_unavailable()
    try:
        question = req.question

        # 本地向量检索（空库时 n_results 会超过实际条数，先按条数收敛）
        total = kb_collection.count()
        if total == 0:
            return {"success": False, "error": "知识库还是空的，请先上传文档"}

        results = kb_collection.query(
            query_texts=[question],
            n_results=min(3, total)
        )
        related_docs = (results.get("documents") or [[]])[0]

        # 拼接提示词
        context = "\n\n".join(related_docs)

        # 多轮对话：把最近几轮历史带进上下文（原来 history 参数收了但从没用过）
        history_text = ""
        for item in (req.history or [])[-6:]:
            role = "用户" if item.get("role") == "user" else "助手"
            history_text += f"{role}：{item.get('content', '')}\n"

        prompt = "请基于以下参考资料回答用户的问题。如果参考资料里没有答案，就说明无法回答。\n\n"
        prompt += f"参考资料：\n{context}\n\n"
        if history_text:
            prompt += f"历史对话：\n{history_text}\n"
        prompt += f"用户问题：{question}\n"

        # 调用大模型生成回答
        answer = call_ai(prompt)

        return {
            "success": True,
            "answer": answer,
            "related_docs": related_docs
        }
    except Exception as e:
        msg = str(e)
        low = msg.lower()
        if (isinstance(e, PermissionError) or ".cache" in msg
                or "timeout" in low or "timed out" in low or "onnx" in low or "download" in low):
            msg += ("（Chroma 首次使用需要把约 80MB 的嵌入模型下载到用户目录 ~/.cache/chroma，"
                    "需保证该目录可写且能联网；网络慢时可能超时，重试一次即可）")
        return {"success": False, "error": msg}