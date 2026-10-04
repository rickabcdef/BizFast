# 技术选型 · BizFast

## 前端

| 项 | 选型 | 理由 |
|---|---|---|
| 框架 | **Taro 4 + React 18 + TypeScript** | 一套代码编译 Web/H5 + 微信小程序 + App(RN) + 鸿蒙(OpenHarmony)，契合 PRD「网页版为代码地基」要求 |
| 状态管理 | Zustand（或 Taro 自带 + React Context） | 轻量、跨端一致 |
| 请求层 | 自研 `services/api.ts`（fetch 封装） | 统一错误处理、进度轮询、Token 注入 |
| 样式 | SCSS + 设计令牌（`theme/tokens.ts`） | 科技风：藏蓝背景、蓝紫渐变、呼吸光效，各端只改布局不改色值 |
| 小游戏 | 原生 H5 + Canvas，零第三方引擎 | M7 美术 100% 代码绘制 |
| 桌面 | 后续 Tauri/Electron 包装 Web 产物 | Win/Mac 复用 |

## 后端

| 项 | 选型 | 理由 |
|---|---|---|
| 语言 | Python 3.11 | PRD 明确 Python 生态（Pillow/pypdf/qrcode） |
| Web 框架 | **FastAPI** | 异步、类型化、自带 OpenAPI 文档，适合队列 + AI 调用 |
| ORM | SQLAlchemy 2（async） | 关系型数据建模 |
| 校验 | Pydantic v2 | 请求/响应契约，与前端 `types/index.ts` 对齐 |
| 鉴权 | JWT（access + refresh） | 游客可免登录，注册用户多端同步 |
| 队列 | **RQ**（或 Celery + Redis） | 启动包异步生成（M4-01） |
| 缓存 | Redis | 诊断 24h 缓存、热点数据、会话 |
| 对象存储 | S3 兼容（MinIO 本地 / 云 OSS 生产） | 启动包永久保存（M4-05） |

## 数据

- **关系库**：PostgreSQL（账号、订单状态机、权益/会员、分享邀请、风控）。
- **缓存**：Redis。
- **对象存储**：启动包文件（ZIP/PDF/Excel/PNG/SVG）云端永久保存，多端下载。

## 办公文件生成（严格锁定，仅 MIT/BSD/LGPL）

| 用途 | 库 | 协议 | 红线（禁用） |
|---|---|---|---|
| 图片处理 | Pillow + libvips（动态链接） | MIT / LGPL | — |
| PDF 合并/拆分/读取 | pypdf | BSD-3 | **PyMuPDF(AGPL)**、**itext7(AGPL)** |
| 二维码 | python-qrcode | BSD | — |
| 图片压缩 | libvips | LGPL（动态链接） | **pngquant(GPL-3.0)** |
| 文案助手 | 大模型 API + 自研后处理 | — | 不存储用户输入原文 |

## 依赖协议白名单

- ✅ 允许：MIT / Apache-2.0 / BSD / LGPL（动态链接）
- ❌ 禁止：GPL / AGPL（任何版本）

> 引入新依赖前，先在 `requirements.txt` 备注协议；CI 需做许可证扫描（见 ADR）。
