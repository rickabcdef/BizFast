# m4_delivery 启动包生成与交付（P0）

负责人：研发 B · 状态：网页端已完成（后端接口见 docs/api-contract.md 第 4 章）

## 页面状态
- **P07 生成进度页**：M4-01 异步生成入队；M4-02 真实进度「已完成 x/10」+ 正在生成的文件名
  （进度条蓝紫渐变 + 流光；进度值来自后端，前端不造假）；M2-03 等待小游戏入口气泡
  （导航到 m7_games，小游戏不阻塞后台任务，退出后回到本页）；M4-08 失败自动重试 2 次，
  仍失败全额退款并如实告知。
- **P08 启动包交付页**：M4-03 打包 ZIP 一键下载（包内中文命名）；M4-04 单件下载 +
  在线预览 PDF/图片（预览不产生额外费用）；M4-05 云端永久保存（无订单时展示
  「我的启动包」列表，换端登录可重新下载）；M4-06 重新生成（会员免费 / 单次 1 次，
  规则界面明示，确认后进入重新生成流程）。

## 参数
- `?orderId=xxx`：进入指定订单的生成/交付流程；未传时展示「我的启动包」云端列表。
- `?matchId=xxx`：可选，创建生成任务时携带。

## 衔接
- 支付成功（m5_pay）→ 1.5s 后 `redirectTo` 本页（M4-01 入口，负责人 B 补齐）。
- 我的启动包（m10_user）单件下载 / 打包下载 → `navigateTo` 本页承接。

## 调试
- 开发模式（USE_MOCK=on）下使用 Mock 数据：进度每 2s 轮询、约 6s 完成 10 件；
  下载/预览使用可实际打开的占位文件（data URL），离线可演示。
- 生产模式（USE_MOCK=off）直连真实后端：`POST /api/package/create`、
  `GET /api/package/{orderId}/progress`、`GET /api/package/{orderId}`、
  `GET /api/package/{orderId}/item/{code}`、`GET /api/package/{orderId}/zip`、
  `POST /api/package/{orderId}/regenerate`、`GET /api/packages`。
