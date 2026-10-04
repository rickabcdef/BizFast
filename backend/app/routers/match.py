"""商机匹配 - 负责人 A - 对应 m3_match
路由前缀: /api/match
需求点: 见 docs/api-contract.md
"""
from fastapi import APIRouter

router = APIRouter(prefix='/api/match', tags=['match'])

# TODO: 在此实现本模块接口，业务逻辑放入 app/services/match.py
