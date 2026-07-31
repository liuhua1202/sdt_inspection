"""Windows taskbar icon helper.

Why this exists: a single ``iconbitmap()`` call is not enough on
Windows 10/11.

* ``iconbitmap()`` only sets the per-window ``WM_SETICON`` icon, which
  the taskbar / Alt-Tab do **not** always show consistently.
* Windows 10/11 taskbar + the modern Start menu / virtual desktop
  hint panel all read the **class** icon (``WNDCLASSEX.HICON``).
* Tk will reset the class icon back to its default during
  ``Toplevel.__init__`` and the first paint event, so we have to
  re-apply it on a timer.

This module applies both layers (per-window + class) and retries
the class-level set for up to 60 seconds so the taskbar icon sticks.
"""
from __future__ import annotations

import os
import sys

from . import paths as _paths

# Module-level so the user can ``apply_icon(self.root)`` without
# importing anything else.
def _resolve_icon_path() -> str | None:
    """Return the absolute path to ``favicon.ico`` or ``None``.

    Delegates to ``paths.find_favicon()`` so every module that needs
    the logo uses the same search order (BASE_DIR first, then DATA_DIR).
    """
    p = _paths.find_favicon()
    return str(p) if p is not None else None


# =====================================================================
#  Public entry point
# =====================================================================
def apply_icon(window) -> None:
    """Set the window + class icons for the given Toplevel / Tk root.

    Safe to call on every platform: on non-Windows it falls back to
    Tk's cross-platform ``iconphoto``; on Windows it also drives
    ``WM_SETICON`` and ``SetClassLongPtrW`` so the taskbar shows the
    operator's ``favicon.ico`` instead of the generic Python icon.
    """
    ico_path = _resolve_icon_path()
    if not ico_path:
        return

    # 1) Cross-platform photo icon.  This drives dock / Unity
    # launcher icons on Linux and macOS, and is also used by Tk as
    # a fallback for the taskbar.
    try:
        from PIL import Image, ImageTk  # type: ignore
        pil_img = Image.open(ico_path)
        # Prefer a size-matched frame from the .ico so the window
        # title-bar matches what the user sees in favicon.ico.  A
        # 32 px icon is the right size for the title bar / window
        # decoration.
        ico = getattr(pil_img, "ico", None)
        if ico is not None and (32, 32) in ico.sizes():
            pil_img = ico.getimage((32, 32))
        else:
            pil_img = pil_img.convert("RGBA").resize(
                (32, 32), Image.Resampling.LANCZOS)
        # Keep transparency so the favicon's alpha channel is
        # preserved (the previous version flattened onto white,
        # which changed the visual appearance of the icon).
        if pil_img.mode != "RGBA":
            pil_img = pil_img.convert("RGBA")
        window.iconphoto(False, ImageTk.PhotoImage(pil_img))
    except Exception as exc:
        print(f'[apply_icon] iconphoto failed: {exc}', file=sys.stderr)

    # 2) Windows-specific: per-window + class-level via Win32 APIs.
    if sys.platform == 'win32':
        try:
            window.iconbitmap(ico_path)
        except Exception as exc:
            print(f'[apply_icon] iconbitmap failed: {exc}', file=sys.stderr)

        try:
            _apply_icon_win32(window, ico_path)
        except Exception as exc:
            print(f'[apply_icon] win32 hook failed: {exc}', file=sys.stderr)

        # 3) Tk resets the class icon during the first paint.  Re-apply
        # for up to ~60 seconds with exponentially-spaced retries so
        # the taskbar ends up showing our icon, not the default
        # python.exe / Tk icon.
        def _retry() -> None:
            try:
                _apply_icon_win32(window, ico_path)
            except Exception:
                pass

        for ms in (50, 150, 300, 600, 1200, 2500, 5000,
                   10000, 20000, 35000, 50000, 60000):
            try:
                window.after(ms, _retry)
            except Exception:
                break


