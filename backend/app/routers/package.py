"""启动包生成 - 负责人 B - 对应 m4_delivery
路由前缀: /api/package
需求点: 见 docs/api-contract.md
"""
from fastapi import APIRouter

router = APIRouter(prefix='/api/package', tags=['package'])

# TODO: 在此实现本模块接口，业务逻辑放入 app/services/package.py
