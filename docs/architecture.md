# 系统总体架构 · BizFast

## 1. 设计原则

1. **前后端分离，业务逻辑只在后端**：所有算法、计算、生成逻辑集中在 `backend/`，七端（Web / 小程序 / Android / iOS / 鸿蒙 / Win / Mac）共用同一套后端 API，禁止各端重复实现。
2. **一套前端代码多端复用**：`frontend/` 以网页版(H5) 为代码地基，经 Taro 编译为微信小程序、App(RN)、鸿蒙(OpenHarmony)；桌面端(Win/Mac) 复用 Web 产物（Tauri/Electron 后续接入）。
3. **异步化**：启动包(D01–D10) 生成放入消息队列异步执行，前端轮询真实进度（M4-01）。
4. **缓存**：诊断结果缓存 24h，相同条件不重复消耗算力（M2-06）；热点商机数据进 Redis。
5. **高可用**：主 AI 模型不可用时自动切换备用模型，单模型故障服务可用性 ≥99%（M2-08）。

## 2. 分层架构

```
┌──────────── 七端 (Presentation) ────────────┐
│ Web/H5 · 微信小程序 · Android · iOS · 鸿蒙 · Win/Mac │
│  frontend/ (Taro + React + TS)                │
│   pages/ components/ services/ utils(适配层)   │
└───────────────┬──────────────────────────────┘
                │ HTTPS / JSON （统一 REST + 进度轮询）
┌───────────────▼──────────────────────────────┐
│ 后端 API 网关 (FastAPI)                        │
│  routers/  →  services/  →  models/ + ai/     │
│  core/ (config/security/errors/logging)        │
└───┬───────────┬──────────────┬───────────────┘
    │           │              │
┌───▼───┐  ┌────▼────┐  ┌─────▼─────┐  ┌─────────┐
│Postgres│  │  Redis  │  │  Queue    │  │  Object  │
│账号/订单│  │缓存/会话│  │(RQ/Celery)│  │ Storage │
│权益/风控│  │         │  │ 启动包生成 │  │ ZIP/PDF │
└───────┘  └─────────┘  └─────┬─────┘  └─────────┘
                               │
                        ┌──────▼──────┐
                        │ app/office/ │  D01–D10 生成（Pillow/pypdf/qrcode/libvips）
                        │ app/ai/     │  大模型客户端 + 降级
                        └─────────────┘
```

## 3. 七端战略与平台能力矩阵

| 端 | 优先级 | 周期 | 独有 / 差异能力 |
|---|---|---|---|
| 网页版 Web/H5 | P0 | 1–4 周 | 完整链路、Excel 深度测算、分享、在线预览 |
| 微信小程序 | P1 | 5–7 周 | 微信支付 JSAPI、分享、相册、推送；**不做 PDF 转 Word** |
| Android | P2 | 8–13 周 | 推送、本地文件库、相册 |
| iOS | P2 | 8–13 周 | Apple IAP（**禁止站外支付引导**）、本地文件库 |
| HarmonyOS NEXT | P3 | 14–18 周 | 鸿蒙原生、华为支付 |
| Windows | P3 | 14–18 周 | 批量生成、本地文件库、打印、Excel 深度 |
| macOS | P3 | 14–18 周 | 同 Windows，触控板优化 |

- **通用必须支持**：首屏、诊断、商机、启动包生成下载、在线预览、付费下单、基础工具。
- **熔断**：网页版付费转化率 < 3% 暂停铺端。

## 4. 关键数据流

### 4.1 诊断 + 商机（M2/M3）
游客/注册用户提交三要素 → `POST /api/diagnose` → 校验打标(≤200ms) → 异步产出热度图(≤30s) → 返回 3 个匹配商机卡片 → 点击第 4 个锁定商机触发付费弹窗(M3-07)。结果按条件哈希缓存 24h。

### 4.2 启动包生成（M4）
点击「生成专属启动包」→ `POST /api/payment/create`（弹窗三清单：10件+永久保存+7天退）→ 支付（各端渠道适配）→ 回调/主动查单 → 订单置「生成中」→ 入队 `package.generate` → 后端 `app/office` 顺序生成 D01–D10 → 打包 ZIP + 逐件存对象存储 → 订单置「已交付」→ 前端轮询拿到下载链接。失败重试 2 次，仍失败全额退款(M4-08)。

### 4.3 支付渠道适配（M5-04）
微信内/小程序→微信支付 JSAPI；网页微信外→支付宝网页/扫码；Android→微信/支付宝；iOS→Apple IAP；鸿蒙→华为支付；Win/Mac→支付宝/微信扫码。适配逻辑集中在 `backend/app/services/payment.py` + `frontend/src/utils/platform.ts`。

## 5. 部署拓扑（见 infra/）

- 本地：`docker compose up -d`（Postgres + Redis + MinIO + backend + frontend/nginx）。
- 生产：后端多副本 + 队列 worker 独立扩容；对象存储用云 OSS；前端静态产物走 CDN。
- 主 AI 模型故障时，`app/ai/client.py` 自动降级备用模型，保证可用性 ≥99%。
