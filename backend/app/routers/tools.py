"""工具箱 - 负责人 C - 对应 m6_tools
路由前缀: /api/tools
需求点: 见 docs/api-contract.md
"""
from fastapi import APIRouter

router = APIRouter(prefix='/api/tools', tags=['tools'])

# TODO: 在此实现本模块接口，业务逻辑放入 app/services/tools.py
