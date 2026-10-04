# BizFast · 生意快启

> AI 驱动的「生意决策 + 落地交付」工具。用户输入 **启动资金 / 每日可投入时间 / 所在城市** 三个条件，约 30 分钟交付一份可直接开干的《生意启动包》（10 件实体文件）。
>
> - 产品代号：**BizFast / 生意快启**
> - 商业模式：Freemium（信息层永久免费，方案层与结果层付费）
> - 北极星指标：每周成功交付的《生意启动包》数量（付费生成成功单数）
> - 战略顺序：**网页版先行（1–4 周，含付费验证关）→ 小程序（5–7 周）→ Android/iOS（8–13 周）→ 鸿蒙/Win/Mac（14–18 周）**
> - 熔断机制：网页版付费转化率 < 3% 时暂停铺端

详细需求见 [`docs/prd/`](docs/prd/)（原 PRD V2.1 与产品创意文档）。

---

## 技术栈总览

| 层 | 选型 | 说明 |
|---|---|---|
| 前端（一套代码多端） | **Taro 4 + React + TypeScript** | 网页版(H5) 为代码地基，可编译为微信小程序 / App(RN) / 鸿蒙(OpenHarmony)；Win/Mac 复用 Web 产物（Tauri/Electron 后续接入） |
| 后端 | **Python 3.11 + FastAPI** | 业务逻辑、算法、生成逻辑**只在后端**，七端对齐 |
| ORM / 校验 | **SQLAlchemy 2 + Pydantic v2** | |
| 关系库 | **PostgreSQL** | 账号、订单状态机、权益、分享关系、风控 |
| 缓存 / 队列 | **Redis** | 诊断结果 24h 缓存；启动包异步生成（RQ / Celery） |
| 对象存储 | **S3 兼容（MinIO 本地 / 云 OSS 生产）** | 启动包 ZIP/PDF/Excel 云端永久保存 |
| 办公文件生成 | **Pillow + pypdf + python-qrcode + libvips** | 仅 MIT/BSD/LGPL，**严禁** PyMuPDF/itext7/pngquant（AGPL/GPL） |
| 容器化 | **Docker Compose** | 本地一键起全部依赖 |

> 开源协议白名单：**MIT / Apache / BSD / LGPL（动态链接）**；红线：**GPL / AGPL 禁止**。详见 [`docs/adr/README.md`](docs/adr/README.md)。

## 仓库结构

```
BizFast/
├── docs/                 # 架构、技术栈、接口契约、模块归属、ADR、PRD 原文
├── assets/ui/            # UI 切图、原型、设计稿（参考素材，不参与构建）
├── frontend/             # 一套前端代码 → 七端（Taro + React + TS）
│   └── src/
│       ├── pages/        # 按 M1–M11 模块分目录（每模块一页）
│       ├── components/   # 科技风通用组件
│       ├── services/     # API 客户端（按模块）
│       ├── utils/        # 跨端适配（支付 / 分享 / 存储）
│       ├── theme/        # 设计令牌（藏蓝背景 / 蓝紫渐变 / 呼吸光效）
│       ├── canvas-games/ # M7 自研小游戏
│       ├── store/        # 状态管理
│       ├── types/        # 与后端 schema 对齐的 TS 类型
│       └── constants/    # 模块 / 交付物枚举
├── backend/              # Python + FastAPI（业务逻辑唯一处）
│   └── app/
│       ├── core/         # config / database / security / errors / logging
│       ├── models/       # SQLAlchemy 实体
│       ├── schemas/      # Pydantic 请求/响应
│       ├── routers/      # 各模块 API 路由
│       ├── services/     # 各模块业务逻辑
│       ├── ai/           # 大模型客户端 + 降级策略
│       ├── queue/        # 启动包异步生成消费者
│       ├── office/       # D01–D10 十件交付物生成器
│       ├── storage/      # 对象存储适配
│       └── utils/
├── infra/                # Docker Compose / Dockerfile / nginx / .env.example
├── scripts/              # 脚手架与本地引导脚本
└── tests/                # 共享契约 / E2E 测试
```

## 模块与负责人映射（4 名 AI 程序员）

| 开发者 | 职责模块 | 模块 |
|---|---|---|
| **A** | 诊断 / 匹配 / 付费 / 消息 | M2 诊断、M3 匹配、M5 付费、M9 消息 |
| **B** | 生成 / 运营后台 | M4 启动包生成、M11 运营管理后台 |
| **C** | 工具箱 / 小游戏 | M6 工具箱、M7 解压小游戏 |
| **D** | 首屏 / 个人中心 / 分享 | M1 首屏、M8 分享、M10 个人中心 |

> 完整拆分、接口清单、优先级见 [`docs/module-ownership.md`](docs/module-ownership.md) 与 [`docs/api-contract.md`](docs/api-contract.md)。

## 本地开发

### 后端（端口 8000）
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # 填写数据库 / Redis / 对象存储 / 大模型 Key
uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs
```

### 前端（网页版 H5，端口 10086）
```bash
cd frontend
npm install
npm run dev                     # Taro 开发模式（H5）
# 编译小程序: npm run build:weapp ；编译 App: npm run build:rn
```

### 一键起依赖（PostgreSQL / Redis / MinIO）
```bash
cd infra && docker compose up -d
```

## 分支与协作规范

- 主分支：`pm`（本仓库默认，产品/PM 分支，承载脚手架与需求基线）。
- 开发分支：每人基于 `pm` 拉 `dev/<module>`，PR 合回 `pm`。
- 提交信息：`[模块] 动作：说明`，例如 `[M4] feat: 新增 D01 可行性评分卡生成`。
- 严禁把 `.env`、密钥、大体积构建产物提交入库（见 `.gitignore`）。
- 全部错误提示必须为中文 + 重试（禁止英文报错 / 错误码直出），见 `backend/app/core/errors.py`。

## 合规红线（务必遵守）

1. 依赖仅限 MIT / Apache / BSD / LGPL（动态链接）；**GPL / AGPL 一律禁止**。
2. 免费层：不限次、无水印、无广告。
3. 游客不强制登录；iOS 绝不出现站外支付引导。
4. 小游戏美术 100% 代码绘制，音效 CC0 / 自录，禁第三方素材。
5. 文案助手 / AI 调用**不存储用户输入原文**。

## 当前状态

本仓库为 **脚手架（scaffold）**：目录、框架、配置、模块边界、接口契约与团队分工已就绪，待 4 名 AI 程序员按 [`docs/module-ownership.md`](docs/module-ownership.md) 认领并填充实现。
