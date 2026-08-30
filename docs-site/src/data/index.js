import { sections as promo } from './promo.js'
import { sections as manual } from './manual.js'
import { sections as tech } from './tech.js'

// 主色统一为平台科技蓝（#2F6FED），与 frontend 平台默认主题色一致
export const docs = [
  {
    key: 'promo',
    path: '/promo',
    nav: '宣传手册',
    desc: '平台核心理念、功能亮点与价值主张，快速了解平台全貌。',
    accent: '#2F6FED',
    sections: promo,
  },
  {
    key: 'manual',
    path: '/manual',
    nav: '使用手册',
    desc: '从界面总览到各功能模块，一步步教您上手使用平台。',
    accent: '#2F6FED',
    sections: manual,
  },
  {
    key: 'tech',
    path: '/tech',
    nav: '技术文档',
    desc: '系统架构、仿真算法、数据模型与安全设计等深度技术说明。',
    accent: '#2F6FED',
    sections: tech,
  },
]
