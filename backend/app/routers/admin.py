"""运营管理后台 - 负责人 B+D - 对应 m11_admin
路由前缀: /api/admin
需求点: 见 docs/api-contract.md
"""
from fastapi import APIRouter

router = APIRouter(prefix='/api/admin', tags=['admin'])

# TODO: 在此实现本模块接口，业务逻辑放入 app/services/admin.py
