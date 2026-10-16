"""
扫描异常滞留的论文任务，并恢复数据库状态或重新派发。
"""
import logging

from sqlalchemy.orm import Session

from app.services.processing_job_repository import ProcessingJobRepository

logger = logging.getLogger(__name__)

class JobRecoveryService:
    """协调 PostgreSQL 任务恢复与 Celery 消息派发。"""

    def __init__(self, db: Session, dispatch_task):
        self.db = db
        self.dispatch_task = dispatch_task
        self.jobs = ProcessingJobRepository(db)

    
    def recover_once(self, limit: int = 100) -> dict:
        """执行一轮任务恢复扫描，使用原子预留限制重复派发。"""

        candidates = self.jobs.list_recovery_candidates(
            limit=limit
        )

        recovered = 0
        failed = 0
        dispatched = 0
        dispatch_errors = 0

        for candidate in candidates:
            task_id = candidate.task_id

            try:
                if candidate.status == "processing":
                    # 重新检查数据库状态，避免恢复已续租的任务。
                    if candidate.attempt_count < candidate.max_attempts:
                        changed = self.jobs.recover_expired_job(task_id)

                        if changed:
                            recovered += 1
                    else:
                        changed = self.jobs.fail_expired_job(task_id)

                        if changed:
                            failed += 1

                    self.db.commit()

                    if not changed:
                        continue

                    # 次数耗尽的任务已经 failed，不再派发。
                    if candidate.attempt_count >= candidate.max_attempts:
                        continue

                elif candidate.status != "pending":
                    continue

                # 原子预留派发资格。
                # 多个调度器竞争同一个任务时，
                # 只有获得资格者才向 Redis 发送消息。
                reserved = self.jobs.reserve_dispatch(
                    task_id=task_id,
                    interval_seconds=30,
                )

                if not reserved:
                    self.db.rollback()
                    continue

                # 必须先提交预留结果，才能向 Redis 派发。
                self.db.commit()

                try:
                    self.dispatch_task(task_id)
                    dispatched += 1

                except Exception:
                    # 不能声称已经派发成功。
                    # 预留窗口到期后，可以重新扫描并派发。
                    dispatch_errors += 1

            except Exception:
                dispatch_errors += 1
                logger.exception(
                    "Failed to dispatch processing job: task_id=%s",
                    task_id,
                )

        return {
            "scanned": len(candidates),
            "recovered": recovered,
            "failed": failed,
            "dispatched": dispatched,
            "dispatch_errors": dispatch_errors,
        }
