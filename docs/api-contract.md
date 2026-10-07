# 接口契约 · BizFast

> **模块编号已按 V5.0（现金流导向版）更新。** V2.2 → V5.0 映射：
> 用户与账号 = **M0**（新）｜商机诊断与匹配 = **M1**（原 M2+M3）｜支付与订单 = **M2**（原 M5）｜启动包生成 = **M3**（原 M4）｜
> 运营后台 = **M4**（原 M11）｜裂变传播与分享 = **M5**（原 M8）｜AI 教练 M6 / 多模态 M7 / 工具箱 M8 / 小游戏 M9 / 个人中心 M10 / 生态 M11（均为 P1）。
> **原 M9「消息与提醒」模块在 V5.0 已删除**，只保留「会员到期提醒」（收进第 8 章自动化清单）。

## 1. 通用规范

- 基址：`https://<host>/api`
- 协议：REST + JSON；生成类长任务用「创建→轮询进度」模式。
- 鉴权：`Authorization: Bearer <JWT>`；游客可访问诊断/商机/工具免登录接口。
- 时间：ISO-8601（UTC，带 Z）。
- 文件命名：`生意快启_交付物名称_生成日期`（如 `生意快启_可行性评分卡_20261004.pdf`）。
- 进度真实不造假；「今日限制」等稀缺数字同样必须来自真实订单（V5.0 第 2.3 节）。

### 1.0 游客态约定（不强制登录：未登录可完成免费诊断）

游客可免登录走完「诊断 → 商机 → 付费下单 → 查单 → 交付」全链路，身份靠 `X-Guest-Token` 维持：

- 客户端首次请求**不传**该头；服务端生成一个 token，并在**每个响应头**回写 `X-Guest-Token`。
- 客户端必须把该值**持久化**（本地存储），此后所有请求都带上 `X-Guest-Token: <token>`。
- CORS 已 `expose_headers: X-Guest-Token, X-Request-Id`，浏览器可直接读到。
- **不回传的后果**：每次请求都会被当成新游客，订单 / 收藏 / 交付包全部查不到（联调必踩）。
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
| 40901 | 退款申请已提交，正在人工审核，请耐心等待 | 重复创建 / 重复提交 |
| 42901 | 操作过于频繁，请稍后再试 | 限流 |
| 50001 | 服务开小差了，请重试 | 内部错误 |
| 50002 | AI 服务暂时不可用，已切换备用模型 | AI 降级 |
| 60001 | 支付未成功，请重新支付 | 支付失败 |

> 所有异常必须经 `backend/app/core/errors.py` 转换为中文 `message` + 重试建议。

## 2. 端点清单（按模块）

### M0 用户与账号（A）
- `POST /api/auth/guest` 创建游客账号（也可由 `X-Guest-Token` 隐式创建）。
- `POST /api/auth/sms/send` 发送短信验证码；`POST /api/auth/sms/login` 手机号+验证码登录。
- `POST /api/auth/login`（契约路径，手机号+验证码）· `POST /api/auth/wechat`（unionid 登录）。
- `POST /api/auth/refresh` 刷新 access_token。
- `GET /api/user/me` → 账号 + 会员 + **M0-02 画像**（city/capitalBand/dailyHoursBand/experience）
  + **M0-03 额度**（purchasedCount/usedPackageCount/quotaTotal/quotaRemaining/quotaUnlimited）。
- `POST /api/user/profile` body:{city?, capitalBand?, dailyHoursBand?, experience?} 更新画像
  （≤6 字段、全部单选/滑块、不强制真实姓名；城市与诊断链路同一套归一化，「上海市」落库为「上海」）。
