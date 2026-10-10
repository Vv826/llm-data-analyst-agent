# AI 智能应用平台
基于大模型的一站式 AI 应用平台，包含「自然语言数据分析智能体」和「RAG 知识库问答」两大核心业务模块。

## 核心功能
### 📊 模块一：AI 自助数据分析（Agent 模式）
- 支持 CSV / Excel 表格文件上传，自动解析并生成数据质量报告
- 自然语言提问，智能体自主规划分析步骤、调用工具完成计算
- 自动匹配并生成可视化图表（柱状图 / 折线图 / 饼图）
- 完整展示 Agent 执行链路：思考过程、工具调用、传入参数
- 内置数据概览、统计计算、分组聚合、条件过滤、排序等工具

### 📚 模块二：RAG 知识库问答
- 支持 TXT / MD / PDF / Word 文档上传，自动解析与文本切片
- 基于 Chroma 本地向量数据库，实现语义相似度检索
- 检索增强生成（RAG），严格基于文档内容回答，从根源降低大模型幻觉
- 支持多轮对话，保留上下文记忆
- 回答附带对应参考资料片段，可溯源

## 技术栈
- **后端**：FastAPI + Uvicorn + LangChain + ChromaDB + Pandas
- **前端**：React + Vite + Ant Design + ECharts
- **大模型**：字节跳动豆包大模型（Doubao）

## 项目结构
ai-data-project/
├── main.py                 # 后端主入口，包含 Agent + RAG 全部接口
├── requirements.txt        # Python 依赖清单
├── uploads/                # 上传文件临时目录
├── chroma_db/              # 本地向量数据库存储
├── frontend/               # 前端工程
│   ├── src/
│   │   ├── App.jsx
│   │   ├── App.css
│   │   └── main.jsx
│   └── package.json
├── .gitignore
└── README.md


## 快速开始
### 环境要求
- Python 3.10+
- Node.js 18+
- 豆包大模型 API 密钥

### 后端启动
```bash
# 1. 创建并激活虚拟环境
python -m venv venv
venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务
uvicorn main:app --reload

- 接口地址：[http://127.0.0.1:8000](http://127.0.0.1:8000)
- 在线文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

# 1. 进入前端目录
cd frontend

# 2. 安装依赖
npm install

# 3. 启动开发服务
npm run dev

页面地址：[http://localhost:5173](http://localhost:5173)

## 使用说明

1. **数据分析**：上传表格文件 → 输入自然语言问题 → 查看分析结论、可视化图表、执行过程
2. **知识库问答**：上传文档 → 输入问题 → 获取基于文档的精准回答与参考来源

## 注意事项

- 所有数据均存储在本地，不上传第三方服务器
- 大模型 API 密钥请自行配置，请勿提交到公开仓库
- 单文件大小建议控制在 10MB 以内，后端硬上限 200MB（可用环境变量 `MAX_UPLOAD_MB` 调整）
- 安装依赖时**不要**额外安装 `chromadb-client`：它会破坏 `chromadb` 的持久化客户端，
  导致后端起不来（详见 `requirements.txt` 顶部说明）

#### 4. 上传到 GitHub 的命令
GitHub 新建空仓库后，本地项目根目录打开终端执行：
```bash
git init
git add .
git commit -m "init: AI智能应用平台 数据分析Agent + RAG知识库"
git branch -M main
git remote add origin 你的仓库地址.git
git push -u origin main