# =====================================================================
#  Win32 implementation
# =====================================================================
def _apply_icon_win32(window, ico_path: str) -> None:
    """Set the Win32 taskbar + title-bar icons directly.

    HWND discovery is the trickiest part because Tk 8.6 + Win11 + Python
    3.14 returns the **child** HWND from ``winfo_id()`` rather than
    the top-level one.  We try ``wm frame`` first (works on classic
    Tk), fall back to ``winfo_id()`` (works on the new behaviour),
    and verify the result really is a top-level window before
    touching its class icon.
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)

    LR_LOADFROMFILE = 0x00000010
    LR_SHARED = 0x00008000
    IMAGE_ICON = 1
    WM_SETICON = 0x0080
    WM_GETICON = 0x007F
    ICON_BIG = 1
    ICON_SMALL = 0
    GCLP_HICON = -14
    GCLP_HICONSM = -34
    GA_PARENT = 1

    # 1) Find the top-level HWND
    hwnd_int: int | None = None
    try:
        frame_id = window.tk.call('wm', 'frame', window._w)
        s = str(frame_id).strip()
        hwnd_int = int(s, 16) if s.startswith(('0x', '0X')) else int(s)
    except Exception:
        pass
    if hwnd_int is None:
        hwnd_int = int(window.winfo_id())
    hwnd = wintypes.HWND(hwnd_int)

    # 2) Verify it is a real top-level window.  Modern Tk + Win11
    # returns a TkChild (whose parent is the desktop) rather than the
    # TkTopLevel wrapper, so we walk up to GA_PARENT and check the
    # class name is the desktop class.
    GetParent = user32.GetParent
    GetParent.argtypes = [wintypes.HWND]
    GetParent.restype = wintypes.HWND

    GetAncestor = user32.GetAncestor
    GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    GetAncestor.restype = wintypes.HWND

    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int

    ga_parent = GetAncestor(hwnd, GA_PARENT)
    desktop_class = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(ga_parent, desktop_class, 256)
    parent = GetParent(hwnd)

    if parent != wintypes.HWND(0) and desktop_class.value != '#32769':
        return  # Not a top-level window; skip class-level changes.

    # 3) ctypes-friendly signatures.  The 4-argument argtypes lists
    # for the stdcall calls below prevent crashes on 64-bit Python.
    LoadImageW = user32.LoadImageW
    LoadImageW.argtypes = [
        wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    LoadImageW.restype = wintypes.HANDLE

    SendMessageW = user32.SendMessageW
    SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    SendMessageW.restype = ctypes.c_ssize_t

    SetClassLongPtrW = user32.SetClassLongPtrW
    SetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    SetClassLongPtrW.restype = ctypes.c_ssize_t

    # 4) Load both sizes we care about: 16 for the taskbar, 32 for
    # the title bar / Alt-Tab.  Tk only stores the 16-pixel version
    # by default, which makes the title bar look blurry.
    #
    # ``LR_SHARED`` tells Windows to manage the HICON lifetime: the
    # system keeps a single cached icon per resource and the
    # caller's handle is valid for the process lifetime.  Without
    # it, the previous HICON owned by ``WM_SETICON`` /
    # ``SetClassLongPtrW`` would leak every time we re-applied the
    # icon (60 seconds of retries after launch = 13 leaks per
    # process).
    load_flags = LR_LOADFROMFILE | LR_SHARED
    hicon_small = LoadImageW(None, ico_path, IMAGE_ICON, 16, 16, load_flags)
    hicon_big = LoadImageW(None, ico_path, IMAGE_ICON, 32, 32, load_flags)

    # 5) Per-window icon (WM_SETICON).  This updates the title bar
    # and the Alt-Tab preview immediately.
    if hicon_small:
        SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
    if hicon_big:
        SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)

    # 6) Class-level icon (SetClassLongPtrW).  This is what Windows
    # reads for the taskbar; without it the taskbar shows Tk's
    # default icon regardless of WM_SETICON.
    if hicon_big:
        try:
            SetClassLongPtrW(hwnd, GCLP_HICON, hicon_big)
        except Exception:
            pass
    if hicon_small:
        try:
            SetClassLongPtrW(hwnd, GCLP_HICONSM, hicon_small)
        except Exception:
            pass