- `GET /api/user/orders` · `POST /api/user/logout` · `DELETE /api/user/account`（注销，15 日清隐私）。
- M0-02 采集时机：注册 / 登录时自动把**首屏已选过的**条件回写画像，不重复问用户（只填空字段，不覆盖手动修改）。
- M0-03 到期提醒：到期前 **3 天 / 1 天各提醒一次**，不要求用户已开启自动续费（`user.renew_stage` 去重）。
- **M0-04 邀请关系绑定（V5.0）**：分享链接形如 `https://<host>/?inviter=BF-7Q2X9`。
  - 落地即暂存：前端冷启动读取 `inviter` 参数落本地存储（被邀请人可能逛很久才登录，不落地就会丢单）；
  - 登录自动携带：`POST /api/auth/login` 与 `POST /api/auth/wechat` 的 `inviterCode` 字段由请求层自动补齐，
    两条登录路径都会调用 `share_service.bind_invite`，**关系首次绑定后不可修改**（幂等，已绑定直接返回）；
  - 绑定成功后前端清除暂存码，避免污染其它账号登录；
  - 后台可查任意用户的邀请来源（见 M4 用户管理 `source` / `inviterPhone`）。

### M1 商机诊断（A）
- `POST /api/diagnose` body:{capital, dailyHours, city, extra?} → {taskId}
  - `extra`（M2-07 补充问答，可整体跳过）：`{experience:'none|some|pro', mode:'offline|online|both', priority:'cost|profit|balance'}`
  - **注意**：城市必须是后端城市库认得的名字（含 `中国香港` / `中国澳门` / `中国台湾`），否则 40002。
- `GET /api/diagnose/{taskId}/progress` → {stage, percent, message}（真实进度，不造假）
- `GET /api/diagnose/{taskId}/result` → {tags, heatmapUrl, cached:bool}
- `GET /api/diagnose/heatmap/{taskId}` 下载/预览热度图（≤30 秒生成）。
- `GET /api/diagnose/{taskId}/share` · `GET /api/diagnose/share-card/{taskId}` 分享卡片数据 / PNG。

### M2 支付与订单（A）
- `GET /api/payment/plans` 三档（V5.0）：开业礼包 **29.9** 单次 / AI 合伙人月卡 **99** / 创业陪跑年卡 **599**。
- `GET /api/payment/addons` 增值加购包（按项计价，不并入标准套餐）。
- `POST /api/payment/create` body:{plan:'single|month|year', platform, matchId} → {orderId, payParams}
- `POST /api/payment/callback/{channel}` 渠道回调（微信/支付宝/Apple/华为），幂等。
- `POST /api/payment/mock/channel-paid` **仅本地模拟**（`PAYMENT_MOCK=true` 时存在，生产 404）：
  把渠道侧标记为「已扣款」但不回写本地订单，用于验收「回调丢失 → 主动查单补单」。
- `GET /api/payment/order/{orderId}` 主动查单兜底（M2-01）+ 退款可走路径提示：
  `downloaded` / `refundPath('self'|'review')` / `refundNotice` / `refundReviewing`。
  - 绝不只靠回调判状态：待支付订单会**主动向渠道查单**，渠道已扣款则立即补单（防漏单，用户不会付了钱拿不到货）；
    查单失败一律 fail-safe（返回 `unknown`，交人工核对），绝不擅自发货。
- `POST /api/payment/refund` **M2-05 退款机制（V5.0）**：
  - 交付物**未下载** → 自助全额退款即时生效（`review=auto_approved`），同步回收会员权益；
  - 交付物**已下载** → 不即时退款，转人工审核（`review=pending`、`reviewRequired=true`），
    后台「订单管理」一键同意 / 驳回；审核通过后同样回收权益。
  - 幂等：同一订单重复提交返回 40901（避免刷审核队列）。
- `POST /api/payment/coupon/validate` · `GET /api/payment/coupons`（不可叠加、规则明示）。
- `GET|PUT /api/payment/subscription` · `POST /api/payment/subscription/cancel`（自动续费，取消 ≤3 步）。
- `GET /api/payment/risk` 查询本人风控状态（透明告知）。

### M1 商机匹配（A）
- `GET /api/match?taskId=` → {free:[3 个免费商机], locked:{第 4 个锁定商机}}
- `GET /api/match/{id}` 详情 ≤1.5s，含 `today`（V5.0 第 2.3 节「今日限制」）。
- `GET /api/match/{id}/today` → {todayTaken, dailyLimit, todayRemaining, soldOut, notice}
  计数口径 = **当天真实支付成功的该商机订单数**（`opportunity_daily_limit` 默认 50），数字必须真实，绝不造假。
- `POST /api/match/{id}/favorite` 收藏 / 取消收藏 · `GET /api/match/favorites` 我的收藏
- `GET /api/match/{id}/entitled` 是否已解锁该商机完整方案。

