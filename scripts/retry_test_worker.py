"""
启动仅用于本地联调的一次性解析故障注入 Worker。
"""

from app.services.paper_processing_service import PaperProcessingService
from app.services.processing_errors import TransientProcessingError
from app.worker.celery_app import celery_app

_original_process_pdf = PaperProcessingService.process_pdf
_failed_once = False


def fail_once(self, *args, **kwargs):
    """第一次解析测试任务时模拟临时故障。"""
    global _failed_once

    if not _failed_once:
        _failed_once = True
        print("INJECTED_TRANSIENT_FAILURE", flush=True)
        raise TransientProcessingError(
            "Injected transient failure"
        )

    return _original_process_pdf(self, *args, **kwargs)


PaperProcessingService.process_pdf = fail_once


if __name__ == "__main__":
    celery_app.start(
        argv=[
            "worker",
            "--loglevel=info",
            "--pool=solo",
            "--concurrency=1",
            "--hostname=retry-test@%h",
        ]
    )