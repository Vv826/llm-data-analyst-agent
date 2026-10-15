"""接口层测试：用 FastAPI TestClient 直接请求接口（不调用大模型）。

⚠️ 会往 uploads/ 里写一个测试用文件（该目录已 gitignore）。
"""
from fastapi.testclient import TestClient

import main
import pytest

client = TestClient(main.app)


def test_hello():
    r = client.get("/")
    assert r.status_code == 200


def test_metrics_shape():
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.json()
    assert "calls" in body
    assert "total_tokens" in body

@pytest.mark.requires_kb
def test_rag_documents_lists_sources():
    r = client.get("/rag/documents")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["documents"], list)
    if body["documents"]:
        first = body["documents"][0]
        assert "source" in first and "chunks" in first


def test_upload_csv_returns_quality_report():
    csv = "城市,销售额\n北京,100\n上海,\n".encode("utf-8")
    r = client.post("/upload", files={"file": ("pytest_upload.csv", csv)})
    body = r.json()
    assert body["success"] is True
    assert body["rows"] == 2
    assert body["columns"] == 2
    assert body["missing_rate"]["销售额"] == 50.0     # 2 行里缺 1 行


def test_upload_rejects_empty_file():
    r = client.post("/upload", files={"file": ("pytest_empty.csv", b"")})
    assert r.json()["success"] is False


def test_multi_agent_rejects_missing_file():
    r = client.post("/multi/analyze", json={"question": "测试", "filename": "不存在的文件.csv"})
    body = r.json()
    assert body["success"] is False
    assert "不存在" in body["error"]


# ---------- AI 代码生成：受限执行（不调用大模型） ----------

def test_code_run_executes_safe_code():
    csv = "城市,销售额\n北京,100\n上海,200\n北京,300\n".encode("utf-8")
    client.post("/upload", files={"file": ("pytest_code.csv", csv)})
    r = client.post("/code/run", json={
        "filename": "pytest_code.csv",
        "code": "print(df['销售额'].sum())",
    })
    body = r.json()
    assert body["success"] is True
    assert "600" in body["output"]


def test_code_run_rejects_dangerous_code():
    """接口层必须再次校验 —— 不信任前端传来的代码（纵深防御）"""
    csv = "a\n1\n".encode("utf-8")
    client.post("/upload", files={"file": ("pytest_code2.csv", csv)})
    r = client.post("/code/run", json={"filename": "pytest_code2.csv", "code": "import os"})
    body = r.json()
    assert body["success"] is False
    assert "安全检查" in body["error"]


def test_code_run_rejects_missing_file():
    r = client.post("/code/run", json={"filename": "不存在的表.csv", "code": "print(1)"})
    assert r.json()["success"] is False