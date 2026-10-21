"""在加载 pytest 和应用代码前初始化独立测试数据库配置。"""

import os
import sys

from dotenv import dotenv_values
from sqlalchemy.engine import make_url


def main() -> int:
    """校验测试数据库并启动 pytest。"""

    values = dotenv_values(".env.test")

    url = (
        os.environ.get("TEST_DATABASE_URL")
        or values.get("TEST_DATABASE_URL")
    )

    if not url:
        raise RuntimeError("TEST_DATABASE_URL is required")

    if make_url(url).database != "docurag_test":
        raise RuntimeError(
            "Tests must use docurag_test"
        )

    # 必须在导入 pytest 之前执行。
    os.environ["DATABASE_URL"] = url
    os.environ["ENV_FILE"] = ".env.test"
    # 普通业务测试使用明确的测试环境，不依赖开发环境密钥。
    os.environ["APP_ENV"] = "test"
    os.environ["AUTH_ENABLED"] = "false"

    import pytest

    return pytest.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())