### M3 启动包生成（B）
- `POST /api/package/create` body:{orderId?, matchId?} → 需先完成支付 → {orderId}（幂等：重复请求返回 40901 但可继续轮询）
- `GET /api/package/{orderId}/progress` → {stage, percent, done, total, currentItem, retryCount, status}（真实进度，percent=done/total×100；生成失败自动重试 2 次，仍失败 status=failed 并全额退款）
- `GET /api/package/{orderId}` → {items:[D01..D10 元数据], zipUrl, status, retryCount}
  - 每件元数据：{code, name, fileType(主格式), url, formats:[{fileType, url}...]}；PRD 4.4.1 多格式交付物：D03/D06 = PDF+Word、D07 = Word+TXT、D08 = PNG+SVG、D09 = PDF+Excel，其余单格式。
- `GET /api/package/{orderId}/item/{code}?format=&dl=1` 单件下载/预览；`dl=1` 表示**真实下载**（M2-05 以此为「已下载」判定依据，决定能否自助退款），不带 `dl` 仅预览不计入。
- `GET /api/package/{orderId}/zip` 打包 ZIP 下载（无条件记为已下载）。
- `POST /api/package/{orderId}/regenerate`（P1，限次：会员无限次 / 单次购买 1 次）。
- `GET /api/packages` 我的启动包列表（云端永久保存，M3-05 / M10-01 共用，按时间倒序）。

### M8 工具箱（C，永久免费）
- `POST /api/tools/image/compress` · `POST /api/tools/pdf/merge` · `POST /api/tools/qrcode` · `POST /api/tools/copywriter`

### M9 小游戏（C）
- 纯前端 Canvas，无后端依赖（如需计分再补 `games` 服务）。

### M5 裂变传播与分享（C+D）
- `POST /api/share/card` 生成成果卡片（P0）。
- `GET /api/share/{id}` 卡片数据；`POST /api/share/track` 数据回收（P1）。
- `POST /api/share/talk-topic/track` 谈资卡转发埋点（V5.0 M5-04）。
- `POST /api/events/track` 转化漏斗埋点（V5.0 M4-07：visit / diagnose_start / pay_click / download）。
- `POST /api/notify/read` 等站内消息接口保留（**V5.0 已删除 M9 消息模块**，仅保留会员到期提醒与必要的订单/退款通知）。

### M10 个人中心（D）
- 账号/订单/权益相关端点见 **M0 用户与账号（A）** 与 `/api/user/*`；个人中心页面另含收藏商机、谈资历史、喜报素材。
- `GET /api/home/config` 首屏配置（资金/时间档位、城市枚举版本号，`city_list_version`）。

### M4 运营后台（B+D，内部）
- 登录：`POST /api/admin/auth/login` body:{username, password} → 第一步；`POST /api/admin/auth/verify-2fa`（TOTP 第二步验证）（密钥走环境变量，不进代码库）
- 数据看板：`GET /api/admin/dashboard` → {kpis:{diagnoseCount, payCount, revenueYuan, refundRate, conversionRate, packageDoneRate, avgOrderYuan}, trend:[{date, orders, revenue}], refreshAt}（数据延迟 ≤ 5 分钟）
- 用户管理：`GET /api/admin/users?page=&pageSize=&keyword=&memberStatus=&source=` → {items, total, page, pageSize}；`GET /api/admin/users/{id}` → {user, orders, packages}
  - V5.0 §10.2：列表与详情里的手机号**一律脱敏**（`138****5678`），不得明文直出。
  - **M0-04 来源渠道**：出参 `source` ∈ `邀请注册`｜埋点渠道值｜`自然流量`；邀请注册时附 `inviterPhone`（同样脱敏）。
    `source` 筛选参数**真实生效**（此前被接收却从不生效，属已修复的契约断裂）。
