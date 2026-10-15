import { useEffect, useState } from 'react'
import { Tag } from 'antd'
import { DashboardOutlined, WarningOutlined } from '@ant-design/icons'
import axios from 'axios'

const API = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

// 告警 code → 简短标签（完整信息放在 title 里，鼠标悬停可见）
const ALERT_LABEL = {
  slow_call: '调用过慢',
  high_fail_rate: '失败率偏高',
  token_budget: 'Token 超预算',
}

export default function MetricsBar() {
  const [m, setM] = useState(null)

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const res = await axios.get(`${API}/metrics`)
        if (alive) setM(res.data)
      } catch {
        // 后端没起时静默忽略
      }
    }
    load()
    const timer = setInterval(load, 5000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])

  if (!m || !m.calls) return null

  return (
    <div className="metrics-bar">
      <span className="metrics-title"><DashboardOutlined /> 模型调用监控</span>
      <Tag>{m.calls} 次调用</Tag>
      <Tag>{m.total_tokens.toLocaleString()} tokens</Tag>
      <Tag>均值 {m.avg_latency_ms} ms</Tag>
      <Tag>P95 {m.p95_latency_ms} ms</Tag>
      <Tag>估算 ¥{m.total_cost.toFixed(4)}</Tag>
      {m.failed > 0 && <Tag style={{ color: '#dc2626' }}>{m.failed} 次失败</Tag>}
      {(m.alerts || []).map((a) => (
        <Tag
          key={a.code}
          title={`${a.message}（阈值：${JSON.stringify(m.thresholds || {})}）`}
          style={{
            color: '#dc2626',
            borderColor: a.level === 'error' ? '#dc2626' : undefined,
            background: a.level === 'error' ? '#fef2f2' : undefined,
          }}
        >
          <WarningOutlined /> {ALERT_LABEL[a.code] || a.code}
        </Tag>
      ))}
    </div>
  )
}