"""生意诊断 - 负责人 A - 对应 m2_diagnose
路由前缀: /api/diagnose
需求点: 见 docs/api-contract.md
"""
from fastapi import APIRouter

router = APIRouter(prefix='/api/diagnose', tags=['diagnose'])

# TODO: 在此实现本模块接口，业务逻辑放入 app/services/diagnose.py
