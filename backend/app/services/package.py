"""启动包生成服务（M4）。

支付成功后异步生成 D01–D10 十件交付物，上传存储并打包 ZIP：
- D01 可行性评分卡 (PDF)
- D02 回本测算表 (Excel)
- D03 客户画像与获客清单 (PDF + Word)
- D04 供应商线索与询价话术 (PDF)
- D05 定价与开业活动 (PDF)
- D06 开店流程清单 (PDF + Word)
- D07 获客文案10条 (Word + TXT)
- D08 店名与物料 (PNG + SVG)
- D09 30天行动日历 (Excel + PDF)
- D10 风险清单与止损线 (PDF)

多格式映射的权威定义在 `app.office.DELIVERABLE_FORMATS`（PRD 4.4.1）。

约定：本模块是生成链路的**唯一实现**，`routers/package.py`（HTTP 触发）
与 `queue/worker.py`（RQ 触发）都调用这里，避免两份逻辑漂移。
"""
from __future__ import annotations

import asyncio
import io
import logging
import uuid
import zipfile
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DeliverableFile, DiagnosisTask, Order, Package
from app.office import AI_DELIVERABLES, DELIVERABLES, FILE_EXT, generate_formats
from app.services import ai_cost
from app.storage import get_storage

logger = logging.getLogger(__name__)

# 进程内「同一订单只跑一次生成」锁。
# inline 模式下 HTTP 触发与队列触发都在同一事件循环里，前端双 effect／重复点击
# 会并发入队两次；靠这把锁把第二次挡在门外，避免并发生成写出重复交付物。
_run_locks: dict[str, asyncio.Lock] = {}

# 生成失败自动重试次数（超出后全额退款，M4-08）
_MAX_RETRY = 2


def _run_lock(order_id: str) -> asyncio.Lock:
    lock = _run_locks.get(order_id)
    if lock is None:
        lock = asyncio.Lock()
        _run_locks[order_id] = lock
    return lock


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _capital_label(capital: int) -> str:
    if capital <= 10000:
        return "1万以下"
    elif capital <= 50000:
        return "1–5万"
    elif capital <= 200000:
        return "5–20万"
    return "20万以上"


