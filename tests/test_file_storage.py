"""本地 PDF 文件存储服务测试。"""

import hashlib
from uuid import uuid4

import pytest

from app.services.file_storage import LocalFileStorage


def test_save_and_read_pdf(tmp_path):
    storage = LocalFileStorage(tmp_path)
    file_id = str(uuid4())
    data = b"%PDF-1.7\nfake test bytes"

    path = storage.save_pdf(file_id, data)

    assert path.is_file()
    assert path.read_bytes() == data
    assert path.name == f"{file_id}.pdf"


def test_hash_verification(tmp_path):
    storage = LocalFileStorage(tmp_path)
    file_id = str(uuid4())
    data = b"%PDF-1.7\nexample"

    storage.save_pdf(file_id, data)

    expected = hashlib.sha256(data).hexdigest()

    assert storage.verify_hash(file_id, expected)
    assert not storage.verify_hash(file_id, "wrong-hash")


def test_duplicate_file_id_is_rejected(tmp_path):
    storage = LocalFileStorage(tmp_path)
    file_id = str(uuid4())

    storage.save_pdf(file_id, b"first")

    with pytest.raises(FileExistsError):
        storage.save_pdf(file_id, b"second")

    assert storage.get_pdf_path(file_id).read_bytes() == b"first"


def test_invalid_file_id_is_rejected(tmp_path):
    storage = LocalFileStorage(tmp_path)

    with pytest.raises(ValueError):
        storage.save_pdf("../../secret", b"data")


def test_delete_pdf(tmp_path):
    storage = LocalFileStorage(tmp_path)
    file_id = str(uuid4())

    storage.save_pdf(file_id, b"data")
    storage.delete_pdf(file_id)

    assert storage.get_pdf_path(file_id) is None


def test_missing_pdf_returns_none(tmp_path):
    storage = LocalFileStorage(tmp_path)

    assert storage.get_pdf_path(str(uuid4())) is None
