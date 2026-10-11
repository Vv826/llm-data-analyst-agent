import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import './index.css'
import App from './App.jsx'

// 统一视觉风格：黑白灰单色主题（仅主题层，不影响业务逻辑）
const theme = {
  token: {
    colorPrimary: '#18181b',
    colorInfo: '#18181b',
    colorLink: '#18181b',
    colorLinkHover: '#3f3f46',
    colorTextHeading: '#18181b',
    colorText: '#3f3f46',
    colorTextSecondary: '#71717a',
    colorTextTertiary: '#a1a1aa',
    colorBorder: '#e4e4e7',
    colorBorderSecondary: '#f4f4f5',
    borderRadius: 10,
    fontSize: 14,
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif",
    boxShadowTertiary: '0 1px 2px rgba(0, 0, 0, 0.04)',
  },
  components: {
    Card: {
      borderRadiusLG: 12,
      paddingLG: 20,
      headerFontSize: 15,
      headerBg: 'transparent',
    },
    Table: {
      headerBg: '#fafafa',
      headerColor: '#52525b',
      headerSplitColor: 'transparent',
      borderColor: '#f4f4f5',
      rowHoverBg: '#fafafa',
    },
    Button: {
      fontWeight: 500,
      primaryShadow: 'none',
    },
    Segmented: {
      trackBg: '#f4f4f5',
      itemSelectedBg: '#18181b',
      itemSelectedColor: '#ffffff',
      itemHoverBg: '#e4e4e7',
    },
    Tabs: {
      itemSelectedColor: '#18181b',
      itemHoverColor: '#18181b',
      inkBarColor: '#18181b',
      horizontalItemGutter: 24,
    },
    Progress: {
      defaultColor: '#18181b',
      remainingColor: '#f4f4f5',
    },
    Empty: {
      colorTextDescription: '#a1a1aa',
    },
    Tag: {
      defaultBg: '#f4f4f5',
      defaultColor: '#52525b',
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
