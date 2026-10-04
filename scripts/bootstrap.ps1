# BizFast 本地引导脚本（Windows / PowerShell）
# 用法：powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

Write-Host '==> 启动基础设施（PostgreSQL / Redis / MinIO）' -ForegroundColor Cyan
Set-Location "$root\infra"
docker compose up -d

Write-Host '==> 初始化后端虚拟环境并安装依赖' -ForegroundColor Cyan
Set-Location "$root\backend"
if (-not (Test-Path .venv)) { python -m venv .venv }
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host '已生成 backend/.env，请填写密钥' }

Write-Host '==> 安装前端依赖' -ForegroundColor Cyan
Set-Location "$root\frontend"
if (-not (Test-Path node_modules)) { npm install }

Write-Host '==> 完成。开发：' -ForegroundColor Green
Write-Host '   后端:  cd backend && uvicorn app.main:app --reload'
Write-Host '   前端:  cd frontend && npm run dev:h5'
