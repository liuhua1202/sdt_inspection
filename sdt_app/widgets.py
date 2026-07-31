"""Light-theme custom Tk / ttk widgets for the SDT inspection tool.



The widgets module is intentionally self-contained so the rest of the

UI can treat colors, sizing and motion as design tokens.

"""



from __future__ import annotations

from . import paths as _paths


# Resolved once at import time so the rest of the module can use a
# plain Path instead of repeating the lookup at every render.
FAVICON_PATH = _paths.find_favicon() or (_paths.BASE_DIR / 'favicon.ico')




import math

import tkinter as tk

from tkinter import DoubleVar

from typing import Optional



try:

    from PIL import Image, ImageDraw, ImageTk

    PIL_AVAILABLE = True

except ImportError:  # pragma: no cover - Pillow is optional

    PIL_AVAILABLE = False





# =====================================================================

#  Light-theme design tokens

# =====================================================================

# Tokens are referenced both by ttk.Style (via literal colors) and by

# the custom widgets below.  Keep them aligned with the values used in

# ``ui._setup_styles`` so the whole surface stays consistent.



# Surfaces ------------------------------------------------------------

COLOR_BG_APP = "#F4F6FB"          # window background (very light blue-grey)

COLOR_BG_CARD = "#FFFFFF"         # primary card surface

COLOR_BG_SUBTLE = "#F8FAFC"       # inside-card subtle background

COLOR_BG_ELEVATED = "#F1F5F9"     # hover / selected row

COLOR_BG_INPUT = "#FFFFFF"        # input fields



# Borders -------------------------------------------------------------

COLOR_BORDER = "#E2E8F0"          # default card border

COLOR_BORDER_SUBTLE = "#EEF2F7"   # row separator / table grid

COLOR_BORDER_STRONG = "#CBD5E1"   # focused / hovered border



# Text ----------------------------------------------------------------

COLOR_TEXT_PRIMARY = "#0F172A"    # titles

COLOR_TEXT_BODY = "#1F2937"       # body copy

COLOR_TEXT_MUTED = "#64748B"      # labels / hints

COLOR_TEXT_DISABLED = "#94A3B8"   # disabled text



# Brand & status ------------------------------------------------------

COLOR_BRAND = "#2563EB"           # primary brand blue (CTA / progress)

COLOR_BRAND_DEEP = "#1D4ED8"      # brand hover

COLOR_BRAND_DARK = "#1E3A8A"      # headings on light surfaces

COLOR_BRAND_TINT = "#EFF6FF"      # brand 50 background

COLOR_BRAND_TINT_2 = "#DBEAFE"    # brand 100 background / hover



COLOR_SUCCESS = "#16A34A"

COLOR_SUCCESS_BG = "#DCFCE7"

COLOR_SUCCESS_BORDER = "#BBF7D0"



COLOR_DANGER = "#DC2626"

COLOR_DANGER_BG = "#FEE2E2"

COLOR_DANGER_BORDER = "#FECACA"



COLOR_WARNING = "#D97706"

COLOR_WARNING_BG = "#FEF3C7"



COLOR_INFO = "#0EA5E9"

COLOR_INFO_BG = "#E0F2FE"



# Progress ------------------------------------------------------------

COLOR_PROGRESS_TRACK = "#E2E8F0"

COLOR_PROGRESS_FILL = COLOR_BRAND



# Trough for the legacy card-progress background; kept for backwards

# compatibility with the original code path.

COLOR_TRACK_LEGACY = "#E5E7EB"



# Typography ----------------------------------------------------------

FONT_FAMILY_UI = "Microsoft YaHei UI"

FONT_FAMILY_FALLBACK = "Microsoft YaHei"

FONT_FAMILY_MONO = "Cascadia Code"

FONT_FAMILY_MONO_FALLBACK = "Consolas"



# Motion --------------------------------------------------------------

ANIMATION_DURATION_MS = 320

ANIMATION_STEP_MS = 16



# Sizing --------------------------------------------------------------

PROGRESSBAR_HEIGHT = 6

PROGRESSBAR_HEIGHT_LARGE = 8

PROGRESSBAR_CORNER_RADIUS = 4





