# Folder ZIP downloads

User requested downloading each folder and all its descendants as a ZIP. This supersedes the first-version ZIP exclusion in the original design.

## Implementation

- Folder `⋯` menus provide ZIP 다운로드. The page toolbar provides 현재 폴더 ZIP 다운로드, including the storage root.
- `GET /api/archive?path=` streams a ZIP containing the selected top-level folder, descendants, Unicode names and empty folders. `HEAD` validates metadata; `GET` with `check=true` returns the filename as JSON for actionable browser preflight errors.
- Authenticate every request. Traverse by directory descriptors with no-follow flags. Exclude symlinks, special files and `.nas-upload` at all depths; reject unsafe archive names.
- Preflight captures metadata and checks readability, keeping normal errors before download headers. Contents are then read in 256 KiB blocks through standard-library ZIP/ZIP64 without a temporary archive. Compression level 1 keeps processing suitable for media-heavy folders.
- Metadata is held in memory; cap at 100,000 entries and depth 256. Abort if source files are replaced or changed during download; this is a live read, not a filesystem snapshot. Dynamic ZIP downloads do not support Range/resume.
- No changes to original files, mergerfs policies, storage mounts or account state.

## Verification

- API regression suite first failed on missing endpoint, then passed. Includes CRC/byte equality, nesting, Unicode, empty folders, bounded output chunks, authentication, unsafe names/paths, symlink swaps, special-file/staging exclusion, permission errors, entry limits and concurrent source changes.
- Browser regression first failed on missing ZIP menu. Mobile ZIP download and expiry handling passed along with all existing file/media flows.
- Real mergerfs 2.33.5 with two disposable branches and epmfs policy: nested folder ZIP extracted with matching original bytes and valid CRC. No personal storage attached.
- Non-root container integration verified ZIP extraction and all previous storage/restart behavior.
- Fresh independent code review found no material issues. Its actionable-error UX note was addressed by JSON preflight rather than parsing bodyless HEAD errors; regression reproduced RED then fixed.
- Final verification: backend 54/54 passed; browser 9/9 passed; TypeScript/Vite and Docker builds passed. No additional runtime dependencies.
