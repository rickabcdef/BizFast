"""付费与订单 - 负责人 A - 对应 m5_pay
路由前缀: /api/payment
需求点: 见 docs/api-contract.md
"""
from fastapi import APIRouter

router = APIRouter(prefix='/api/payment', tags=['payment'])

# TODO: 在此实现本模块接口，业务逻辑放入 app/services/payment.py
