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