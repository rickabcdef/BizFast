# AGENTS.md · AI 开发团队守则（BizFast / 生意快启）

本仓库由 **4 名 AI 程序员（A / B / C / D）** 协作开发。本文件是所有开发 Agent 的最高行为准则。

## 1. 角色与模块归属

| 你 | 负责模块 | 目录（前端 / 后端） |
|---|---|---|
| **A** | M2 诊断 / M3 匹配 / M5 付费 / M9 消息 | frontend/src/pages/m2_*, m3_*, m5_*, m9_* · backend/app/{routers,services}/diagnose,match,payment,notify |
| **B** | M4 启动包生成 / M11 运营后台 | frontend/src/pages/m4_*, m11_* · backend/app/{routers,services}/package,admin + app/office + app/queue |
| **C** | M6 工具箱 / M7 解压小游戏 | frontend/src/pages/m6_*, m7_* + canvas-games · backend/app/{routers,services}/tools,games |
| **D** | M1 首屏 / M8 分享 / M10 个人中心 | frontend/src/pages/m1_*, m8_*, m10_* · backend/app/{routers,services}/auth,share |

> 认领前先读 [`docs/module-ownership.md`](docs/module-ownership.md) 与 [`docs/api-contract.md`](docs/api-contract.md)。

## 2. 架构铁律

- **业务逻辑只在后端**：算法、计算、文件生成、支付状态机不得在前端重复实现。前端只做采集、展示、轮询进度。
- **一套前端代码多端**：网页版是地基，不得为某端写死逻辑；跨端差异走 `frontend/src/utils/platform.ts` 适配层。
- **进度真实不造假**：生成/诊断进度必须来自后端真实状态（M2-02、M4-02）。
- **异步生成**：启动包生成入队列，前端轮询（M4-01）。

## 3. 编码规范

- 错误提示**必须中文 + 重试按钮**，禁止英文报错或裸错误码（见 `backend/app/core/errors.py`）。
- 免费层：不限次、无水印、无广告。
- 命名：模块 `M1`–`M11`，功能点 `Mx-y`（如 M1-03）；交付物 `D01`–`D10`；价格档 单次9.9 / 月39 / 年199。
- 交付物文件统一命名：`生意快启_交付物名称_生成日期`。
- 小游戏美术 100% 代码绘制；音效 CC0 / 自录。

## 4. 依赖红线

- 允许：MIT / Apache-2.0 / BSD / LGPL（动态链接）。
- **禁止**：GPL / AGPL（含 PyMuPDF、itext7、pngquant）。
- 办公文件：**Pillow / pypdf / python-qrcode / libvips** 已锁定。

## 5. 提交与协作

- 基于 `pm` 拉 `dev/<module>`，PR 合回 `pm`。
- 提交信息：`[模块] 动作：说明`，如 `[M4] feat: 新增 D01 可行性评分卡生成`。
- **绝不**提交 `.env`、密钥、构建产物、大体积 zip/png。
- 改接口先更新 `docs/api-contract.md` 与 `frontend/src/types/index.ts`。

## 6. 验证关纪律

- 网页版上线即开始收钱；付费转化率 < 3% 不扩端。
- P0 模块（M1/M2/M3/M4/M5/M10 相关）为第 1–4 周必须上线项。