async def build_context(db: AsyncSession, order: Order) -> dict:
    """构建交付物生成上下文：城市 / 资金 / 时间 / 目标商机。"""
    diag = (await db.execute(
        select(DiagnosisTask)
        .where(DiagnosisTask.user_id == order.user_id)
        .order_by(DiagnosisTask.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    capital = diag.capital if diag else 50000

    # 目标商机：优先取订单关联的 match_id，其次取诊断结果里的第一个，最后兜底
    # 走「有效视图」：后台运营的编辑 / 下架 / 新增对交付物同样生效（M4-04）
    from app.data import opp_library

    pool = opp_library.library()
    opp = pool[0] if pool else {}
    if order.match_id:
        for o in pool:
            if o.get("id") == order.match_id:
                opp = o
                break

    return {
        "order_id": order.id,
        "city": diag.city if diag else "上海",
        "capital": capital,
        "capital_label": _capital_label(capital),
        "daily_hours": diag.daily_hours if diag else 8,
        "opportunity": opp,
        "score": 85,
        "user_id": order.user_id,
    }


async def run_generation(order_id: str, user_id: str, force: bool = False) -> None:
    """生成端到端流程（在独立 DB 会话中执行，供后台任务调用）。

    并发安全（M4-01）：
    - 进程内：同一 order_id 用 asyncio 锁串行化，重复触发直接丢弃；
    - 数据库：packages.order_id 唯一约束，跨进程重复创建时容忍并复用已有行；
    - 幂等：已 delivered 且已有交付物时直接短路，不再重复生成。
    `force=True` 用于「重新生成」——跳过幂等短路，全量重做。

    失败自动重试 2 次；仍失败则全额退款（M4-08）。重试在这里的循环内完成，
    而不是在生成函数里递归调用自己——否则会被自己持有的锁挡住、静默不重试。
    """
    lock = _run_lock(order_id)
    if lock.locked():
        logger.info("启动包生成已在进行中，忽略重复触发：order_id=%s", order_id)
        return

    async with lock:
        attempt = 0
        while True:
            delivered = await _generation_once(order_id, user_id, force=force or attempt > 0)
            if delivered:
                return
            attempt += 1
            if attempt > _MAX_RETRY:
                await _mark_refunded(order_id)
                return
            logger.warning(
                "启动包生成失败，第 %s/%s 次重试：order_id=%s", attempt, _MAX_RETRY, order_id
            )


async def _has_items(db: AsyncSession, package_id: str) -> bool:
    row = (await db.execute(
        select(DeliverableFile.id).where(DeliverableFile.package_id == package_id).limit(1)
    )).first()
    return row is not None


async def _get_package_row(db: AsyncSession, order_id: str) -> Package | None:
    """取订单对应的启动包。用 first() 而非 scalar_one_or_none()：
    历史脏数据（唯一约束生效前产生的重复行）不应让接口 500。"""
    return (await db.execute(
        select(Package).where(Package.order_id == order_id).order_by(Package.created_at.asc())
    )).scalars().first()


async def _generation_once(order_id: str, user_id: str, force: bool) -> bool:
    """执行一次完整生成。返回 True 表示已交付，False 表示本轮失败（需上层重试）。"""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        order = await db.get(Order, order_id)
        if not order:
            logger.error("启动包生成失败：订单不存在 order_id=%s", order_id)
            return False

        existing = await _get_package_row(db, order_id)
        if (
            not force
            and existing is not None
            and existing.status == "delivered"
            and await _has_items(db, existing.id)
        ):
            logger.info("启动包已交付，跳过重复生成：order_id=%s pkg=%s", order_id, existing.id)
            return True

        # 复用已有的 Package（重试 / 重新生成 / 断点续做）或新建
        pkg = existing
        if pkg is None:
            pkg = Package(
                id=str(uuid.uuid4()),
                order_id=order_id,
                user_id=user_id,
                status="generating",
                retry_count=0,
            )
            db.add(pkg)
            try:
                await db.commit()
            except IntegrityError:
                # 跨进程并发（多 RQ worker）撞上 order_id 唯一约束：复用已落库的那一行
                await db.rollback()
                pkg = await _get_package_row(db, order_id)
                if pkg is None:
                    raise
                logger.info("启动包并发创建冲突，复用已有行：order_id=%s pkg=%s", order_id, pkg.id)
                if pkg.status == "delivered" and await _has_items(db, pkg.id):
                    logger.info("启动包已交付，跳过重复生成：order_id=%s", order_id)
                    return True
        else:
            pkg.status = "generating"
            pkg.zip_url = None
            # 全量重做：清掉旧交付物（含历史多格式行 / 上次中断的半成品），避免新旧混杂
            old_items = await db.execute(
                select(DeliverableFile).where(DeliverableFile.package_id == pkg.id)
            )
            for old in old_items.scalars().all():
                await db.delete(old)

        order.status = "generating"
        order.generating_at = _now()
        await db.commit()
        await db.refresh(pkg)

        storage = get_storage()
        # (ZIP 内中文归档名, 格式, 本地路径)
        file_paths: list[tuple[str, str, str]] = []
        date_str = _now().strftime("%Y%m%d")

        try:
            context = await build_context(db, order)
            all_codes = sorted(DELIVERABLES.keys())
            # V5.0 闸门 6：生成前先做一次预算熔断判定（触及上限则全量降级模板模式）
            owner_key = f"user:{user_id}"
            budget = await ai_cost.check_budget(db, owner_key, order.plan or "none", "package")
            # V5.0 闸门 4：轮数上限（启动包 ≤25 轮）。AI 件每件 3 轮，超限则降级模板模式。
            rounds_gate = ai_cost.check_rounds("package", 3 * len(AI_DELIVERABLES))
            ai_allowed = bool(budget["allow_ai"]) and bool(rounds_gate["allow_ai"])
            if not ai_allowed:
                logger.warning(
                    "启动包生成降级模板模式：order_id=%s 预算=%s 轮数=%s",
                    order_id,
                    budget["allow_ai"],
                    rounds_gate["allow_ai"],
                )

            for code in all_codes:
                name, _primary = DELIVERABLES[code]
                # PRD 4.4.1：一个交付物可能交付多种格式（D03=PDF+Word 等），逐一落库，
                # 每行 DeliverableFile 代表「一件交付物的一个格式」。
                try:
                    formats = generate_formats(code, context)
                except Exception as exc:
                    logger.exception("交付物生成失败: %s %s - %s", code, name, exc)
                    continue

                for fmt, local_path in formats.items():
                    ext = FILE_EXT.get(fmt, "bin")
                    try:
                        storage_key = f"packages/{user_id}/{order_id}/{code}_{name}.{ext}"
                        url = storage.save_file(local_path, storage_key)

                        db.add(DeliverableFile(
                            id=str(uuid.uuid4()),
                            package_id=pkg.id,
                            code=code,
                            name=name,
                            file_type=fmt,
                            url=url,
                        ))
                        await db.commit()
                        # M4-03：ZIP 包内统一中文命名「生意快启_交付物名称_生成日期.扩展名」
                        file_paths.append((f"生意快启_{name}_{date_str}.{ext}", fmt, local_path))
                        logger.info("交付物生成完成: %s %s [%s]", code, name, fmt)
                    except IntegrityError:
                        # 并发写入撞上 (package_id, code, file_type) 唯一约束：视为已生成，
                        # 回滚失败事务后继续（不回滚会让本会话后续所有写操作报错）
                        await db.rollback()
                        file_paths.append((f"生意快启_{name}_{date_str}.{ext}", fmt, local_path))
                        logger.info("交付物已存在，跳过重复落库: %s %s [%s]", code, name, fmt)
                    except Exception as exc:  # 单个格式失败不阻断其余交付物
                        await db.rollback()
                        logger.exception("交付物落库失败: %s %s [%s] - %s", code, name, fmt, exc)

                # V5.0 第 7 章闸门 3「模板化交付」成本记账：7 件模板填充 + 3 件 AI 实时生成。
                # 成本红线：开业礼包单次 ≤ 3.5 元，故此处必须如实记账，供 M4-05 看板核算毛利率。
                try:
                    if code in AI_DELIVERABLES and ai_allowed:
                        prompt = f"为{context.get('city', '本市')}的{name}生成个性化内容"
                        await ai_cost.record_ai_call(
                            db,
                            "package",
                            prompt,
                            name,  # completion 量级按交付物名称占位，token 由估算函数换算
                            owner_key=owner_key,
                            order_id=order_id,
                            rounds=min(3, int(rounds_gate["capped_rounds"])),
                        )
                    else:
                        # 模板填充（含熔断降级的 AI 件）：成本极低，如实入账
                        await ai_cost.record_template_deliverable(
                            db, order_id, owner_key, code, chars=800
                        )
                    await db.commit()
                except Exception as exc:  # 记账失败绝不影响交付
                    await db.rollback()
                    logger.warning("AI 成本记账失败（不影响交付）: %s - %s", code, exc)

            if not file_paths:
                raise RuntimeError("全部交付物生成失败")

            # 打包 ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for arcname, _fmt, local_path in file_paths:
                    try:
                        zf.write(local_path, arcname)
                    except Exception as exc:
                        logger.warning("ZIP 打包跳过: %s - %s", arcname, exc)
            zip_buffer.seek(0)
            zip_url = storage.save_bytes(
                f"packages/{user_id}/{order_id}/startup_package.zip",
                zip_buffer.read(),
            )

            pkg.status = "delivered"
            pkg.zip_url = zip_url
            order.status = "delivered"
            order.delivered_at = _now()
            await db.commit()

            logger.info("启动包生成全部完成: order_id=%s zip=%s", order_id, zip_url)

            # M9：生成完成后给用户发一条站内消息
            try:
                from app.services import notify as notify_service

                await notify_service.create_notification_for_user(
                    db,
                    user_id,
                    "package",
                    "启动包已生成完成",
                    f"《{context['opportunity'].get('title', '你的创业项目')}》启动包 10 件交付物已就绪，可立即下载。",
                    f"/package/{order_id}",
                )
                await db.commit()
            except Exception as exc:  # 消息失败不影响交付
                logger.warning("启动包完成消息推送失败：%s", exc)

            return True

        except Exception as exc:
            logger.exception("启动包生成异常: order_id=%s", order_id)
            try:
                pkg.retry_count = (pkg.retry_count or 0) + 1
                pkg.status = "generating"
                await db.commit()
            except Exception as inner:
                logger.warning("失败计数落库失败：%s", inner)
                await db.rollback()
            return False


async def _mark_refunded(order_id: str) -> None:
    """重试用尽：标记失败并全额退款，同时给用户发站内消息（M4-08）。"""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        order = await db.get(Order, order_id)
        if order is None:
            return
        pkg = await _get_package_row(db, order_id)

        if pkg is not None:
            pkg.status = "failed"
        order.status = "refunded"
        order.refunded_at = _now()
        await db.commit()
        logger.error("启动包生成连续失败，已全额退款：order_id=%s", order_id)

        try:
            from app.services import notify as notify_service

            await notify_service.create_notification_for_user(
                db,
                order.user_id,
                "refund",
                "启动包生成失败，已全额退款",
                "系统多次尝试生成启动包仍未成功，已为你全额退款，款项将原路退回。",
                f"/orders/{order.id}",
            )
            await db.commit()
        except Exception as exc:
            logger.warning("退款消息推送失败：%s", exc)
