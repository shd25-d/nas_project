# Personal NAS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver the approved personal NAS with authenticated file management, previews, mobile UI and Docker deployment.

**Architecture:** React/TypeScript builds static assets served by one FastAPI process. Files and SQLite sessions live in separate persistent directories. File operations use descriptor-relative traversal without symlinks.

**Tech Stack:** Python, FastAPI, SQLite, Argon2id, React, Vite, PDF.js, Mammoth, DOMPurify, highlight.js.

**Spec:** `docs/superpowers/specs/2026-11-04-personal-nas-design.md` (approved).

## Global Constraints

- One app container; no external CDN or conversion service.
- Single owner; no public signup; account created by interactive CLI.
- File storage `/data/files`, app state `/data/app`; original bytes preserved.
- Default upload cap 10 GiB; streaming writes and atomic no-overwrite publication.
- Auth and CSRF for file mutations; no symlink or traversal access.
- Korean responsive UI; router/VPN configuration outside scope.

## Review Focus

- Filename collisions and concurrent mutations must never overwrite original data.
- Symlinks and ancestor-directory changes must not escape the storage root.
- Interrupted uploads and oversize bodies must leave no visible partial files.
- DOCX zip expansion and hostile HTML must remain bounded and inert.
- Expired sessions during upload/viewing must fail clearly without exposing bytes.

### Task 1: Authentication and application boundary

**Files:** `server/config.py`, `server/auth.py`, `server/main.py`, `server/cli.py`, `tests/test_auth.py`, `tests/conftest.py`, `requirements*.txt`.
**Interfaces:** `create_app(settings: Settings) -> FastAPI`; `create_owner(settings, username, password, reset=False)`; `GET /api/session` returns `{username, csrf}`; `POST /api/login` accepts username/password and returns session; logout requires `X-CSRF-Token`.

- [x] Write API integration tests for no owner, unauthenticated access, login/logout, CSRF, expiration and persistent account restart.
- [x] Run pytest and observe missing implementation fail.
- [x] Implement SQLite owner/session storage with hashed tokens, expiry, login throttling, CLI and response headers.
- [x] Run authentication suite; require all green.

### Task 2: Safe streaming file management

**Files:** `server/storage.py`, `server/files.py`, `tests/test_files.py`.
**Interfaces:** `GET /api/files?path=` lists entries; `POST /api/folders {path,name}`; `POST /api/upload?path=&name=` streams raw body; `PATCH /api/entry {path,destination}` moves/renames; `DELETE /api/entry?path=`; authenticated `GET /api/content?path=&download=` with HTTP Range.

- [x] Write integration tests for byte equality, listing, move/delete, Unicode, collision, oversize cleanup, invalid paths, symlinks, Range, directory-self move and authentication.
- [x] Observe failing tests, then implement descriptor-relative storage and request streaming into hidden staging.
- [x] Return structured Korean API errors; test original-file preservation and staged upload cleanup.
- [x] Run entire backend suite.

### Task 3: Bounded document previews

**Files:** `server/previews.py`, `tests/test_previews.py`, `web/src/Viewer.tsx`.
**Interfaces:** `GET /api/preview?path=` returns `{kind,text}` for bounded UTF-8 source or `{kind,html}` for DOCX; media/PDF use authenticated content endpoint.

- [x] Write tests for plain text, binary/oversize rejection, minimal DOCX, corrupt/expanded zip rejection and hostile document HTML.
- [x] Observe failures; implement bounded DOCX subprocess conversion with timeout and response limits; sanitize both server and client.
- [x] Verify backend suite.

### Task 4: Responsive user interface

**Files:** `web/src/{App,Explorer,Viewer,api,types}.tsx/ts`, `web/src/styles.css`, `web/package.json`, `web/index.html`, `web/tsconfig*.json`, `web/vite.config.ts`, `web/e2e/app.spec.ts`.
**Interfaces:** Use API contracts above; use native authenticated content URLs, XHR upload progress, local PDF.js worker and sanitized DOMPurify DOCX.

- [x] Write browser scenarios for login, folder/upload/download, preview, rename/move/delete, mobile layout, unsupported files and expired session.
- [x] Run against missing UI to establish red.
- [x] Build Korean UI with sidebar, breadcrumb, file list, action menus, progress, accessible dialogs and mobile layout.
- [x] Typecheck/build, run real browser workflows at desktop and mobile sizes.

### Task 5: Container, documentation and final review

**Files:** `Dockerfile`, `compose.yaml`, `.env.example`, `.dockerignore`, `.gitignore`, `README.md`, verification ledger.

- [x] Add multi-stage build, non-root runtime, volume mounts and configurable bind address/port, healthcheck.
- [x] Document account creation/reset, permissions, backup, development, supported previews, VPN deployment assumptions.
- [x] Run full backend suite, frontend build and browser suite; Compose config/build/start/restart if engine available.
- [x] Fresh whole-project review, reproduce and fix material findings with tests.
- [x] Record evidence and limitations; deliver startup commands without publishing externally.
