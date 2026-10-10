import os

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models.document import Document

def get_test_database_url() -> str:
    values = dotenv_values(".env.test")

    url = (
        os.environ.get("TEST_DATABASE_URL")
        or values.get("TEST_DATABASE_URL")
    )

    if not url:
        raise RuntimeError(
            "TEST_DATABASE_URL is required"
        )

    if make_url(url).database != "docurag_test":        #test数据库安全检查
        raise RuntimeError(
            "Tests must use docurag_test"
        )

    return url


@pytest.fixture
def db_session():
    engine = create_engine(
        get_test_database_url(),
        pool_pre_ping=True,
    )

    connection = engine.connect()
    transaction = connection.begin()    #外层

    db = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",   #SAVEPOINT模式，允许嵌套事务
        expire_on_commit=False,
    )

    try:
        yield db
    finally:
        db.close()

        if transaction.is_active:
            transaction.rollback()

        connection.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def sample_document(db_session):
    document = Document(
        title="Sample Document",
        filename="sample.pdf",
    )
    db_session.add(document)    #添加到session，SQLAlchemy开始跟踪这个对象
    db_session.flush()          #flush() 会让 SQLAlchemy 执行 INSERT，但不会提交外层事务。
    db_session.refresh(document)#重新读取数据库中的字段
    
    return document