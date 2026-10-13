import hashlib
import os
import tempfile
from pathlib import Path
from uuid import UUID


class LocalFileStorage:
    def __init__(self, storage_dir: Path):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, file_id: str) -> Path:
        # Only a valid UUID may be used as a storage identifier.
        safe_id = str(UUID(file_id))
        return self.storage_dir / f"{safe_id}.pdf"

    def save_pdf(self, file_id: str, data: bytes) -> Path:
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
            os.link(temporary_path, target)

            return target

        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def get_pdf_path(self, file_id: str) -> Path | None:
        target = self._path(file_id)

        if not target.is_file():
            return None

        return target

    def verify_hash(
        self,
        file_id: str,
        expected_hash: str,
    ) -> bool:
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
        self._path(file_id).unlink(missing_ok=True)
