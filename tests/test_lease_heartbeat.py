
"""测试 Worker 租约心跳的续租、停止及失效处理。"""

from unittest.mock import MagicMock, patch

import pytest

from app.worker.lease_heartbeat import LeaseHeartbeat


def test_heartbeat_renews_lease():
    """心跳应提交成功的租约续期。"""

    db = MagicMock()
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = db

    with patch(
        "app.worker.lease_heartbeat.ProcessingJobRepository"
    ) as repo_class:
        repo_class.return_value.renew_lease.return_value = True

        heartbeat = LeaseHeartbeat(
            task_id="test-task",
            attempt_count=1,
            session_factory=session_factory,
        )

        assert heartbeat._renew_once() is True

    repo_class.return_value.renew_lease.assert_called_once_with(
        "test-task",
        1,
    )
    db.commit.assert_called_once()


def test_heartbeat_detects_lease_loss():
    """续租条件更新失败时，应返回失败。"""

    db = MagicMock()
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = db

    with patch(
        "app.worker.lease_heartbeat.ProcessingJobRepository"
    ) as repo_class:
        repo_class.return_value.renew_lease.return_value = False

        heartbeat = LeaseHeartbeat(
            task_id="test-task",
            attempt_count=1,
            session_factory=session_factory,
        )

        assert heartbeat._renew_once() is False

    db.rollback.assert_called_once()


def test_heartbeat_handles_database_error():
    """数据库续租异常应被视为租约状态不可信。"""

    session_factory = MagicMock(
        side_effect=ConnectionError("Database unavailable")
    )

    heartbeat = LeaseHeartbeat(
        task_id="test-task",
        attempt_count=1,
        session_factory=session_factory,
    )

    assert heartbeat._renew_once() is False


def test_heartbeat_rejects_invalid_interval():
    """不允许零间隔或负数间隔。"""

    with pytest.raises(ValueError):
        LeaseHeartbeat(
            task_id="test-task",
            attempt_count=1,
            interval_seconds=0,
        )


def test_heartbeat_marks_loss_on_renew_failure():
    """续租失败后应标记租约失效。"""

    from unittest.mock import patch

    heartbeat = LeaseHeartbeat(
        task_id="test-task",
        attempt_count=1,
        interval_seconds=0.01,
    )

    with patch.object(
        heartbeat,
        "_renew_once",
        return_value=False,
    ):
        heartbeat.start()

        assert heartbeat._lost_event.wait(timeout=1.0)
        assert heartbeat.lease_lost is True

        heartbeat.stop()


def test_heartbeat_stops_without_lease_loss():
    """正常停止时不应错误标记租约失效。"""

    heartbeat = LeaseHeartbeat(
        task_id="test-task",
        attempt_count=1,
        interval_seconds=60.0,
    )

    heartbeat.start()
    heartbeat.stop()

    assert heartbeat.lease_lost is False
    assert not heartbeat._thread.is_alive()