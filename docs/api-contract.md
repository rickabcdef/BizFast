# 接口契约 · BizFast

## 1. 通用规范

- 基址：`https://<host>/api`
- 协议：REST + JSON；生成类长任务用「创建→轮询进度」模式。
- 鉴权：`Authorization: Bearer <JWT>`；游客可访问诊断/商机/工具免登录接口。
- 时间：ISO-8601（UTC，带 Z）。
- 文件命名：`生意快启_交付物名称_生成日期`（如 `生意快启_可行性评分卡_20261004.pdf`）。
- 进度真实不造假（M2-02 / M4-02）。

### 1.0 游客态约定（M1-07：不强制登录）

游客可免登录走完「诊断 → 商机 → 付费下单 → 查单 → 消息」全链路，身份靠 `X-Guest-Token` 维持：

- 客户端首次请求**不传**该头；服务端生成一个 token，并在**每个响应头**回写 `X-Guest-Token`。
- 客户端必须把该值**持久化**（本地存储），此后所有请求都带上 `X-Guest-Token: <token>`。
- CORS 已 `expose_headers: X-Guest-Token, X-Request-Id`，浏览器可直接读到。
- **不回传的后果**：每次请求都会被当成新游客，订单 / 收藏 / 消息全部查不到（联调必踩）。
- 登录后携带 `Authorization: Bearer <JWT>` 时以用户身份为准，`owner_key` 由 `guest:<token>` 切换为 `user:<id>`。
- 参考实现：前端 `frontend/src/services/api.ts`（`bf_guest_token`），后端 `backend/app/main.py` + `core/context.py`。

### 1.1 统一响应
```json
{ "code": 0, "message": "ok", "data": { }, "request_id": "..." }
```
- `code === 0` 成功；非 0 为业务错误，前端展示 `message`（中文）。

### 1.2 错误码（中文提示，禁止英文/裸码直出）

| code | message（示例） | 场景 |
|---|---|---|
| 0 | ok | 成功 |
| 40001 | 请输入启动资金、每日时间和所在城市 | 参数缺失 |
| 40002 | 当前城市暂不支持，请手动选择 | 城市越界 |
| 40101 | 登录已过期，请重新登录 | Token 失效 |
| 40301 | 该内容仅付费用户可生成 | 权益不足 |
| 40401 | 未找到对应的生意启动包 | 资源不存在 |
| 40901 | 订单正在生成中，请稍候 | 重复创建 |
| 42901 | 操作过于频繁，请稍后再试 | 限流 |
| 50001 | 服务开小差了，请重试 | 内部错误 |
| 50002 | AI 服务暂时不可用，已切换备用模型 | AI 降级 |
| 60001 | 支付未成功，请重新支付 | 支付失败 |

> 所有异常必须经 `backend/app/core/errors.py` 转换为中文 `message` + 重试建议。

## 2. 端点清单（按模块）

### M1 首屏（D）
- `GET /api/home/config` 返回资金/时间档位、城市枚举版本号。

### M2 诊断（A）
- `POST /api/diagnose` body:{capital, dailyHours, city} → {taskId}
- `GET /api/diagnose/{taskId}/progress` → {stage, percent, message}
- `GET /api/diagnose/{taskId}/result` → {tags, heatmapUrl, cached:bool}
- `GET /api/diagnose/heatmap/{id}` 下载/预览热度图。

### M3 商机匹配（A）
- `GET /api/match?taskId=` → {opportunities:[{id, title, fiveElements, cases, risks}]}
- `GET /api/match/{id}` 详情 ≤1.5s。
- `POST /api/match/{id}/favorite` 收藏（P1）。
- 第 4 个锁定商机 → 触发 `M5` 付费弹窗。

### M4 启动包生成（B）
- `POST /api/package/create` body:{orderId?, matchId?} → 需先完成支付 → {orderId}（幂等：重复请求返回 40901 但可继续轮询）
- `GET /api/package/{orderId}/progress` → {stage, percent, done, total, currentItem, retryCount, status}（真实进度，percent=done/total×100）
- `GET /api/package/{orderId}` → {items:[D01..D10 元数据], zipUrl, status, retryCount}
- `GET /api/package/{orderId}/item/{code}` 单件下载/预览（预览不产生额外费用）。
- `GET /api/package/{orderId}/zip` 打包 ZIP 下载（包内中文命名）。
- `POST /api/package/{orderId}/regenerate`（P1，限次：会员无限次 / 单次购买 1 次）。
- `GET /api/packages` 我的启动包列表（云端永久保存，M4-05 / M10-01 共用，按时间倒序）。

