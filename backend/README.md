# backend/ · BizFast 后端（Python + FastAPI）

业务逻辑、算法、文件生成、支付状态机**唯一所在地**。七端共用同一套 API。

## 目录
```
app/
  main.py            # 入口：挂载路由、全局异常处理（中文）、CORS、健康检查
  core/              # config / database / security / errors(中文错误码) / logging
  models/            # SQLAlchemy 实体（见 docs/data-model.md）
  schemas/           # Pydantic 请求/响应
  routers/           # 各模块 API：auth, diagnose, match, package, payment, tools, games, share, notify, admin
  services/          # 各模块业务逻辑（供 routers 调用）
  ai/                # 大模型客户端 + 降级策略
  queue/             # 启动包异步生成消费者（RQ）
  office/            # D01–D10 十件交付物生成器（Pillow/pypdf/qrcode）
  storage/           # 对象存储适配（S3 兼容）
```

## 开发
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # 填写 DB / Redis / 对象存储 / 大模型 Key
uvicorn app.main:app --reload  # http://127.0.0.1:8000/docs
```

## 约定
- 所有异常经 `core/errors.py` 归一为中文 `message` + 重试建议，**禁止英文报错或裸错误码直出**（ADR-006）。
- 业务逻辑只在 `services/`，`routers/` 只做参数校验与编排。
- 改接口须同步更新 `docs/api-contract.md` 与 `frontend/src/types/index.ts`。
