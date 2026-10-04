"""消息与提醒 - 负责人 A - 对应 m9_notify
路由前缀: /api/notify
需求点: 见 docs/api-contract.md
"""
from fastapi import APIRouter

router = APIRouter(prefix='/api/notify', tags=['notify'])

# TODO: 在此实现本模块接口，业务逻辑放入 app/services/notify.py
