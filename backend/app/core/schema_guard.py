"""SQLite 轻量自愈迁移：为既有库补齐模型新增的字段。

背景（真实踩过的坑）
------------------
本项目本地开发用 SQLite + ``Base.metadata.create_all``。``create_all`` 只会
**建缺失的表**，不会给已存在的表**补列**。于是任何一位同学在旧库上拉取新代码后，
只要模型新增了字段（V5.0 就新增了 ``users.renew_stage`` / ``users.city`` /
``users.capital_band`` / ``users.daily_hours_band`` / ``users.experience``），
启动后相关接口就会抛 ``sqlite3.OperationalError: no such column``。

表现极具误导性：前台首屏依赖 ``POST /api/auth/guest`` 建游客会话，一旦它 500，
用户看到的是「服务开小差了，请重试」——**整个产品都打不开**，
但报错信息完全指不到「库里少了一列」。

所以这里在 ``create_all`` 之后做一次幂等的「补列」：比对模型与实际表结构，
对缺失的列执行 ``ALTER TABLE ... ADD COLUMN``，并尽量按其默认值回填。

适用范围
--------
仅用于 SQLite（本地开发 / 演示）。生产 PostgreSQL 请走 Alembic 正式迁移，
本模块刻意不处理非 SQLite 方言，避免掩盖真实的迁移缺失。
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.dialects import sqlite as sqlite_dialect
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.database import Base

logger = logging.getLogger(__name__)

_DIALECT = sqlite_dialect.dialect()


def _sql_literal(value: object) -> str | None:
    """把 Python 标量默认值转成 SQL 字面量；无法静态表达时返回 None。"""
    if value is None or isinstance(value, datetime):
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _column_default_literal(column) -> str | None:
    """取列的静态默认值（仅标量默认；callable 默认无法在 DDL 里表达）。"""
    default = getattr(column, "default", None)
    if default is not None and getattr(default, "is_scalar", False):
        return _sql_literal(default.arg)
    return None


async def ensure_columns(engine: AsyncEngine) -> list[str]:
    """为既有表补齐模型新增的列，返回被补齐的 ``表.列`` 列表（幂等）。"""
    added: list[str] = []
    async with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            rows = (await conn.execute(text(f'PRAGMA table_info("{table.name}")'))).all()
            if not rows:  # 表还不存在（create_all 未覆盖到），交给 create_all
                continue
            existing = {row[1] for row in rows}
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(dialect=_DIALECT)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
                literal = _column_default_literal(column)
                if literal is not None:
                    ddl += f" DEFAULT {literal}"
                # SQLite 不允许 ADD COLUMN NOT NULL 且无默认值；
                # 这里一律按可空列添加（模型侧仍由 SQLAlchemy 默认值保证写入有值）。
                await conn.execute(text(ddl))
                added.append(f"{table.name}.{column.name}")
    if added:
        logger.warning(
            "检测到 %d 个字段缺失，已自动补齐（建议后续补正式迁移）：%s",
            len(added),
            ", ".join(added),
        )
    return added
