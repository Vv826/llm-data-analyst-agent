"""会话记忆与知识库元数据工具的测试（不调用大模型）。"""
import os
import sqlite3

import pytest
import main


class TestPersistentMemory:
    def test_checkpointer_is_sqlite_backed(self):
        """必须是 SQLite 持久化版 —— 内存版重启就丢"""
        assert type(main._rag_checkpointer).__name__ == "SqliteSaver"

    def test_chat_db_file_exists(self):
        assert os.path.exists(main.CHAT_DB_PATH)

    def test_chat_db_has_checkpoint_tables(self):
        conn = sqlite3.connect(main.CHAT_DB_PATH)
        try:
            names = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        assert {"checkpoints", "writes"} <= names

    def test_fresh_thread_has_no_history(self):
        """全新的 thread_id 不该有历史 —— 会话隔离的底层保证"""
        cfg = {"configurable": {"thread_id": "unit-test-never-used-xyz"}}
        assert main._rag_checkpointer.get_tuple(cfg) is None

    def test_db_can_be_reopened(self):
        """模拟服务重启：用同一个库文件重新构造 saver 不应报错"""
        from langgraph.checkpoint.sqlite import SqliteSaver
        conn = sqlite3.connect(main.CHAT_DB_PATH, check_same_thread=False)
        try:
            saver = SqliteSaver(conn)
            saver.setup()          # 幂等，重复调用不应报错
            assert saver.get_tuple({"configurable": {"thread_id": "unit-reopen"}}) is None
        finally:
            conn.close()


class TestKnowledgeBaseMetadataTool:
    """对应开发笔记里的那个 bug：模型曾把 6 份文档说成 2 份"""

    @pytest.mark.requires_kb
    def test_lists_every_document(self):
        listed = main.build_list_documents_tool().invoke({})
        for d in main.rag_documents()["documents"]:
            assert d["source"] in listed

    @pytest.mark.requires_kb
    def test_reports_correct_total(self):
        listed = main.build_list_documents_tool().invoke({})
        total = len(main.rag_documents()["documents"])
        assert f"{total} 份文档" in listed