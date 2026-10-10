import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import './index.css'
import App from './App.jsx'

// 统一视觉风格：主色、圆角、字体、组件细节（仅主题层，不影响业务逻辑）
const theme = {
  token: {
    colorPrimary: '#6366f1',
    colorInfo: '#6366f1',
    colorLink: '#6366f1',
    colorTextHeading: '#0f172a',
    colorText: '#334155',
    colorBorderSecondary: '#f1f3f9',
    borderRadius: 12,
    fontSize: 14,
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif",
    boxShadowTertiary:
      '0 1px 2px rgba(15, 23, 42, 0.04), 0 10px 26px -16px rgba(15, 23, 42, 0.18)',
  },
  components: {
    Card: {
      borderRadiusLG: 18,
      paddingLG: 22,
      headerFontSize: 15,
    },
    Table: {
      headerBg: '#f8f9fe',
      headerColor: '#475069',
      headerSplitColor: 'transparent',
      borderColor: '#f1f3f9',
      rowHoverBg: '#f8f9ff',
    },
    Button: {
      fontWeight: 500,
    },
    Tabs: {
      itemSelectedColor: '#4f46e5',
      inkBarColor: '#4f46e5',
      horizontalItemGutter: 24,
    },
    Progress: {
      defaultColor: '#6366f1',
    },
    Empty: {
      colorTextDescription: '#94a3b8',
    },
  },
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ConfigProvider locale={zhCN} theme={theme}>
      <App />
    </ConfigProvider>
  </StrictMode>,
)
