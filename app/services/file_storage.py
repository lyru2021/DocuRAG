"""本地 PDF 原文存储服务。"""

import hashlib
import os
import tempfile
from pathlib import Path
from uuid import UUID


class LocalFileStorage:
    """本地 PDF 原文存储。

    该类只负责文件系统读写和 hash 校验；数据库记录由仓储层负责维护。
    """

    def __init__(self, storage_dir: Path):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, file_id: str) -> Path:
        """把 file_id 转换为安全的 PDF 文件路径。

        Args:
            file_id: 文档文件 UUID 字符串。

        Returns:
            Path: 存储目录下对应的 PDF 路径。

        Raises:
            ValueError: `file_id` 不是合法 UUID。
        """

        # Only a valid UUID may be used as a storage identifier.
        # 通过 UUID 解析阻止路径穿越或任意文件名写入。
        safe_id = str(UUID(file_id))
        return self.storage_dir / f"{safe_id}.pdf"

    def save_pdf(self, file_id: str, data: bytes) -> Path:
        """保存 PDF 原始字节。

        Args:
            file_id: 文档文件 UUID 字符串。
            data: PDF 原始字节。

        Returns:
            Path: 成功保存后的目标路径。

        Raises:
            ValueError: `file_id` 不是合法 UUID。
            FileExistsError: 相同 file_id 的文件已经存在。
            OSError: 临时文件写入、同步或发布失败。
        """

        target = self._path(file_id)

        if target.exists():
            raise FileExistsError(
                f"File already exists: {file_id}"
            )

        temporary_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.storage_dir,
                prefix=".upload-",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(data)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)

            # Atomic publication without overwriting an existing target.
            # 先写临时文件再发布，避免数据库写入前读到不完整 PDF。
            os.link(temporary_path, target)

            return target

        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def get_pdf_path(self, file_id: str) -> Path | None:
        """返回 PDF 路径。

        Args:
            file_id: 文档文件 UUID 字符串。

        Returns:
            Path | None: 文件存在时返回路径，否则返回 None。

        Raises:
            ValueError: `file_id` 不是合法 UUID。
        """

        target = self._path(file_id)

        if not target.is_file():
            return None

        return target

    def verify_hash(
        self,
        file_id: str,
        expected_hash: str,
    ) -> bool:
        """校验本地 PDF 内容是否匹配数据库保存的 SHA-256。

        Args:
            file_id: 文档文件 UUID 字符串。
            expected_hash: 数据库中保存的十六进制 SHA-256 摘要。

        Returns:
            bool: 文件存在且 hash 一致时返回 True，否则返回 False。

        Raises:
            ValueError: `file_id` 不是合法 UUID。
        """

        path = self.get_pdf_path(file_id)

        if path is None:
            return False

        digest = hashlib.sha256()

        with path.open("rb") as file:
            for block in iter(
                lambda: file.read(1024 * 1024),
                b"",
            ):
                digest.update(block)

        return digest.hexdigest() == expected_hash

    def delete_pdf(self, file_id: str) -> None:
        """删除本地 PDF 文件。

        Args:
            file_id: 文档文件 UUID 字符串。

        Raises:
            ValueError: `file_id` 不是合法 UUID。
        """

        self._path(file_id).unlink(missing_ok=True)
