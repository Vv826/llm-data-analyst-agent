import { useState } from 'react'
import { Button, Card, Input, Tag, Upload, Spin, Empty, message } from 'antd'
import {
  ThunderboltOutlined,
  UploadOutlined,
  RobotOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  BulbOutlined,
} from '@ant-design/icons'
import axios from 'axios'

const API = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

// 专家的展示信息（与后端 /multi/analyze 返回的 plan 字段对齐）
const AGENT_META = {
  data: { label: '数据分析专家', icon: <DatabaseOutlined /> },
  kb: { label: '知识库专家', icon: <FileTextOutlined /> },
}

const EXAMPLES = [
  '知识库里项目分析报告的主要结论是什么？我上传的表格数据能支持这些结论吗？',
  '这份表格里有哪些字段、大概是什么数据？',
  '知识库里的薪资结论，和这份表格的收入分布一致吗？',
]

export default function MultiPanel() {
  const [filename, setFilename] = useState(null)
  const [question, setQuestion] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)

  const doUpload = async ({ file, onSuccess, onError }) => {
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await axios.post(`${API}/upload`, form)
      if (res.data?.success) {
        setFilename(res.data.filename)
        message.success(`表格已就绪：${res.data.filename}`)
        onSuccess?.(res.data)
      } else {
        message.error(res.data?.error || '上传失败')
        onError?.(new Error('upload failed'))
      }
    } catch {
      message.error('上传失败，请确认后端已启动')
      onError?.(new Error('upload failed'))
    }
  }

  const run = async () => {
    const q = question.trim()
    if (!q) {
      message.warning('请先输入问题')
      return
    }
    setRunning(true)
    setResult(null)
    try {
      const res = await axios.post(`${API}/multi/analyze`, { question: q, filename })
      if (res.data?.success) setResult(res.data)
      else message.error(res.data?.error || '执行失败')
    } catch {
      message.error('请求失败，请确认后端已启动')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="layout">
      <div className="col">
        <Card
          className="panel rise"
          title={<span className="panel-title"><ThunderboltOutlined />协同任务</span>}
          extra={<span className="panel-header-hint">Supervisor 调度</span>}
        >
          <div className="multi-file-row">
            <Upload customRequest={doUpload} showUploadList={false} accept=".csv,.xlsx">
              <Button icon={<UploadOutlined />}>{filename ? '更换表格' : '上传表格（可选）'}</Button>
            </Upload>
            {filename ? (
              <>
                <span className="multi-file-name">{filename}</span>
                <Button type="link" size="small" onClick={() => setFilename(null)}>移除</Button>
              </>
            ) : (
              <span className="multi-file-hint">不选则只由知识库专家回答</span>
            )}
          </div>

          <Input.TextArea
            rows={3}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="例如：知识库里报告的结论，和我上传的表格数据对得上吗？"
          />

          <div className="multi-examples">
            {EXAMPLES.map((e) => (
              <Tag key={e} className="multi-example" onClick={() => setQuestion(e)}>{e}</Tag>
            ))}
          </div>

          <Button
            type="primary"
            block
            size="large"
            loading={running}
            onClick={run}
            icon={<ThunderboltOutlined />}
          >
            {running ? '多智能体协同中…' : '开始协同分析'}
          </Button>

          <p className="multi-note">
            <BulbOutlined /> Supervisor 先判断需要哪些专家，再由专家各自执行，最后融合结论。
          </p>
        </Card>
      </div>

      <div className="col">
        {running && (
          <Card className="panel rise">
            <div className="multi-running">
              <Spin />
              <div>
                <div>正在协同处理…</div>
                <div className="multi-running-hint">
                  规划 → 专家执行 → 融合结论，通常需要 40~80 秒
                </div>
              </div>
            </div>
          </Card>
        )}

        {!running && !result && (
          <Card className="panel rise">
            <Empty description="填写问题后点击「开始协同分析」" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </Card>
        )}

        {result && (
          <>
            <Card
              className="panel rise"
              title={<span className="panel-title"><RobotOutlined />调度与专家结论</span>}
              extra={<span className="panel-header-hint">总耗时 {result.elapsed_ms} ms</span>}
            >
              <div className="multi-plan">
                <span className="multi-plan-label">Supervisor 规划</span>
                {(result.plan || []).map((a) => (
                  <Tag key={a} className="multi-agent-tag">
                    {AGENT_META[a]?.icon} {AGENT_META[a]?.label || a}
                  </Tag>
                ))}
              </div>

              {(result.findings || []).map((f) => (
                <details key={f.agent} className="multi-finding">
                  <summary>
                    <span className="multi-finding-title">
                      {AGENT_META[f.agent]?.icon} {f.title}
                    </span>
                    <span className="multi-finding-meta">{f.elapsed_ms} ms</span>
                    {f.docs?.length > 0 && (
                      <Tag className="multi-doc-count">命中 {f.docs.length} 段原文</Tag>
                    )}
                  </summary>
                  <div className="multi-finding-body">{f.content}</div>
                  {f.docs?.length > 0 && (
                    <div className="multi-doc-list">
                      {f.docs.map((d, i) => (
                        <div key={i} className="multi-doc-item">{d}</div>
                      ))}
                    </div>
                  )}
                </details>
              ))}
            </Card>

            <Card
              className="panel rise"
              title={<span className="panel-title"><ThunderboltOutlined />融合结论</span>}
            >
              <div className="multi-answer">{result.answer}</div>
            </Card>
          </>
        )}
      </div>
    </div>
  )
}