### M5 付费与订单（A）
- `POST /api/payment/create` body:{plan:'single|month|year', platform, matchId} → {orderId, payParams}
- `POST /api/payment/callback/{channel}` 渠道回调（微信/支付宝/Apple/华为）。
- `GET /api/payment/order/{orderId}` 主动查单兜底（M5-06）。
- `POST /api/payment/refund` 7 天无理由退款 ≤24h 到账。

### M6 工具箱（C，永久免费）
- `POST /api/tools/image/compress` · `POST /api/tools/pdf/merge` · `POST /api/tools/qrcode` · `POST /api/tools/copywriter`

### M7 小游戏（C）
- 纯前端 Canvas，无后端依赖（如需计分再补 `games` 服务）。

### M8 分享（D）
- `POST /api/share/card` 生成成果卡片（P0）。
- `GET /api/share/{id}` 卡片数据；`POST /api/share/track` 数据回收（P1）。

### M9 消息（A）
- `GET /api/notify/subscribe` · 服务通知/Push/桌面通知配置（PRD 仅标题，待设计）。

### M10 个人中心（D）
- `POST /api/auth/login`(手机号/验证码) · `POST /api/auth/wechat`(unionid) · `GET /api/user/me` · `GET /api/user/orders` · `POST /api/user/logout` · `DELETE /api/user/account`(注销，15 日清隐私)。

### M11 运营后台（B+D，内部）
- 登录：`POST /api/admin/login` body:{username, password} → {token, name, role:'admin|operator|support'}（密钥走环境变量，不进代码库）
- 数据看板：`GET /api/admin/dashboard` → {kpis:{diagnoseCount, payCount, revenueYuan, refundRate, conversionRate, packageDoneRate, avgOrderYuan}, trend:[{date, orders, revenue}], refreshAt}（数据延迟 ≤ 5 分钟）
- 用户管理：`GET /api/admin/users?page=&pageSize=&keyword=&memberStatus=` → {items, total, page, pageSize}；`GET /api/admin/users/{id}` → {user, consumption}
- 订单管理：`GET /api/admin/orders?page=&pageSize=&status=&keyword=`；`POST /api/admin/orders/{id}/refund` body:{action:'approve|reject', reason}
- 商机库管理（P0）：`GET /api/admin/opportunities?page=&pageSize=&status=&keyword=`；`POST /api/admin/opportunities/import` body:{items[]}；`POST /api/admin/opportunities/{id}/review` body:{action:'approve|reject', reason}
- 提示词配置：`GET /api/admin/prompts`；`PUT /api/admin/prompts/{key}` body:{content, model}（改后无需发版生效）
- 内容审核：`GET /api/admin/reviews?page=&pageSize=&status=&keyword=`；`POST /api/admin/reviews/{id}` body:{action:'pass|reject', reason}
- 权限管理：`GET /api/admin/roles`；`PUT /api/admin/roles/{role}` body:{perms[]}（操作记录操作人）
- 审计日志：`GET /api/admin/audit-logs?page=&pageSize=&operator=&action=`（保留 ≥ 180 天）
- 分享转化（D）：`GET /api/admin/share/stats` · `GET /api/admin/users` · `GET /api/admin/orders`。

## 3. 订单状态机（M5-05）
```
待支付 → 已支付 → 生成中 → 已交付
   │         │         │
   └─────────┴──→ 已关闭（超时/取消）
已支付/生成中/已交付 → 已退款（7天无理由）
```
每态带 `timestamp`。支付回调 + 定时主动查单双保险防漏单。

## 4. 角色与权益
游客 / 注册用户 / 单次(9.9) / 月度(39) / 年度(199) / 运营管理员。多端权益互通（同账号任意端一致）。