- 订单管理：`GET /api/admin/orders?page=&pageSize=&status=&keyword=&abnormal=&channel=`；`PUT /api/admin/orders/{orderId}/refund` body:{action:'approve|reject', reason}
  - 异常订单包含 `refund_review`（退款待审核）、`paid_no_delivery`（已支付未交付超 2 小时）、`callback_missing`（渠道回调缺失）三类，红色高亮；
    出参带 `downloaded` / `refundRequested` / `refundReason` / `abnormal` / `abnormalType` / `abnormalHandled`。
  - **M2-03 手动标记已处理**：`POST /api/admin/orders/{orderId}/resolve` body:{note?}
    写订单事件（可追溯处理人与时间）+ 关闭该订单的未读告警；标记后 `abnormal=false`、`abnormalHandled=true`，不再红色高亮。
- 商机库管理（P0）：`GET /api/admin/opportunities?page=&pageSize=&status=&keyword=`；`POST /api/admin/opportunities/import` body:{items[]}；`POST /api/admin/opportunities/{id}/review` body:{action:'approve|reject', reason}
- 提示词配置：`GET /api/admin/prompts`；`PUT /api/admin/prompts/{promptKey}` body:{content, model}（改后无需发版生效）
- 内容审核：`GET /api/admin/reviews?page=&pageSize=&status=&keyword=`；`POST /api/admin/reviews/{id}/action` body:{action:'pass|reject', reason}
- 权限管理：`GET /api/admin/roles`；`PUT /api/admin/roles/{role}` body:{perms[]}（操作记录操作人）
- 审计日志：`GET /api/admin/audit`（保留 ≥ 180 天）
- V5.0 后台三块看板：`GET /api/admin/cost-monitor`（AI 成本，超 25% 告警）、`GET /api/admin/funnel`（转化漏斗）、`GET /api/admin/growth`（裂变含 K 因子）。
- 运营自动化：`GET /api/admin/daily-reports` · `GET /api/admin/alerts` · `POST /api/admin/alerts/scan`（一键巡检）。
  - 告警类型：`paid_no_delivery`（已支付未交付超 2 小时）、`callback_missing`（渠道回调缺失，
    超过 `order_callback_missing_minutes` 默认 15 分钟；渠道已扣款则**自动补单**并降级为 warning 告警，
    查不到则 danger 交人工核对）、`duplicate_payment`（同用户窗口内 ≥2 笔已支付，疑似重复扣款需退款）、
    `cost_overrun`（AI 成本占收入比超 25%）。按 `fingerprint` 去重，不重复刷屏。
- 导出：`GET /api/admin/export/{exportType}`（users/orders/deliveries/events）。

## 3. 订单状态机（M2-03）

```
待支付 → 已支付 → 生成中 → 已交付
   │         │         │
   └─────────┴──→ 已关闭（超时/取消）
已支付/生成中/已交付 → 已退款
```

每态带 `timestamp`。**防漏单双保险**：渠道回调（`POST /api/payment/callback/{channel}`）
+ 主动查单（`GET /api/payment/order/{orderId}`，以及后台定时巡检 `POST /api/admin/alerts/scan`）。
回调丢失时，主动查单若发现渠道已扣款会**自动补单**（用户无感）；查不到则挂 `callback_missing` 告警交人工核对。

**退款分两条路（V5.0 M2-05）**：

```
未下载 ──→ 自助全额退款（即时生效）──→ 已退款 + 会员权益回收
已下载 ──→ 提交申请 → refund_review=pending ──→ 后台审核
                                    ├─ 同意 → 已退款 + 会员权益回收
                                    └─ 驳回 → 订单恢复原状态（可再次申请）
```

- 已下载判定依据：`order.downloaded_at`（由 `GET /api/package/{orderId}/item/{code}?dl=1` 或 ZIP 下载写入）。
- 权益回收：月卡/年卡直接置 `plan=none`；单次卡需确认无其它进行中订单后再回收。
- 超过 `refund_window_days`（默认 7 天）后不再受理自助退款，提示联系客服。

## 4. 角色与权益
游客 / 注册用户 / 开业礼包(29.9 单次) / AI 合伙人月卡(99) / 创业陪跑年卡(599) / 增值加购包(9.9–199/项) / 运营管理员。
月卡与年卡**不限次**生成启动包（`quotaUnlimited=true`）；单次礼包按「一单一次生成」计额度
（`purchasedCount` / `usedPackageCount` / `quotaRemaining`）。多端权益互通（同账号任意端一致）。
