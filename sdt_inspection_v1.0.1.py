"""Launcher kept under the original file name for backward compatibility.

PyInstaller already injects ``pyi_rth__tkinter.py`` which sets
``TCL_LIBRARY`` and ``TK_LIBRARY`` to ``_internal/_tcl_data`` and
``_internal/_tk_data`` before any of our code runs.  This launcher
therefore just needs to import and call ``sdt_app.ui.run``.

The Tcl/Tk runtime fixup previously inlined here was removed because
it duplicated (and on some PyInstaller builds conflicted with) the
official runtime hook.
"""

from sdt_app.ui import run


if __name__ == "__main__":
    run()
