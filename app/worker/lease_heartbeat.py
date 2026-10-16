"""使用独立数据库会话为执行中的论文任务定期续租。"""
import logging
from threading import Event, Thread

from app.db.session import SessionLocal
from app.services.processing_job_repository import (
    ProcessingJobRepository,
)

logger = logging.getLogger(__name__)
class LeaseHeartbeat:
    """维护当前 Worker 执行尝试的数据库租约。"""

    def __init__(
        self,
        task_id: str,
        attempt_count: int,
        interval_seconds: float = 60.0,
        session_factory=None,
    ):
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")

        self.task_id = task_id
        self.attempt_count = attempt_count
        self.interval_seconds = interval_seconds
        self.session_factory = (
            session_factory
            if session_factory is not None
            else SessionLocal
        )

        self._stop_event = Event()
        self._lost_event = Event()
        self._renewed_event = Event()
        self._thread = None

    @property
    def lease_lost(self) -> bool:
        """表示续租失败，当前执行尝试可能已失效。"""
        return self._lost_event.is_set()

    def _renew_once(self) -> bool:
        """使用独立事务完成一次续租。"""
        try:
            with self.session_factory() as db:
                jobs = ProcessingJobRepository(db)

                if not jobs.renew_lease(
                    self.task_id,
                    self.attempt_count,
                ):
                    db.rollback()
                    return False

                db.commit()
                return True

        except Exception:
            logger.exception(
                "Lease heartbeat failed: task_id=%s attempt=%s",
                self.task_id,
                self.attempt_count,
            )
            return False

    def _run(self) -> None:
        """周期续租，记录续租成功与租约失效状态。"""

        while not self._stop_event.wait(self.interval_seconds):
            if not self._renew_once():
                if not self._stop_event.is_set():
                    self._lost_event.set()
                return

            self._renewed_event.set()

    def start(self) -> None:
        """启动心跳线程。"""
        if self._thread is not None:
            raise RuntimeError("Heartbeat already started")

        self._thread = Thread(
            target=self._run,
            name=f"lease-heartbeat-{self.task_id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """请求停止心跳，并在限定时间内等待线程退出。"""

        self._stop_event.set()

        if self._thread is None:
            return

        self._thread.join(timeout=timeout)

        if self._thread.is_alive():
            self._lost_event.set()
            logger.warning(
                "Lease heartbeat did not stop in time: task_id=%s",
                self.task_id,
            )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()
        return False
