"""解压小游戏 - 负责人 C - 对应 m7_games
路由前缀: /api/games
需求点: 见 docs/api-contract.md
"""
from fastapi import APIRouter

router = APIRouter(prefix='/api/games', tags=['games'])

# TODO: 在此实现本模块接口，业务逻辑放入 app/services/games.py
