## Day 4 — Testing and Transaction Management

### Implemented and Verified

- Added reusable pytest fixtures for the test database, HTTP client, and sample document.
- Used a separate PostgreSQL database (`docurag_test`).
- Implemented transaction isolation with SQLAlchemy SAVEPOINTs.
- Verified document CRUD, HTTP 422/404 responses, and cascading deletion.
- Tested unique constraint violations using PostgreSQL.
- Verified Repository rollback behavior using a mocked commit failure.

### Test Results

- First repeated test run: 13 passed.
- Second repeated test run: 13 passed.
- Test database before and after repeated runs: 0 documents, 0 chunks.
- Transaction tests: 2 passed.

### Technical Notes

**Connection pooling:** Reuses database connections and manages connection availability, reducing repeated connection establishment overhead.

**Database indexing:** Supports efficient record lookup for suitable queries while introducing storage and write-maintenance costs.

**Transaction management:** Successful write operations are committed. Failed operations are rolled back, and Sessions are closed after use.

### Limitations

- Connection pool and index performance have not been benchmarked.
- Tests currently run against a local PostgreSQL instance.
- Redis, file upload, document parsing, and vector search are not yet implemented.


## Day 5 — PDF/TXT Upload and Parsing

### Implemented

- Added `POST /documents/upload` using FastAPI `UploadFile`.
- Restricted uploads to PDF and TXT files with a 10 MiB size limit.
- Implemented PDF text extraction using PyMuPDF and strict UTF-8 TXT decoding.
- Added text cleaning while preserving line and paragraph boundaries.
- Added upload metadata fields through Alembic migration `958f10b430f0`.
- Stored parsed text, media type, file size, SHA-256 hash, UUID, parsing status, and text length in PostgreSQL.
- Added error handling for empty files, unsupported formats, invalid encoding, invalid PDFs, and PDFs without extractable text.
- Used separate service and repository layers for parsing and persistence.

### Verification

- Upload API tests: **10 passed**.
- Manually uploaded a TXT file and a text-based PDF.
- Both uploads created queryable Document records.
- Database text-content inspection and final regression test: pending confirmation.

### Known Limitations

- Scanned PDFs are not supported because OCR has not been implemented.
- PDF extraction may be inaccurate for complex layouts, tables, or formulas.
- Original uploaded files are not persisted; only metadata and extracted text are stored.
- File uploads are limited to 10 MiB.
- SHA-256 is recorded for identification; automatic deduplication is not implemented.