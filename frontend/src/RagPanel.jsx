import { useEffect, useRef, useState } from 'react'
import { Upload, Button, Input, Card, Tag, Empty, Spin, message } from 'antd'
import {
  InboxOutlined,
  SendOutlined,
  FileTextOutlined,
  RobotOutlined,
  UserOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import axios from 'axios'

const { TextArea } = Input

// 与数据分析页共用同一个后端
const API = 'http://127.0.0.1:8000'

export default function RagPanel() {
  const [doc, setDoc] = useState(null)            // { filename, chunks }
  const [uploading, setUploading] = useState(false)
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [messages, setMessages] = useState([])    // { role, content, docs }
  const [sessionId, setSessionId] = useState(() => `s-${Date.now()}`)
  const listRef = useRef(null)

  // 有新消息时自动滚到底部
  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, asking])

  // 上传文档入库
  const handleUpload = async (file) => {
    setUploading(true)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await axios.post(`${API}/rag/upload`, formData)
      if (res.data?.success === false) {
        message.error('上传失败：' + (res.data.error || '文件无法解析'))
        return false
      }
      setDoc({ filename: res.data.filename, chunks: res.data.chunks })
      message.success(`已入库：${res.data.chunks} 个片段`)
    } catch (err) {
      message.error('上传失败：' + (err?.response?.data?.error || err?.message || '请确认后端已启动'))
    } finally {
      setUploading(false)
    }
    return false
  }

  // 提问（带 session_id，服务端靠它记住上下文）
  const handleAsk = async () => {
    const q = question.trim()
    if (!q) {
      message.warning('请先输入问题')
      return
    }
    if (asking) return

    setMessages((prev) => [...prev, { role: 'user', content: q }])
    setQuestion('')
    setAsking(true)
    try {
      const res = await axios.post(`${API}/rag/chat`, { question: q, session_id: sessionId })
      if (res.data?.success === false) {
        setMessages((prev) => [...prev, { role: 'assistant', content: '出错了：' + res.data.error, docs: [] }])
      } else {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: res.data.answer, docs: res.data.related_docs || [] },
        ])
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: '请求失败：' + (err?.response?.data?.error || err?.message || '请确认后端已启动'),
          docs: [],
        },
      ])
    } finally {
      setAsking(false)
    }
  }

  // 开启新对话：清空消息 + 换一个 session_id（验证会话隔离）
  const handleNewChat = () => {
    setMessages([])
    setSessionId(`s-${Date.now()}`)
    message.success('已开启新对话')
  }

  return (
    <div className="layout">
      {/* ============ 左：文档上传 ============ */}
      <div className="col">
        <Card
          className="panel rise"
          title={<span className="panel-title"><FileTextOutlined />知识库文档</span>}
          extra={<Tag color="geekblue" style={{ margin: 0 }}>PDF · Word · TXT</Tag>}
        >
          <div className="upload-zone">
            <Upload.Dragger
              beforeUpload={handleUpload}
              accept=".pdf,.docx,.txt,.md,.csv"
              maxCount={1}
              disabled={uploading}
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">{uploading ? '正在解析入库…' : '点击或拖拽文档到此处上传'}</p>
              <p className="ant-upload-hint">支持 PDF / Word(.docx) / TXT / MD / CSV</p>
            </Upload.Dragger>
          </div>

          {doc && (
            <div className="doc-info">
              <FileTextOutlined style={{ color: '#6366f1' }} />
              <span>{doc.filename}</span>
              <Tag color="green" style={{ marginLeft: 'auto', marginRight: 0 }}>
                {doc.chunks} 个片段
              </Tag>
            </div>
          )}
        </Card>

        <Card className="panel rise" title={<span className="panel-title"><RobotOutlined />使用提示</span>}>
          <p className="rag-tip">1. 先上传一份文档，它会自动切片并写入本地向量库。</p>
          <p className="rag-tip">2. 然后提问，智能体会先检索知识库，再基于检索结果回答。</p>
          <p className="rag-tip">3. 支持追问（比如"刚才那条的细节呢"），服务端会记住上下文。</p>
          <p className="rag-tip">4. 点"新对话"可清空上下文，验证会话隔离。</p>
        </Card>
      </div>

      {/* ============ 右：对话 ============ */}
      <div className="col">
        <Card
          className="panel rise"
          title={<span className="panel-title"><RobotOutlined />知识库问答</span>}
          extra={
            <Button
              size="small"
              type="text"
              icon={<ReloadOutlined />}
              onClick={handleNewChat}
              disabled={messages.length === 0}
            >
              新对话
            </Button>
          }
        >
          <div className="chat-list" ref={listRef}>
            {messages.length === 0 && !asking && (
              <div className="chat-empty">
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    <span style={{ color: '#94a3b8', fontSize: 13 }}>
                      上传文档后，在这里向知识库提问
                    </span>
                  }
                />
              </div>
            )}

            {messages.map((msg, index) => (
              <div key={index} className={`chat-row ${msg.role === 'user' ? 'is-user' : 'is-ai'}`}>
                <span className={`chat-avatar ${msg.role === 'user' ? 'is-user' : 'is-ai'}`}>
                  {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                </span>
                <div className="chat-bubble">
                  {msg.content}
                  {msg.docs && msg.docs.length > 0 && (
                    <details className="chat-refs">
                      <summary>参考资料（{msg.docs.length} 段）</summary>
                      {msg.docs.map((d, i) => (
                        <div className="chat-ref-item" key={i}>
                          {d.length > 260 ? d.slice(0, 260) + '…' : d}
                        </div>
                      ))}
                    </details>
                  )}
                </div>
              </div>
            ))}

            {asking && (
              <div className="chat-row is-ai">
                <span className="chat-avatar is-ai"><RobotOutlined /></span>
                <div className="chat-bubble">
                  <Spin size="small" /> <span style={{ marginLeft: 8 }}>正在检索知识库…</span>
                </div>
              </div>
            )}
          </div>

          <div className="chat-input-row">
            <TextArea
              className="ask-input"
              rows={2}
              placeholder="输入问题，例如：这份文档的主要结论是什么？"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault()
                  handleAsk()
                }
              }}
            />
            <Button
              type="primary"
              className="ask-btn chat-send"
              icon={<SendOutlined />}
              onClick={handleAsk}
              loading={asking}
            >
              发送
            </Button>
          </div>
        </Card>
      </div>
    </div>
  )
}