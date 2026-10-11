import { useState } from 'react'
import {
  Upload,
  Button,
  Input,
  Card,
  Table,
  message,
  Tag,
  Progress,
  Empty,
  Tabs,
  Alert,
  Skeleton,
  Segmented,
} from 'antd'
import {
  InboxOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  TableOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  BulbOutlined,
  CopyOutlined,
  CodeOutlined,
  RocketOutlined,
} from '@ant-design/icons'
import axios from 'axios'
import ReactECharts from 'echarts-for-react'
import RagPanel from './RagPanel'
import './App.css'

const { TextArea } = Input

// 图表配色（黑白灰：靠深浅区分序列）
const PALETTE = [
  '#18181b',
  '#3f3f46',
  '#52525b',
  '#71717a',
  '#a1a1aa',
  '#c4c4c8',
  '#e4e4e7',
]

// 提问示例（仅 UI 辅助，点击后填入输入框）
const QUICK_QUESTIONS = [
  '各个分类的数量分布是怎样的？',
  '数值列的平均值分别是多少？',
  '排名前 10 的记录是什么？',
]

// 图表类型中文名（仅展示用）
const CHART_LABELS = { bar: '柱状图', line: '折线图', pie: '饼图' }

// 智能体执行链路（从原标签页里抽出来，失败分支也能复用同一套渲染）
function ToolHistory({ items }) {
  if (!items || items.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={<span style={{ color: '#a1a1aa', fontSize: 13 }}>本次没有调用任何工具</span>}
      />
    )
  }
  return (
    <div className="history-list">
      {items.map((item, index) => (
        <div className="history-item" key={index}>
          <div className="history-head">
            <Tag style={{ margin: 0 }}>第 {item.step} 步</Tag>
            <Tag className="col-tag" style={{ margin: 0 }}>{item.action}</Tag>
          </div>
          {item.thought ? (
            <p className="history-line">
              <span className="history-key" style={{ color: '#18181b' }}>思考：</span>
              {item.thought}
            </p>
          ) : null}
          <p className="history-line">
            <span className="history-key" style={{ color: '#71717a' }}>参数：</span>
            <code className="history-code">{JSON.stringify(item.input)}</code>
          </p>
        </div>
      ))}
    </div>
  )
}

