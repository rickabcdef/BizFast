# 架构决策记录（ADR）· BizFast

> 任何技术决策变更，先在此追加一条 ADR（编号递增），再改代码。

## ADR-001 前端采用 Taro 4 + React + TypeScript（一套代码多端）
- **背景**：PRD 要求网页版为代码地基，可编译为小程序/App/鸿蒙；七端共用一套前端。
- **决策**：Taro 4（React）。其编译器原生支持 H5 / 微信小程序 / React Native(App) / OpenHarmony(鸿蒙)，最贴合「一套代码多端」；Win/Mac 后续用 Tauri/Electron 包装 Web 产物。
- **备选**：uni-app(Vue)、Flutter（Dart 生态与 PRD 的 Python 后端/JS 工具箱协同弱）、纯 React+Vite（多端需自行桥接）。
- **影响**：跨端差异必须收敛到 `frontend/src/utils/platform.ts` 适配层，禁止页面内写死平台逻辑。

## ADR-002 后端采用 Python 3.11 + FastAPI
- **背景**：PRD 明确 Python 生态（Pillow/pypdf/python-qrcode/libvips），需异步 + AI 调用 + OpenAPI 文档。
- **决策**：FastAPI + SQLAlchemy 2(async) + Pydantic v2。
- **影响**：业务逻辑集中在 `backend/app`，七端不得重复实现算法。

## ADR-003 数据：PostgreSQL + Redis + S3 兼容对象存储
- **决策**：PostgreSQL（关系/状态机）、Redis（缓存+会话+队列 Broker）、S3 兼容存储（MinIO 本地 / 云 OSS 生产）。
- **影响**：启动包文件存对象存储并永久保存（M4-05），多端下载。

## ADR-004 异步生成：消息队列（RQ / Celery）
- **决策**：启动包(D01–D10) 生成入 Redis-backed 队列，前端轮询真实进度（M4-01/M4-02）。
- **影响**：`app/queue/worker.py` 消费 `package.generate`；worker 可独立扩容。

## ADR-005 依赖协议白名单（MIT/Apache/BSD/LGPL，禁 GPL/AGPL）
- **决策**：仅引入白名单协议依赖；办公文件生成锁定 Pillow/pypdf/python-qrcode/libvips。
- **红线**：禁用 PyMuPDF、itext7、pngquant 等 AGPL/GPL 库；CI 加入许可证扫描。
- **影响**：引入新依赖须在 `requirements.txt` 备注协议。

## ADR-006 错误必须中文化
- **决策**：所有异常经 `backend/app/core/errors.py` 归一为中文 `message` + 重试建议，禁止英文报错或裸错误码直出前端。
