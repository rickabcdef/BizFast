// BizFast scaffold generator - creates repetitive module stubs only.
// Run: node scripts/_scaffold.gen.js   (safe to delete after first run)
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '..');

function write(rel, content) {
  const full = path.join(ROOT, rel);
  fs.mkdirSync(path.dirname(full), { recursive: true });
  fs.writeFileSync(full, content, 'utf8');
}

// Module registry: id, title, owner (A/B/C/D), priority, summary
const MODULES = [
  { id: 'm1_home',     title: '首屏与启动',           owner: 'D', prio: 'P0', summary: '启动资金/时间/城市三要素采集，游客可用，冷启动性能。' },
  { id: 'm2_diagnose', title: '生意诊断',             owner: 'A', prio: 'P0', summary: '条件校验打标、进度可视化、机会热度图、24h缓存、AI降级。' },
  { id: 'm3_match',    title: '商机匹配',             owner: 'A', prio: 'P0', summary: '3个匹配商机卡片、五要素数字卡、详情、案例、风险、锁定付费。' },
  { id: 'm4_delivery', title: '启动包生成与交付',     owner: 'B', prio: 'P0', summary: '十件交付物(D01-D10)异步生成、进度、ZIP、云端永久保存。' },
  { id: 'm5_pay',      title: '付费与订单',           owner: 'A', prio: 'P0', summary: '付费弹窗、三档价格、各端支付适配、订单状态机、退款。' },
  { id: 'm6_tools',    title: '工具箱',               owner: 'C', prio: 'P1', summary: '图片压缩转换、PDF合并拆分、二维码、文案助手，永久免费。' },
  { id: 'm7_games',    title: '解压小游戏',           owner: 'C', prio: 'P1', summary: '指尖解压、数字合成，Canvas纯自研，无广告无内购。' },
  { id: 'm8_share',    title: '分享与增长',           owner: 'D', prio: 'P1', summary: '成果卡片、多渠道分享、邀请奖励、数据回收、脱敏合规。' },
  { id: 'm10_user',    title: '个人中心',             owner: 'D', prio: 'P0', summary: '账号、订单、权益、工具入口、多端同步。' },
  { id: 'm11_admin',   title: '运营管理后台',         owner: 'B+D', prio: 'P1', summary: '分享转化、用户管理、订单查询（内部角色）。' },
];

// ---------- Frontend page stubs ----------
for (const m of MODULES) {
  const cls = m.id.replace(/_/g, '-');
  const page = `import { View, Text } from '@tarojs/components'
import './index.scss'

// ${m.id} ${m.title} | 负责人: ${m.owner} | 优先级: ${m.prio}
// 需求点: 见 docs/api-contract.md 与 docs/module-ownership.md
export default function ${toPascal(m.id)}() {
  return (
    <View className='page ${cls}'>
      <Text className='placeholder'>${m.title}（TODO: 负责人 ${m.owner} 实现 | ${m.prio}）</Text>
    </View>
  )
}
`;
  write(`frontend/src/pages/${m.id}/index.tsx`, page);
  write(`frontend/src/pages/${m.id}/index.scss`, `.page.${cls} { min-height: 100vh; }\n.placeholder { color: #8b93b8; padding: 32px; display: block; }\n`);
  write(`frontend/src/pages/${m.id}/index.config.ts`, `export default definePageConfig({\n  navigationBarTitleText: '${m.title}'\n})\n`);
  write(`frontend/src/pages/${m.id}/README.md`,
    `# ${m.id} ${m.title}\n\n- 负责人: **${m.owner}**\n- 优先级: **${m.prio}**\n- 概述: ${m.summary}\n\n## 需求点\n见 \`docs/api-contract.md\` 对应模块。\n\n## 验收\nP0 模块为网页版第 1-4 周必须上线。\n`);
}

// ---------- Backend router + service stubs ----------
const BE = [
  { key: 'auth',      mod: 'm10_user',  title: '账号与鉴权',     owner: 'D' },
  { key: 'diagnose',  mod: 'm2_diagnose', title: '生意诊断',     owner: 'A' },
  { key: 'match',     mod: 'm3_match',  title: '商机匹配',       owner: 'A' },
  { key: 'package',   mod: 'm4_delivery', title: '启动包生成',   owner: 'B' },
  { key: 'payment',   mod: 'm5_pay',    title: '付费与订单',     owner: 'A' },
  { key: 'tools',     mod: 'm6_tools',  title: '工具箱',         owner: 'C' },
  { key: 'games',     mod: 'm7_games',  title: '解压小游戏',     owner: 'C' },
  { key: 'share',     mod: 'm8_share',  title: '分享与增长',     owner: 'D' },
  { key: 'notify',    mod: 'm9_notify', title: '消息与提醒',     owner: 'A' },
  { key: 'admin',     mod: 'm11_admin', title: '运营管理后台',   owner: 'B+D' },
];
for (const b of BE) {
  const router = `"""${b.title} - 负责人 ${b.owner} - 对应 ${b.mod}
路由前缀: /api/${b.key}
需求点: 见 docs/api-contract.md
"""
from fastapi import APIRouter

router = APIRouter(prefix='/api/${b.key}', tags=['${b.key}'])

# TODO: 在此实现本模块接口，业务逻辑放入 app/services/${b.key}.py
`;
  write(`backend/app/routers/${b.key}.py`, router);
  const svc = `"""${b.title} 业务逻辑层 - 负责人 ${b.owner}
所有算法/计算/生成逻辑集中在此，禁止各端重复实现。
"""
# TODO: 实现本模块业务函数，供 routers/${b.key}.py 调用。
`;
  write(`backend/app/services/${b.key}.py`, svc);
}

// ---------- Python __init__ stubs ----------
const pkgs = ['app','app/core','app/models','app/schemas','app/routers','app/services','app/ai','app/queue','app/office','app/storage','app/utils','backend/tests'];
for (const p of pkgs) write(`${p}/__init__.py`, `# package\n`);

// ---------- .gitkeep for purely-empty dirs ----------
const keeps = ['frontend/src/components','frontend/src/store','frontend/src/constants','frontend/src/canvas-games','frontend/src/utils','backend/migrations/versions','tests'];
for (const k of keeps) write(`${k}/.gitkeep`, '');

function toPascal(s){ return s.split(/[_-]/).map(w=>w.charAt(0).toUpperCase()+w.slice(1)).join(''); }
console.log('scaffold stubs generated: ' + MODULES.length + ' frontend pages, ' + BE.length + ' backend modules');
