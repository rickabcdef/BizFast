# 数据模型 · BizFast

> 关系库：PostgreSQL。缓存：Redis。文件：对象存储。以下为实体草案，落地以 `backend/app/models/` 为准。

## 实体关系
```
User 1—* Order 1—1 Package(启动包) 1—* DeliverableFile(D01..D10)
User 1—* Favorite(M3 收藏)      User 1—* ShareCard(M8)
User 1—* Session/JWT            User 1—* Coupon/Invite(邀请码 P1)
```

## 核心实体

### User（账号）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid PK | |
| phone | string? | 手机号（注册用户） |
| unionid | string? | 微信 unionid（跨端同账号） |
| guest_token | string? | 游客标识 |
| role | enum | guest/user/admin |
| plan | enum | none/single/month/year |
| plan_expire_at | timestamptz? | 会员有效期 |
| created_at / updated_at | timestamptz | |

### Order（订单状态机，M5-05）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid PK | |
| user_id | fk | |
| plan | enum | single/month/year |
| amount | int（分） | 9.9/39/199 → 分 |
| platform | enum | web/weapp/android/ios/harmony/win/mac |
| channel | enum | wechat/alipay/apple/huawei |
| status | enum | pending/paid/generating/delivered/refunded/closed |
| paid_at / delivered_at / refunded_at | timestamptz? | 每态时间戳 |
| match_id | string? | 关联锁定商机 |

### Package（启动包，M4）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid PK | |
| order_id | fk | |
| user_id | fk | |
| status | enum | generating/delivered/failed |
| zip_url | string? | 对象存储 ZIP |
| retry_count | int | ≤2（M4-08） |

### DeliverableFile（D01–D10）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid PK | |
| package_id | fk | |
| code | enum | D01..D10 |
| name | string | 交付物名称 |
| file_type | enum | pdf/excel/word/png/svg/txt/zip |
| url | string | 对象存储地址 |
| created_at | timestamptz | |

### DiagnosisTask（诊断，M2）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid PK | |
| user_id? | fk | 游客可为空 |
| capital / daily_hours / city | 条件 | 三要素 |
| tags | jsonb | 打标结果 |
| heatmap_url | string? | 热度图 |
| cache_key | string | 条件哈希，24h 缓存（M2-06） |
| created_at | timestamptz | |

### ShareCard / Favorite / Coupon
- ShareCard：成果卡片（M8），含脱敏后数据。
- Favorite：商机收藏对比（M3-06，P1）。
- Coupon/Invite：优惠券/邀请码（M5-09，P1）。

## 缓存键（Redis）
- `diag:{hash}` → 诊断结果，TTL 24h（M2-06）。
- `hot:biz` → 热点商机数据。
- `sess:{jti}` → JWT 会话。

## 合规保留
- 交易记录依法保留；用户注销后 15 日内清除隐私字段，交易记录除外。