__all__ = [

    "COLOR_BG_APP",

    "COLOR_BG_CARD",

    "COLOR_BORDER",

    "COLOR_BRAND",

    "COLOR_BRAND_DEEP",

    "COLOR_BRAND_DARK",

    "COLOR_SUCCESS",

    "COLOR_DANGER",

    "FONT_FAMILY_UI",

    "ModernProgressbar",

    "IconFactory",

]





# =====================================================================

#  ModernProgressbar

# =====================================================================

class ModernProgressbar(tk.Canvas):

    """Modern, rounded, animated progressbar.



    Exposes the same interface as a ``ttk.Progressbar`` so it can be

    swapped in transparently:



    * ``variable=DoubleVar`` for live binding (0 .. maximum)

    * ``set(value, animate=True)`` to drive the bar manually

    * ``get()`` to read the current value



    Animation rules

    ---------------

    * Forward motion (target > current) animates over 320ms (60fps).

    * Backwards / reset (``target <= current``) snaps instantly so the

      bar never visibly rolls back.

    """



    def __init__(

        self,

        parent,

        variable: Optional[DoubleVar] = None,

        maximum: float = 100,

        bar_height: Optional[int] = None,

        trough_color: Optional[str] = None,

        fill_color: Optional[str] = None,

        corner_radius: Optional[int] = None,

        bg: Optional[str] = None,

        **kwargs,

    ) -> None:

        if bar_height is None:

            bar_height = PROGRESSBAR_HEIGHT

        if corner_radius is None:

            corner_radius = PROGRESSBAR_CORNER_RADIUS

        if bg is None:

            try:

                bg = parent.cget("bg") or COLOR_BG_CARD

            except tk.TclError:

                bg = COLOR_BG_CARD



        super().__init__(

            parent,

            height=bar_height,

            highlightthickness=0,

            bd=0,

            bg=bg,

            **kwargs,

        )



        self._bar_height = bar_height

        self._corner_radius = min(max(0, corner_radius), bar_height // 2)

        self._trough_color = trough_color or COLOR_PROGRESS_TRACK

        self._fill_color = fill_color or COLOR_PROGRESS_FILL

        self._variable = variable

        self._maximum = maximum

        self._tween = None

        self._after_id = None

        self._internal_value = 0.0



        self._trough_rect = self.create_polygon(

            self._rounded_rect_points(0, 0, 0, bar_height, self._corner_radius),

            fill=self._trough_color,

            outline=self._trough_color,

            smooth=True,

            width=0,

        )

        self._fill_rect = self.create_polygon(

            self._rounded_rect_points(0, 0, 0, bar_height, self._corner_radius),

            fill=self._fill_color,

            outline=self._fill_color,

            smooth=True,

            width=0,

        )

        self.bind("<Configure>", self._on_resize)

        if self._variable is not None:

            self._variable.trace_add("write", self._on_var_changed)

            self._on_var_changed()



    # ------------------------------------------------------------------ helpers

    @staticmethod

    def _rounded_rect_points(x1, y1, x2, y2, r):

        """Generate a polygon point list approximating a rounded rect."""

        if x2 - x1 < 2 * r or y2 - y1 < 2 * r or r <= 0:

            return [x1, y1, x2, y1, x2, y2, x1, y2]

        steps = 6

        pts = []

        # top-left

        pts.extend([x1, y1 + r])

        for i in range(steps + 1):

            angle = math.pi + (math.pi / 2) * (i / steps)

            pts.extend([x1 + r + r * math.cos(angle), y1 + r + r * math.sin(angle)])

        # top-right

        pts.extend([x1 + r, y1])

        for i in range(steps + 1):

            angle = -math.pi / 2 + (math.pi / 2) * (i / steps)

            pts.extend([x2 - r + r * math.cos(angle), y1 + r + r * math.sin(angle)])

        # bottom-right

        pts.extend([x2, y1 + r])

        for i in range(steps + 1):

            angle = 0 + (math.pi / 2) * (i / steps)

            pts.extend([x2 - r + r * math.cos(angle), y2 - r + r * math.sin(angle)])

        # bottom-left

        pts.extend([x2 - r, y2])

        for i in range(steps + 1):

            angle = math.pi / 2 + (math.pi / 2) * (i / steps)

            pts.extend([x1 + r + r * math.cos(angle), y2 - r + r * math.sin(angle)])

        return pts



    def _read_value(self) -> float:

        if self._variable is not None:

            try:

                return float(self._variable.get())

            except (tk.TclError, ValueError):

                return 0.0

        return self._internal_value



    def _write_value(self, value: float) -> None:

        if self._variable is not None:

            try:

                self._variable.set(value)

            except tk.TclError:

                pass

        else:

            self._internal_value = float(value)



    # ------------------------------------------------------------------ repaint

    _RESIZE_DEBOUNCE_MS = 16  # ~one frame at 60fps



    def _on_resize(self, event=None) -> None:

        # Debounce resize events: Tk fires one per pixel during a

        # drag, so we coalesce them into a single repaint after

        # the resize has settled.

        if getattr(self, "_resize_after_id", None) is not None:

            try:

                self.after_cancel(self._resize_after_id)

            except tk.TclError:

                pass

        try:

            self._resize_after_id = self.after(

                self._RESIZE_DEBOUNCE_MS, self._apply_resize,

            )

        except tk.TclError:

            pass



    def _apply_resize(self) -> None:

        w = self.winfo_width()

        h = self._bar_height

        self.coords(

            self._trough_rect,

            self._rounded_rect_points(0, 0, w, h, self._corner_radius),

        )

        self.itemconfigure(self._trough_rect, fill=self._trough_color, outline=self._trough_color)

        self._redraw_fill()



    def _on_var_changed(self, *args) -> None:

        self._redraw_fill()



    def _redraw_fill(self) -> None:

        val = self._read_value()

        ratio = max(0.0, min(1.0, val / float(self._maximum or 1)))

        w = self.winfo_width()

        fill_w = int(w * ratio)

        if fill_w <= 0:

            self.coords(self._fill_rect, [0, 0, 0, 0])

            return

        if fill_w < 2 * self._corner_radius:

            pts = [0, 0, fill_w, 0, fill_w, self._bar_height, 0, self._bar_height]

        else:

            pts = self._rounded_rect_points(0, 0, fill_w, self._bar_height, self._corner_radius)

        self.coords(self._fill_rect, pts)

        self.itemconfigure(self._fill_rect, fill=self._fill_color, outline=self._fill_color)



    # ------------------------------------------------------------------ public

    def set(self, value, animate: Optional[bool] = None) -> None:

        try:

            target = float(value)

        except (TypeError, ValueError):

            target = 0.0

        target = max(0.0, min(float(self._maximum or 1), target))

        current = self._read_value()

        if animate is None:

            animate = target > current

        if animate:

            self._animate_to(target)

        else:

            self._write_value(target)

            self._cancel_pending_tick()



    def get(self) -> float:

        return self._read_value()



    # ------------------------------------------------------------------ animation

    def _animate_to(self, target: float, duration_ms: int = ANIMATION_DURATION_MS) -> None:

        start = self._read_value()

        delta = target - start

        if abs(delta) < 0.5:

            self._write_value(target)

            self._cancel_pending_tick()

            return

        steps = max(1, int(duration_ms / ANIMATION_STEP_MS))

        self._tween = {"delta": delta / steps, "left": steps, "target": target}

        self._tick_animation()



    def _tick_animation(self) -> None:

        tween = self._tween

        if not tween:

            return

        if tween["left"] <= 0:

            self._write_value(tween["target"])

            self._cancel_pending_tick()

            return

        self._write_value(self._read_value() + tween["delta"])

        tween["left"] -= 1

        self._after_id = self.after(ANIMATION_STEP_MS, self._tick_animation)



    def _cancel_pending_tick(self) -> None:

        self._tween = None

        aid = getattr(self, "_after_id", None)

        if aid:

            try:

                self.after_cancel(aid)

            except tk.TclError:

                pass

            self._after_id = None



    def destroy(self) -> None:

        self._cancel_pending_tick()

        super().destroy()









# =====================================================================

#  Favicon loader (anti-aliased multi-size)

# =====================================================================

def load_favicon_icons(path, sizes=(16, 24, 32, 48, 64, 128, 256)):

    """Load a .ico file via PIL and pre-render it at each requested size.



    Uses LANCZOS resampling for crisp, anti-aliased edges and returns

    a dict mapping ``size -> ImageTk.PhotoImage``.  ``None`` if PIL is

    unavailable or the file is missing.

    """

    if not PIL_AVAILABLE:

        return None

    try:

        source = Image.open(path)

    except (OSError, FileNotFoundError):

        return None

    # Convert to a uniform RGBA canvas so we can composite onto a known

    # background (the original ICO can have transparent pixels).

    source = source.convert("RGBA")

    icons = {}

    for size in sizes:

        canvas = Image.new("RGBA",

                           (size, size),

                           (255, 255, 255, 0))

        resampled = source.resize(

            (size, size), Image.Resampling.LANCZOS)

        canvas.alpha_composite(resampled)

        icons[size] = ImageTk.PhotoImage(canvas)

    return icons





def _build_favicon_image(path, size=48):
    """
    Load favicon.ico and render it at the given pixel size.

    Prefers the size-matched frame embedded in the .ico (e.g. the
    48x48 frame for a 48 px render) so the in-app icon matches
    what the user sees when they open favicon.ico directly.  Falls
    back to LANCZOS resampling from the largest frame when no
    exact match exists.  Returns ``None`` if the file is missing
    or PIL is unavailable.
    """
    if not PIL_AVAILABLE:
        return None
    try:
        source = Image.open(path)
    except (OSError, FileNotFoundError):
        return None

    ico = getattr(source, "ico", None)
    if ico is not None and (size, size) in ico.sizes():
        # The .ico already has a hand-drawn frame at this exact size;
        # use it as-is for pixel-perfect parity with the file on disk.
        return ico.getimage((size, size)).convert("RGBA")
    return source.convert("RGBA").resize(
        (size, size), Image.Resampling.LANCZOS)


# Lazy cache of rendered favicon frames.  ``_build_favicon_image``
# reads the .ico every time, but the in-app icon is loaded once at
# startup and reused, so a tiny cache avoids redundant disk hits.
_FAVICON_CACHE: dict[int, "Image.Image | None"] = {}


def HIGH_RES_FAVICON(size: int = 48):
    """Return the favicon rendered at the given pixel size.

    Uses the size-matched frame from favicon.ico when one exists so
    the rendered icon is pixel-identical to opening the file
    directly.  Falls back to LANCZOS resampling from the largest
    frame when the requested size is not in the .ico.
    """
    if size not in _FAVICON_CACHE:
        _FAVICON_CACHE[size] = _build_favicon_image(
            str(FAVICON_PATH), size=size)
    return _FAVICON_CACHE[size]


def get_window_icon(window, size=32):
    """
    Bind a PIL-rendered favicon to ``window.iconphoto`` so
    "Tk shows our logo in the title bar / window manager
    "hints.  On Windows the taskbar icon is driven by
    "icon_helper.apply_icon; this helper is the fallback
    "for other platforms and for Tk windows that are not
    "the application root.
    """
    img = HIGH_RES_FAVICON(size=size)
    if img is None:
        return
    try:
        from PIL import ImageTk
        window.iconphoto(False, ImageTk.PhotoImage(img))
    except Exception:
        pass

def make_favicon_chip(path, size=36, background=None,

                      corner_radius=8, padding=0):

    """Render the favicon inside a rounded card-style chip.



    Useful for the TopBar where the logo sits on a white card and

    needs a subtle tinted background.

    """

    if not PIL_AVAILABLE:

        return None

    try:

        source = Image.open(path).convert("RGBA")

    except (OSError, FileNotFoundError):

        return None

    scale = 4

    box = size + padding * 2

    px = box * scale

    canvas = Image.new("RGBA", (px, px), (255, 255, 255, 0))

    draw = ImageDraw.Draw(canvas)

    bg = background or COLOR_BRAND_TINT

    if padding > 0:

        draw.rounded_rectangle(

            (0, 0, px - 1, px - 1),

            radius=corner_radius * scale,

            fill=bg,

        )

    # Center the icon inside the padded area.

    icon_size = size * scale

    icon = source.resize(

        (icon_size, icon_size), Image.Resampling.LANCZOS)

    offset = (padding * scale, padding * scale)

    canvas.alpha_composite(icon, dest=offset)

    return ImageTk.PhotoImage(

        canvas.resize((box, box), Image.Resampling.LANCZOS))





# =====================================================================

#  Log colour tokens (ported from network_inspection/ui/theme.py)





class IconFactory:

    """

    Build tiny icons via PIL. Cached per (name, size, color).



    Used by the inspection UI for checkbox states, the schedule

    switch, and other inline glyphs.  Lifted from ui.py so the

    presentation layer can stay free of PIL details.

    """



    def __init__(self):

        self.cache = {}



    def _draw(self, key, drawer, size, scale=4):

        if not PIL_AVAILABLE or key in self.cache:

            return

        s = size * scale

        img = Image.new("RGBA", (s, s), (255, 255, 255, 0))

        draw = ImageDraw.Draw(img)

        drawer(draw, s, scale)

        self.cache[key] = ImageTk.PhotoImage(

            img.resize((size, size), Image.Resampling.LANCZOS))



    def checkbox(self, checked, size=18):

        # f-string: 'cb-on-{size}' or 'cb-off-{size}'

        key = "cb-" + ("on" if checked else "off") + "-" + str(size)

        if key in self.cache:

            return self.cache[key]



        def build(draw, s, scale):

            box = (scale, scale, s - scale, s - scale)

            if checked:

                draw.rounded_rectangle(

                    box, radius=4 * scale,

                    fill=COLOR_BRAND, outline=COLOR_BRAND, width=scale)

                draw.line(

                    [(5 * scale, 9 * scale), (8 * scale, 12 * scale),

                     (14 * scale, 5 * scale)],

                    fill="#FFFFFF", width=2 * scale, joint="curve")

            else:

                draw.rounded_rectangle(

                    box, radius=4 * scale,

                    fill="#FFFFFF", outline=COLOR_BORDER_STRONG, width=scale)



        self._draw(key, build, size=size)

        return self.cache.get(key)



    def switch_track(self, on, size=(36, 20)):

        """

        Render an iOS-style toggle at the requested (w, h).



        Uses a non-square canvas so the rounded-rectangle track

        and circular knob render at their true aspect ratio.

        """

        # f-string: 'sw-on-{w}x{h}' or 'sw-off-{w}x{h}'

        k = "sw-" + ("on" if on else "off") + "-" + str(size[0]) + "x" + str(size[1])

        if k in self.cache:

            return self.cache[k]

        if not PIL_AVAILABLE:

            return None

        scale = 4

        w, h = size

        sw, sh = w * scale, h * scale

        img = Image.new("RGBA", (sw, sh), (255, 255, 255, 0))

        draw = ImageDraw.Draw(img)

        track_color = COLOR_BRAND if on else "#CBD5E1"

        draw.rounded_rectangle(

            (0, 0, sw - 1, sh - 1),

            radius=sh // 2, fill=track_color,

        )

        knob_left = (sw - sh + 2 * scale) if on else 2 * scale

        draw.ellipse(

            (knob_left, 2 * scale,

             knob_left + (sh - 4 * scale), sh - 2 * scale),

            fill="#FFFFFF",

        )

        self.cache[k] = ImageTk.PhotoImage(

            img.resize(size, Image.Resampling.LANCZOS))

        return self.cache.get(k)

# =====================================================================

# Foreground colours used to highlight log lines in the runtime log

# panel.  The values match the LOG_COLORS map from

# network_inspection so the two tools stay visually consistent.

LOG_COLOR_DEBUG = "#6B7280"     # gray-500

LOG_COLOR_INFO = "#0F6FC6"      # brand blue

LOG_COLOR_WARNING = "#EA580C"   # orange-600

LOG_COLOR_ERROR = "#DC2626"     # red-600

LOG_COLOR_SUCCESS = "#15803D"   # green-700

LOG_COLOR_CRITICAL = "#DC2626"  # red-600 (same as ERROR)

LOG_COLOR_TIMESTAMP = "#94A3B8" # slate-400 (muted prefix)



LOG_COLORS = {

    "DEBUG": LOG_COLOR_DEBUG,

    "INFO": LOG_COLOR_INFO,

    "WARNING": LOG_COLOR_WARNING,

    "ERROR": LOG_COLOR_ERROR,

    "SUCCESS": LOG_COLOR_SUCCESS,

    "CRITICAL": LOG_COLOR_CRITICAL,

}



# Tag names used by the Text widget.  Distinct from level names so we

# can also style other markup (e.g. timestamps).

LOG_TAG_TIMESTAMP = "log-timestamp"

LOG_TAG_LEVELS = tuple(LOG_COLORS.keys())

