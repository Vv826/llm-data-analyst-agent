import { useState } from 'react'
import { Button, Card, Input, Tag, Upload, Empty, message } from 'antd'
import {
  CodeOutlined,
  UploadOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import axios from 'axios'

const API = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

const EXAMPLES = [
  '计算每一列的总和',
  '按类别分组求平均值',
  '找出数值最大的前 5 行',
]

export default function CodePanel() {
  const [filename, setFilename] = useState(null)
  const [question, setQuestion] = useState('')
  const [code, setCode] = useState('')
  const [safe, setSafe] = useState(null)
  const [issues, setIssues] = useState([])
  const [output, setOutput] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('') // '' | 'gen' | 'run'

  const doUpload = async ({ file, onSuccess, onError }) => {
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await axios.post(`${API}/upload`, form)
      if (res.data?.success) {
        setFilename(res.data.filename)
        setCode(''); setOutput(''); setError(''); setSafe(null)
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

  const generate = async () => {
    if (!filename) return message.warning('请先上传表格')
    if (!question.trim()) return message.warning('请先输入问题')
    setBusy('gen'); setCode(''); setOutput(''); setError('')
    try {
      const res = await axios.post(`${API}/code/generate`, { filename, question })
      if (res.data?.success) {
        setCode(res.data.code)
        setSafe(res.data.safe)
        setIssues(res.data.issues || [])
      } else {
        message.error(res.data?.error || '生成失败')
      }
    } catch {
      message.error('请求失败，请确认后端已启动')
    } finally {
      setBusy('')
    }
  }

  const run = async () => {
    if (!code.trim()) return message.warning('没有可运行的代码')
    setBusy('run'); setOutput(''); setError('')
    try {
      const res = await axios.post(`${API}/code/run`, { filename, code })
      setOutput(res.data?.output || '')
      setError(res.data?.success ? '' : (res.data?.error || '执行失败'))
    } catch {
      message.error('请求失败，请确认后端已启动')
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="layout">
      <div className="col">
        <Card
          className="panel rise"
          title={<span className="panel-title"><CodeOutlined />代码生成</span>}
          extra={<span className="panel-header-hint">生成 → 人工确认 → 执行</span>}
        >
          <div className="multi-file-row">
            <Upload customRequest={doUpload} showUploadList={false} accept=".csv,.xlsx">
              <Button icon={<UploadOutlined />}>{filename ? '更换表格' : '上传表格'}</Button>
            </Upload>
            {filename ? (
              <span className="multi-file-name">{filename}</span>
            ) : (
              <span className="multi-file-hint">先上传一个 CSV / Excel</span>
            )}
          </div>

          <Input.TextArea
            rows={3}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="用自然语言描述你想怎么处理这张表，例如：按城市分组求平均销售额"
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
            loading={busy === 'gen'}
            onClick={generate}
            icon={<CodeOutlined />}
          >
            {busy === 'gen' ? '正在生成代码…' : '生成代码'}
          </Button>

          <p className="multi-note">
            <SafetyCertificateOutlined /> 生成的代码**不会自动执行**：先经 AST 安全校验，
            再由你确认后点「运行」，且执行环境已清空内置函数。
          </p>
        </Card>
      </div>

      <div className="col">
        {!code ? (
          <Card className="panel rise">
            <Empty description="输入问题并点击「生成代码」" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </Card>
        ) : (
          <>
            <Card
              className="panel rise"
              title={<span className="panel-title"><CodeOutlined />生成的代码（可编辑）</span>}
              extra={
                safe ? (
                  <Tag icon={<SafetyCertificateOutlined />} className="code-safe">安全检查通过</Tag>
                ) : (
                  <Tag icon={<WarningOutlined />} style={{ color: '#dc2626', borderColor: '#dc2626' }}>
                    未通过校验
                  </Tag>
                )
              }
            >
              <Input.TextArea
                className="code-editor"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                rows={8}
                spellCheck={false}
              />
              {!safe && issues.length > 0 && (
                <p className="multi-note" style={{ color: '#dc2626' }}>
                  {issues.join('；')}
                </p>
              )}
              <Button
                className="code-run"
                type="primary"
                block
                size="large"
                icon={<PlayCircleOutlined />}
                loading={busy === 'run'}
                onClick={run}
              >
                {busy === 'run' ? '正在执行…' : '运行代码'}
              </Button>
            </Card>

            {(output || error) && (
              <Card
                className="panel rise"
                title={<span className="panel-title"><PlayCircleOutlined />执行结果</span>}
              >
                <pre className={`code-output${error ? ' is-error' : ''}`}>{error || output}</pre>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  )
}