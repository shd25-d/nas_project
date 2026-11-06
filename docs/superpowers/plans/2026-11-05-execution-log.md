# Execution ledger

- Design approved by user; implement inline under existing authorization.
- New repository has no baseline commit or application. Work proceeds in provided workspace; no worktree or git commits requested. No existing code to preserve.
- Docker CLI available but daemon stopped (verified with elevated `docker info`). Local Python/Node tests will be run; actual container checks remain conditional on daemon availability.
- Task 1: auth API test-first, missing-module RED → 6 tests GREEN.
- Task 2: storage/streaming API test-first, missing routes RED → file suite GREEN after preview route added.
- Task 3: preview test-first, missing routes RED; diagnosed Mammoth interpreting fdopen.name as a filesystem path; bounded BytesIO conversion fixed the interface. Backend 29 tests GREEN.
- Task 4: browser lifecycle RED on missing UI, then decorative heading accessibility and sidebar overflow issues reproduced and fixed. PDF/DOCX/image/audio and recorded MP4 tests passed. Full lifecycle rerun pending sidebar fix.
- Task 5: Docker Desktop started with approved tool invocation; Docker 29.5.3 ready; actual image build successful on Python 3.12. Compose config and local dependency checks pass.
- Authentication policy: authorize operations at request start; an already authorized stream may finish after session expiry. Each subsequent request requires a valid session.
- Final review: fresh read-only reviewer found no Critical/Important backend or data-loss issues. Download links bypassing session-expiry UI handling was raised as Minor and treated as a required UX fix because the design calls for clear expired-session behavior. Browser regression reproduced RED, shared session preflight added without buffering the download, full browser suite GREEN (7/7). No findings remain deferred.
- Final local verification: `.venv/bin/python -m pytest -q` → 29 passed; `npm run build` → TypeScript and production bundle successful; `npm test` → 7 passed. Compose config and `git diff --check` pass. PDF viewer remains a large lazy-loaded chunk; Vite emits a size advisory only.
- Real container test: disposable Compose project, non-root runtime, 2 MiB chunked upload/download, DOCX conversion under Linux memory limit, local PDF assets, Range, rename/delete, restart preserving account/session/files → PASS. Test project removed; no real personal files or credentials used.
- Desktop/mobile screenshots saved to ignored `artifacts/desktop.png` and `artifacts/mobile.png`; visually inspected without overflow.
- Final image rebuilt and actual local service started. `docker compose ps` → healthy, published on `127.0.0.1:8080` only; `/` HTTP 200 and `/api/status` configured=false. `.env` uses current UID/GID; empty `data/files` and account database initialized. User must choose credentials with the interactive create-owner command.
- Source remains in the provided workspace without committing, pushing, or publishing. No existing branch history existed to merge. Router/VPN and actual phone/network access remain outside this iteration as agreed.
