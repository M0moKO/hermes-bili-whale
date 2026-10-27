/**
 * 养鱼 —— Hermes 桌面运行时插件（磁盘门）
 *
 * 位置：$HERMES_HOME/desktop-plugins/bili-whale/plugin.js
 * 由桌面端在启动时从磁盘加载（不经构建），贡献两样东西：
 *   1) sidebar.nav  → 侧栏一行「养鱼」
 *   2) routes       → /bili-whale 页面，内嵌本地面板（127.0.0.1:8791）
 *
 * 面板服务由 Python 插件 bili_whale 随 Hermes 后端启动。
 */
import { jsx } from 'react/jsx-runtime'

const PANEL_URL = 'http://127.0.0.1:8791/'
const ROUTE = '/bili-whale'

function WhalePanel() {
  return jsx('div', {
    style: { width: '100%', height: '100%', minHeight: '100%', background: '#0f1115' },
    children: jsx('iframe', {
      src: PANEL_URL,
      title: '养鱼面板',
      style: {
        width: '100%',
        height: '100%',
        border: '0',
        display: 'block',
        background: '#0f1115'
      }
    })
  })
}

export default {
  id: 'bili-whale',
  name: '养鱼',
  register(ctx) {
    ctx.registerMany([
      {
        id: 'nav',
        area: 'sidebar.nav',
        order: 60,
        data: { codicon: 'beaker', label: '养鱼', path: ROUTE }
      },
      {
        id: 'page',
        area: 'routes',
        data: { path: ROUTE },
        render: () => jsx(WhalePanel, {})
      }
    ])
  }
}
