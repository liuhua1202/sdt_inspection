# Changelog

A running log of notable changes, organised by severity.

## v2.1 \u2014 Audit and refactor pass

### P0 \u2014 critical bugs (would corrupt state or lose data)

* **Device status matching by name (race on duplicates)**
  `ui._set_device_status` used `break` after the first match, so two
  devices sharing a CSV name would have their state updated on the
  wrong row.  Switched to `return` and silently ignore rows that
  vanished (e.g. CSV reloaded mid-run).

* **InspectionService.stop() did not join the coordinator thread**
  Pressing the window-close button while an inspection was running
  killed the worker before it could finish writing the result log
  file.  `stop(join=True, join_timeout=5.0)` is now used by
  `_on_close` so the in-flight result file is flushed before the
  process exits.

### P1 \u2014 design issues (regressions or platform footguns)

* **AppLogger created a fresh FileHandler on every instantiation**
  Two `InspectionService` instances in the same process used to leave
  two log files open with the same name.  Handlers are now installed
  once at module import time, guarded by `if not logger.handlers`.

* **`has_prompt` failed on bracketed prompts like `[SW1]>`**
  The regex only matched the last character of a line, and the
  fallback list was a single character.  Both now explicitly handle
  `[hostname]>` / `[hostname]#` for Huawei / Cisco / H3C devices.

* **`reference_format` heuristic mis-classified a device named `01`**
  `row[2].isdigit()` was used as a tie-breaker between the 6- and
  8-column CSV formats.  Replaced with a whitelist check against
  `device_types` so numeric names do not get misread as type ids.

* **Dead code: `make_status_pill`**
  Removed \u2014 871 bytes, also dropped from `__all__`.

### P2 \u2014 transport / IO bugs

* **socket.timeout treated as EOF in `_read_paramiko`**
  Paramiko uses a non-blocking poll; a `socket.timeout` is the normal
  idle path, not a real close.  The loop now distinguishes between
  the two: idle continues, `OSError` / `EOFError` / `data == b\"\"`
  after a non-timeout read exit cleanly.

* **`time.sleep(0.1)` + single read to detect a prompt**
  Slow devices (some Huawei models take 200-400 ms to issue a prompt
  after \r\n) would miss the prompt and fall through to the
  `TransportError` branch.  Both SSH and Netmiko paths now nudge the
  device up to three times before giving up.

* **`open_in_file_manager` shell injection**
  The macOS / Linux branches used `os.system(f'open \"{path}\"')`
  which is unsafe for paths containing spaces or shell metachars.
  Now uses `subprocess.run([...], check=False)` with an argument
  list, so the path is never reparsed by a shell.

* **`ModernProgressbar` resize storm**
  Tk fires one `<Configure>` per pixel during a drag.  Added
  `_apply_resize` + a debounced `after(16 ms)` so resizing the
  window only repaints once per frame.

### P2 \u2014 UI architecture

* **`_IconFactory` lifted out of `ui.py`**
  Moved into `widgets.py` (where `make_favicon_chip` and the favicon
  loader already lived).  `ui.py` shrank by 3.3 KB.

* **`sdt_app/messages.py` for i18n readiness**
  Centralised all UI strings under a `M = {...}` dict plus a `t(key)`
  template helper.  No `t()` migration has been done in `ui.py` yet
  (the dict is in place for future work).

* **`_level_of_message` in `ui.py`**
  Replaces the deleted `_detect_log_level` from `logging_service.py`
  and classifies INFO / WARNING / ERROR / SUCCESS by keyword
  detection.  Required because the original `_detect_log_level` was
  removed during a refactor and `_append_log` started throwing
  `NameError` \u2014 making the runtime log panel completely empty.

* **`_summarise_for_ui` deduplicated**
  Earlier refactors left two copies of the helper in
  `logging_service.py`; the second silently overrode the first.
  The duplicate (and the stray `UI_MIN_LEVEL` block between them)
  has been removed.

### Documentation

* `README.md` \u2014 SSH host-key section rewritten to describe the three
  control surfaces (toolbar toggle / env var / startup INFO) and the
  troubleshooting recipe for `SSHException: No matching host key`.
* `DESIGN.md` \u2014 Refinements-vs-v1 section covers the favicon,
  schedule strip, and log colouring decisions.

## Test coverage notes

* 31 unit tests across `tests/test_config_loader.py`,
  `test_interruptible.py`, `test_output.py`, `test_read_loop.py`,
  `test_scheduler.py`, `test_stop.py`.
* New unit tests **not yet added** (low-risk, low-value gaps):
  * `models.Device.display_type` / `resolved_protocol`
  * `inspection_service._run_device` end-to-end with a stub executor
  * `widgets.IconFactory` rendering of state combinations
  * `output.has_prompt` exhaustive Chinese / English prompt fixtures
  * `paths.open_in_file_manager` subprocess arguments

## Open items / known gaps

These are documented but **not** actioned yet:

* **`ui.py` is 54 KB** with 45 methods on `InspectionUI`.  Further
  refactor would require splitting state / view / event-handling
  into separate modules.  Risk vs reward is unfavourable until the
  function growth slows.
* **`messages.py` is unused by `ui.py`**.  Migration of the 80+
  hard-coded Chinese strings to `t("key")` calls is mechanical and
  isolated; a future i18n PR can do it without touching business
  logic.
* **`InspectionEvent` is `frozen=True` but nests the mutable
  `result: Optional[InspectionResult]`**.  Documented; behaviour is
  correct; the asymmetry is a known dataclass limitation.