function App() {
  const [fileName, setFileName] = useState('')
  const [dataQuality, setDataQuality] = useState(null)
  const [question, setQuestion] = useState('')
  const [analyzeResult, setAnalyzeResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [mode, setMode] = useState('data')

  // 上传文件
  const handleUpload = async (file) => {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await axios.post('http://127.0.0.1:8000/upload', formData)
      // 后端解析失败时返回的是 HTTP 200 + success:false；
      // 不判断的话 dataQuality 里没有 column_names，渲染时会把整个页面搞白屏
      if (res.data?.success === false) {
        setDataQuality(null)
        setFileName('')
        message.error('上传失败：' + (res.data.error || '文件无法解析'))
        return false
      }
      setFileName(file.name)
      setDataQuality(res.data)
      message.success('上传成功！')
    } catch (err) {
      message.error('上传失败：' + (err?.response?.data?.error || err?.message || '请确认后端已启动'))
    }
    return false
  }

  // 发送分析请求
  const handleAnalyze = async () => {
    if (!fileName) {
      message.warning('请先上传文件')
      return
    }
    if (!question.trim()) {
      message.warning('请先输入你的问题')
      return
    }
    setLoading(true)
    try {
      const res = await axios.post('http://127.0.0.1:8000/analyze', null, {
        params: { filename: fileName, question: question }
      })
      setAnalyzeResult(res.data)
      if (res.data.success) {
        message.success('分析完成！')
      } else {
        message.error('分析出错：' + res.data.error)
      }
    } catch (err) {
      message.error('请求失败：' + (err?.response?.data?.error || err?.message || '请确认后端已启动'))
    } finally {
      setLoading(false)
    }
  }

  // 复制文本（仅交互辅助）
  const handleCopy = async (text) => {
    try {
      await navigator.clipboard.writeText(text ?? '')
      message.success('已复制到剪贴板')
    } catch {
      message.error('复制失败，请手动选择文本')
    }
  }

  // 生成图表配置
  const getChartOption = () => {
    if (!analyzeResult?.success || !analyzeResult?.chart) return {}
    const { type } = analyzeResult.chart
    const data = analyzeResult.result

    let xData = []
    let yData = []

    // ========== 全格式兼容数据提取 ==========
    if (Array.isArray(data) && data.length > 0) {
      // 数组对象格式
      const keys = Object.keys(data[0])
      const xKey = keys[0]
      let yKey = keys.find(k => typeof data[0][k] === 'number' && !isNaN(data[0][k]))
      if (!yKey && keys.length > 1) yKey = keys[1]
      if (!yKey) yKey = keys[0]

      xData = data.map(item => String(item[xKey]))
      yData = data.map(item => {
        const val = Number(item[yKey])
        return isNaN(val) ? 0 : val
      })

    } else if (typeof data === 'object' && data !== null) {
      // 纯字典格式
      const keys = Object.keys(data)
      xData = keys.map(String)
      
      const firstVal = data[keys[0]]
      if (typeof firstVal === 'object' && firstVal !== null) {
        // 嵌套统计对象：默认取 mean 平均值
        yData = keys.map(k => {
          const num = Number(data[k]?.mean ?? data[k]?.value ?? 0)
          return isNaN(num) ? 0 : num
        })
      } else {
        // 普通键值对：直接取值
        yData = keys.map(k => {
          const num = Number(data[k])
          return isNaN(num) ? 0 : num
        })
      }
    }

    const axisStyle = {
      axisLine: { lineStyle: { color: '#e4e4e7' } },
      axisTick: { show: false },
      axisLabel: { color: '#71717a', fontSize: 11.5 },
    }

    const commonOption = {
      color: PALETTE,
      grid: { left: 12, right: 20, top: 34, bottom: 8, containLabel: true },
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(24, 24, 27, 0.92)',
        borderWidth: 0,
        padding: [8, 12],
        textStyle: { color: '#fafafa', fontSize: 12.5 },
        axisPointer: {
          type: 'shadow',
          shadowStyle: { color: 'rgba(24, 24, 27, 0.06)' },
        },
      },
      xAxis: {
        type: 'category',
        data: xData,
        ...axisStyle,
        axisLabel: { ...axisStyle.axisLabel, interval: 0, hideOverlap: true },
      },
      yAxis: {
        type: 'value',
        ...axisStyle,
        splitLine: { lineStyle: { color: '#f4f4f5', type: 'dashed' } },
      },
    }

    switch (type) {
      case 'bar':
        return {
          ...commonOption,
          series: [{
            type: 'bar',
            data: yData,
            barMaxWidth: 38,
            itemStyle: { borderRadius: [6, 6, 0, 0], color: '#18181b' },
            emphasis: { itemStyle: { color: '#3f3f46' } },
          }]
        }
      case 'line':
        return {
          ...commonOption,
          tooltip: { ...commonOption.tooltip, axisPointer: { type: 'line', lineStyle: { color: '#a1a1aa', type: 'dashed' } } },
          series: [{
            type: 'line',
            data: yData,
            smooth: true,
            symbol: 'circle',
            symbolSize: 7,
            lineStyle: { width: 2.5, color: '#18181b' },
            itemStyle: { color: '#18181b', borderColor: '#fff', borderWidth: 2 },
            areaStyle: {
              color: {
                type: 'linear',
                x: 0, y: 0, x2: 0, y2: 1,
                colorStops: [
                  { offset: 0, color: 'rgba(24, 24, 27, 0.16)' },
                  { offset: 1, color: 'rgba(24, 24, 27, 0.01)' },
                ],
              },
            },
          }]
        }
      case 'pie':
        return {
          color: PALETTE,
          tooltip: {
            trigger: 'item',
            backgroundColor: 'rgba(24, 24, 27, 0.92)',
            borderWidth: 0,
            padding: [8, 12],
            textStyle: { color: '#fafafa', fontSize: 12.5 },
          },
          legend: {
            bottom: 0,
            icon: 'circle',
            itemWidth: 9,
            itemHeight: 9,
            textStyle: { color: '#71717a', fontSize: 12 },
          },
          series: [{
            type: 'pie',
            radius: ['46%', '68%'],
            center: ['50%', '44%'],
            avoidLabelOverlap: true,
            itemStyle: { borderColor: '#fff', borderWidth: 2, borderRadius: 4 },
            label: { color: '#3f3f46', fontSize: 12, formatter: '{b}\n{d}%' },
            labelLine: { length: 10, length2: 12, lineStyle: { color: '#d4d4d8' } },
            data: xData.map((name, i) => ({ name, value: yData[i] })),
          }]
        }
      default:
        return {
          ...commonOption,
          series: [{ type: 'bar', data: yData, barMaxWidth: 38, itemStyle: { borderRadius: [8, 8, 0, 0] } }]
        }
    }
  }


  // 缺失率配色（黑白灰：越深表示缺失越多）
  const rateColor = (rate) => {
    if (!rate) return '#e4e4e7'
    if (rate < 5) return '#a1a1aa'
    return '#52525b'
  }

  return (
    <div className="app-shell">
      <main className="app-main">
        {/* 顶部横幅 */}
        <header className="hero rise">
          <div className="hero-content">
            <span className="hero-badge">
              <ThunderboltOutlined /> 大模型驱动 · 智能体分析引擎
            </span>
            <h1>AI 自助数据分析平台</h1>
            <p>上传表格文件，用一句自然语言提问，智能体自动规划步骤、调用工具完成分析与可视化。</p>
            <div className="hero-steps">
              <span className="hero-step"><i className="step-index">1</i> 上传数据</span>
              <span className="hero-step"><i className="step-index">2</i> 输入问题</span>
              <span className="hero-step"><i className="step-index">3</i> 智能执行</span>
              <span className="hero-step"><i className="step-index">4</i> 查看结果</span>
            </div>
          </div>
        </header>

        <div className="mode-switch">
          <Segmented
            size="large"
            value={mode}
            onChange={setMode}
            options={[
              { label: '数据分析', value: 'data' },
              { label: '知识库问答', value: 'rag' },
            ]}
          />
        </div>

        <div className="layout" style={{ display: mode === 'data' ? undefined : 'none' }}>
          {/* ================= 左栏：数据 ================= */}
          <div className="col">
            <Card
              className="panel rise"
              title={<span className="panel-title"><InboxOutlined />数据上传</span>}
              extra={<span className="panel-header-hint">CSV · Excel · ≤ 200MB</span>}
            >
              <div className="upload-zone">
                <Upload.Dragger
                  beforeUpload={handleUpload}
                  accept=".csv,.xlsx"
                  maxCount={1}
                >
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined />
                  </p>
                  <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
                  <p className="ant-upload-hint">支持 CSV、Excel(.xlsx) 文件，单文件上限 200MB</p>
                </Upload.Dragger>
              </div>
            </Card>

            {/* 数据质量报告 */}
            {dataQuality && (
              <Card
                className="panel rise"
                title={<span className="panel-title"><DatabaseOutlined />数据质量报告</span>}
                extra={<Tag style={{ margin: 0 }}>已就绪</Tag>}
              >
                <div className="stat-grid">
                  <div className="stat-card">
                    <span className="stat-icon"><FileTextOutlined /></span>
                    <div className="stat-body">
                      <div className="stat-label">文件名称</div>
                      <div className="stat-value is-text">{dataQuality.filename}</div>
                    </div>
                  </div>
                  <div className="stat-card">
                    <span className="stat-icon"><TableOutlined /></span>
                    <div className="stat-body">
                      <div className="stat-label">数据行数</div>
                      <div className="stat-value">{dataQuality.rows}</div>
                    </div>
                  </div>
                  <div className="stat-card">
                    <span className="stat-icon"><DatabaseOutlined /></span>
                    <div className="stat-body">
                      <div className="stat-label">数据列数</div>
                      <div className="stat-value">{dataQuality.columns}</div>
                    </div>
                  </div>
                </div>

                <div className="sub-title">字段列表（{dataQuality.column_names?.length ?? 0}）</div>
                <div className="col-tags">
                  {(dataQuality.column_names || []).map((col) => (
                    <Tag key={col} className="col-tag">{col}</Tag>
                  ))}
                </div>

                <div className="sub-title">缺失值统计</div>
                <Table
                  dataSource={Object.entries(dataQuality.missing_rate || {}).map(([col, rate]) => ({
                    column: col,
                    missing: dataQuality.missing_count?.[col],
                    rate: rate + '%'
                  }))}
                  columns={[
                    { title: '列名', dataIndex: 'column', ellipsis: true },
                    { title: '缺失数量', dataIndex: 'missing', width: 92, align: 'right' },
                    {
                      title: '缺失率',
                      dataIndex: 'rate',
                      width: 168,
                      render: (value) => {
                        const rate = parseFloat(value) || 0
                        const severe = rate >= 5
                        return (
                          <div className="rate-cell">
                            <Progress
                              percent={rate}
                              size="small"
                              showInfo={false}
                              strokeColor={rateColor(rate)}
                              trailColor="#f4f4f5"
                            />
                            <span
                              className={`rate-text${severe ? ' is-severe' : ''}`}
                              title={severe ? '缺失率 ≥ 5%，建议关注' : undefined}
                            >
                              {severe && <i className="rate-dot" />}
                              {value}
                            </span>
                          </div>
                        )
                      },
                    },
                  ]}
                  rowKey="column"
                  size="middle"
                  pagination={{ pageSize: 8, hideOnSinglePage: true, size: 'small' }}
                />
              </Card>
            )}
          </div>

          {/* ================= 右栏：分析 ================= */}
          <div className="col">
            <Card
              className="panel rise"
              title={<span className="panel-title"><RobotOutlined />自然语言分析</span>}
              extra={<span className="panel-header-hint">AI 智能体自主规划执行</span>}
            >
              <TextArea
                className="ask-input"
                rows={3}
                placeholder="输入你的问题，比如：每个班级的数学平均分是多少？"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
              <div className="quick-list">
                <span className="quick-label"><BulbOutlined />试试这样问</span>
                {QUICK_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    type="button"
                    className="quick-chip"
                    onClick={() => setQuestion(q)}
                  >
                    {q}
                  </button>
                ))}
              </div>
              <Button
                type="primary"
                className="ask-btn"
                size="large"
                icon={<RocketOutlined />}
                onClick={handleAnalyze}
                loading={loading}
                block
              >
                开始分析
              </Button>
            </Card>

            {/* 分析进行中 */}
            {loading && (
              <Card className="panel rise" title={<span className="panel-title"><RobotOutlined />智能体执行中</span>}>
                <div className="analysis-loading">
                  <Skeleton active paragraph={{ rows: 4 }} title={false} />
                </div>
              </Card>
            )}

            {/* 分析失败 */}
            {!loading && analyzeResult && !analyzeResult.success && (
              <Card className="panel rise" title={<span className="panel-title"><CodeOutlined />分析未完成</span>}>
                <Alert
                  type="error"
                  showIcon
                  message="分析过程出错了"
                  description={analyzeResult.error}
                  style={{ borderRadius: 12, marginBottom: 16 }}
                />
                {analyzeResult.tool_history && analyzeResult.tool_history.length > 0 && (
                  <>
                    <div className="sub-title">已执行步骤</div>
                    <ToolHistory items={analyzeResult.tool_history} />
                  </>
                )}
              </Card>
            )}

            {/* 分析结果 + 图表 */}
            {!loading && analyzeResult && analyzeResult.success && (
              <>
                {/* 分析结论 */}
                <Card
                  className="panel rise"
                  title={<span className="panel-title"><ThunderboltOutlined />分析结论</span>}
                  extra={<Tag style={{ margin: 0 }}>共 {analyzeResult.steps} 步</Tag>}
                >
                  <p style={{ fontSize: 15, lineHeight: 1.8, margin: 0, color: '#27272a' }}>
                    {analyzeResult.final_answer}
                  </p>
                </Card>

                {/* 可视化图表 */}
                {analyzeResult.chart && (
                  <Card
                    className="panel rise"
                    title={<span className="panel-title"><ThunderboltOutlined />可视化图表</span>}
                    extra={
                      <Tag style={{ margin: 0 }}>
                        {CHART_LABELS[analyzeResult.chart?.type] || '图表'}
                      </Tag>
                    }
                  >
                    <div className="chart-wrap">
                      <ReactECharts option={getChartOption()} style={{ height: 400 }} />
                    </div>
                  </Card>
                )}

                {/* 详情标签页 */}
                <Card className="panel rise" title={<span className="panel-title"><CodeOutlined />分析详情</span>}>
                  <Tabs
                    defaultActiveKey="process"
                    items={[
                      {
                        key: 'process',
                        label: <span><RobotOutlined /> 执行过程</span>,
                        children: <ToolHistory items={analyzeResult.tool_history} />,
                      },
                      {
                        key: 'result',
                        label: <span><TableOutlined /> 计算结果</span>,
                        children: (
                          <div className="code-panel">
                            <div className="code-head">
                              <span className="code-dot red" />
                              <span className="code-dot yellow" />
                              <span className="code-dot green" />
                              <span className="code-title">result.json</span>
                              <Button
                                className="code-copy"
                                type="text"
                                size="small"
                                icon={<CopyOutlined />}
                                onClick={() => handleCopy(JSON.stringify(analyzeResult.result, null, 2))}
                              >
                                复制
                              </Button>
                            </div>
                            <pre className="code-body">{JSON.stringify(analyzeResult.result, null, 2)}</pre>
                          </div>
                        ),
                      },
                    ]}
                  />
                </Card>
              </>
            )}

            {/* 空状态 */}
            {!loading && !analyzeResult && (
              <Card className="panel rise">
                <div className="result-empty">
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={
                      <span style={{ color: '#a1a1aa', fontSize: 13 }}>
                        上传数据并提问后，这里会展示图表与分析结果
                      </span>
                    }
                  />
                </div>
              </Card>
            )}
          </div>
        </div>

        {mode === 'rag' && <RagPanel />}
      </main>
    </div>
  )
}

export default App
