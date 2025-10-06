# CODEX Addendum – xsmbseek

Project-specific guidance for Codex when collaborating on the xsmbseek GUI frontend. Read this alongside the global `CODEX.md` at the start of every session.

## Project Snapshot
- xsmbseek is a tkinter GUI that orchestrates the external SMBSeek backend via subprocesses.
- Keep frontend/backend separation intact: no direct imports from SMBSeek, only subprocess invocations.
- Many workflows depend on persisted user settings (`gui/utils/settings_manager.py`)—treat signature changes carefully.

## Working Agreements
- Surface downstream effects (GUI ➔ backend ➔ docs/tests) before changing behaviour.
- When touching backend integration (`gui/utils/backend_interface.py` or `gui/utils/scan_manager.py`), audit progress parsing, error handling, and configuration side effects.
- Before altering UI callbacks, inspect corresponding ScanManager/BackendInterface expectations to avoid contract drift (recent example: scan dialog ➔ `_start_new_scan`).

## Breadth Checks Before Editing
- For any CLI command changes, update documentation snippets in `docs/` and confirm tests/mocks still align.
- If modifying table column layouts or selection semantics in GUI components, verify index-dependent references (e.g., treeview column offsets) and export helpers.
- When adjusting settings schema, update defaults, getters, and persistence routines together to avoid partial migrations.

## Testing Expectations
- Prefer `./xsmbseek --mock` for GUI smoke tests when backend is unavailable.
- When CLI changes are involved, note required real-backend tests even if you cannot run them locally.
- Document manual test steps executed (e.g., “launched scan dialog, started mock scan”) in final summaries.

## Documentation & Memory Hooks
- Record new lessons here with short bullets (optionally date-stamped). Keep entries concise so future sessions can skim quickly.
- If a convention crosses projects, sync it back into the root `CODEX.md` as well.

### Open Notes (2025-02-14)
- **Scan dialog contract**: Ensure dialog returns a full scan options dict; `_start_new_scan` is not string-compatible.
- **Phase changes**: When backend workflow shifts, update progress mappings in both `BackendInterface` and `ScanManager`, plus user-facing copy.
- **Avoid lists**: Favourite/avoid toggles share SettingsManager—mirror helper methods when adding new flags.
- **Scan results summary counts** (2025-02-20): Completion dialog still shows zeros for host/share counts despite DB persisting totals. Treat as known issue until parser fix lands.

Add new findings below this section as they emerge.
