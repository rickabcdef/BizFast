# infra/ · 基础设施

本地一键起全部依赖：

```bash
cd infra
cp .env.example .env
docker compose up -d
```

启动后：
- 前端(H5)：http://localhost
- 后端 API 文档：http://localhost:8000/docs
- PostgreSQL：localhost:5432
- Redis：localhost:6379
- MinIO 控制台：http://localhost:9001 （桶 `bizfast`）

## 文件
- `docker-compose.yml` —— 编排 postgres / redis / minio / backend / frontend
- `Dockerfile.backend` —— Python 3.11 + libvips，启动 FastAPI
- `Dockerfile.frontend` —— Node 构建 H5 产物 + nginx 托管
- `nginx.conf` —— SPA 兜底 + `/api` 反代后端 + `/files` 反代对象存储

## 生产建议
- 数据库 / 对象存储改用托管服务（云 RDS / 云 OSS），移除 expose 端口。
- backend 与 queue worker 分开部署、独立扩容。
- 前端静态产物走 CDN。
