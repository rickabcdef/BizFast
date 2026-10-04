"""账号与鉴权 - 负责人 D - 对应 m10_user
路由前缀: /api/auth
需求点: 见 docs/api-contract.md
"""
from fastapi import APIRouter

router = APIRouter(prefix='/api/auth', tags=['auth'])

# TODO: 在此实现本模块接口，业务逻辑放入 app/services/auth.py
