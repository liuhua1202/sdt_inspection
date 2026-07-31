"""Light-theme Tkinter UI for the modular SDT inspection application."""

from __future__ import annotations

import os
import re
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageDraw, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from .config_loader import DEFAULT_ENCODINGS, load_commands, load_devices, load_project
from .widgets import (
    COLOR_BG_APP, COLOR_BG_CARD, COLOR_BG_ELEVATED, COLOR_BG_SUBTLE,
    COLOR_BORDER, COLOR_BORDER_STRONG, COLOR_BORDER_SUBTLE,
    COLOR_BRAND, COLOR_BRAND_DEEP, COLOR_BRAND_DARK,
    COLOR_BRAND_TINT, COLOR_BRAND_TINT_2,
    COLOR_DANGER, COLOR_SUCCESS,
    COLOR_TEXT_BODY, COLOR_TEXT_MUTED, COLOR_TEXT_PRIMARY, COLOR_WARNING,
    FONT_FAMILY_FALLBACK, FONT_FAMILY_MONO_FALLBACK, FONT_FAMILY_UI,
    LOG_COLOR_TIMESTAMP, LOG_COLORS, LOG_TAG_LEVELS, LOG_TAG_TIMESTAMP,
    ModernProgressbar, IconFactory, load_favicon_icons, make_favicon_chip,
    HIGH_RES_FAVICON, get_window_icon,
)
from .inspection_service import InspectionService
from .scheduler import PeriodicScheduler
from .logging_service import AppLogger
from .icon_helper import apply_icon
from .models import Device, InspectionEvent, ResultStatus
from .paths import (
    COMMANDS_DIR, CONFIG_DIR, LOG_DIR, ensure_directories, open_in_file_manager,
)


# Weekday labels shown in the schedule dropdown (1=Mon ... 7=Sun).
WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"]
WEEKDAY_INDEX = {label: i + 1 for i, label in enumerate(WEEKDAY_LABELS)}


class InspectionUI:
    WINDOW_BG = COLOR_BG_APP
    APP_PAD_X = 16
    APP_PAD_Y = 14
    GAP = 10

    def __init__(self, root):
        self.root = root
        self.root.title("SDT \u7f51\u7edc\u8bbe\u5907\u5de1\u68c0")
        self.root.geometry("1240x780")
        self.root.minsize(1040, 660)
        self._set_icon()
        self.icons = IconFactory()

        # Bounded event queue: when the UI thread is frozen (modal
        # dialog, system sleep, etc.) the workers must not be able
        # to grow the queue without bound.  10k events is ~17 minutes
        # of buffer at the 100 ms polling cadence, which is plenty
        # of headroom for an operator-driven inspection run.  We
        # also switch every producer to ``put_nowait`` and silently
        # drop on overflow; the persistent log file is the source of
        # truth and the UI is a transient view.
        self.events: Queue = Queue(maxsize=10000)
        self._dropped_event_count = 0
        self.logger = AppLogger(self.events)
        self.service = InspectionService(self.events)
        self.scheduler = PeriodicScheduler()
        self.devices = []
        self.device_types = {}
        self.commands_by_type = {}
        self.tree_items = {}
        self.visible_indices = {}
        self.inspection_running = False
        self.success_count = 0
        self.failed_count = 0
        self.cancelled_count = 0
        self.scheduler_tick_id = None

        self._create_variables()
        self._setup_styles()
        self._create_widgets()
        self._load_defaults()
        self.root.after(100, self._poll_events)
        self.scheduler_tick_id = self.root.after(1000, self._scheduler_tick)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _set_icon(self):
        # On Windows, apply_icon drives the class-level icon so the
        # taskbar shows our favicon (iconbitmap only sets WM_SETICON,
        # which the taskbar ignores).  On other platforms this falls
        # back to iconphoto + iconbitmap via icon_helper.
        apply_icon(self.root)

    def _create_variables(self):
        self.status_var = tk.StringVar(value="\u6b63\u5728\u52a0\u8f7d\u914d\u7f6e...")
        self.progress_var = tk.DoubleVar(value=0)
        self.concurrency_var = tk.StringVar(value="5")
        self.encoding_var = tk.StringVar(value="\u81ea\u52a8\u68c0\u6d4b")
        self.devices_file_var = tk.StringVar(value="\u8bbe\u5907\u5217\u8868\uff1a\u672a\u52a0\u8f7d")
        self.commands_file_var = tk.StringVar(value="\u547d\u4ee4\u914d\u7f6e\uff1a\u672a\u52a0\u8f7d")
        self.total_var = tk.StringVar(value="0")
        self.success_var = tk.StringVar(value="0")
        self.failed_var = tk.StringVar(value="0")
        self.running_var = tk.StringVar(value="\u2014")
        self.search_var = tk.StringVar()
        self.visible_count_var = tk.StringVar(value="\u663e\u793a 0/0")
        self.schedule_check_text_var = tk.StringVar(value="\u542f\u7528\u5b9a\u65f6\u5de1\u68c0")
        self.schedule_enabled_var = tk.BooleanVar(value=False)
        self.schedule_frequency_var = tk.StringVar(value="\u5929")
        self.schedule_day_var = tk.StringVar(value="1")
        self.schedule_hour_var = tk.StringVar(value="09")
        self.schedule_minute_var = tk.StringVar(value="00")
        self.schedule_weekday_var = tk.StringVar(value=WEEKDAY_LABELS[0])
        self.next_schedule_var = tk.StringVar(value="\u4e0b\u6b21\u5de1\u68c0\uff1a\u672a\u542f\u7528")
        # SSH host-key policy.  Defaults to the
        # SDT_STRICT_HOST_KEYS env var so existing
        # deployments keep working unchanged.
        self.strict_host_keys_var = tk.BooleanVar(
            value=os.getenv("SDT_STRICT_HOST_KEYS", "0") == "1",
        )

    def _setup_styles(self):
        self.root.configure(bg=self.WINDOW_BG)
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        ui_font = (FONT_FAMILY_UI, 10)
        ui_font_bold = (FONT_FAMILY_UI, 10, "bold")
        body_font = (FONT_FAMILY_UI, 9)
        small_font = (FONT_FAMILY_UI, 9)
        title_font = (FONT_FAMILY_UI, 16, "bold")
        subtitle_font = (FONT_FAMILY_UI, 9)

        style.configure("App.TFrame", background=self.WINDOW_BG)
        style.configure("Card.TFrame", background=COLOR_BG_CARD,
                        borderwidth=0, relief="flat")
        style.configure("Card.Inner.TFrame", background=COLOR_BG_CARD)
        style.configure("Subtle.TFrame", background=COLOR_BG_SUBTLE)
        style.configure("Toolbar.TFrame", background=COLOR_BG_CARD)

        style.configure("Title.TLabel", background=self.WINDOW_BG,
                        foreground=COLOR_TEXT_PRIMARY, font=title_font,
                        padding=0)
        style.configure("Subtitle.TLabel", background=self.WINDOW_BG,
                        foreground=COLOR_TEXT_MUTED, font=subtitle_font)
        style.configure("Brand.TLabel", background=COLOR_BG_CARD,
                        foreground=COLOR_BRAND_DARK,
                        font=(FONT_FAMILY_UI, 13, "bold"))
        style.configure("CardTitle.TLabel", background=COLOR_BG_CARD,
                        foreground=COLOR_TEXT_PRIMARY, font=ui_font_bold)
        style.configure("CardHint.TLabel", background=COLOR_BG_CARD,
                        foreground=COLOR_TEXT_MUTED, font=body_font)
        style.configure("CardValue.TLabel", background=COLOR_BG_CARD,
                        foreground=COLOR_BRAND_DARK,
                        font=(FONT_FAMILY_UI, 22, "bold"))
        style.configure("Status.TLabel", background=COLOR_BG_CARD,
                        foreground=COLOR_TEXT_BODY, font=body_font, padding=6)
        style.configure("Muted.TLabel", background=COLOR_BG_CARD,
                        foreground=COLOR_TEXT_MUTED, font=small_font)
        style.configure("Schedule.TLabel", background=COLOR_BG_CARD,
                        foreground=COLOR_TEXT_BODY, font=body_font)

        style.configure("TButton",
                        background=COLOR_BG_CARD,
                        foreground=COLOR_TEXT_BODY,
                        bordercolor=COLOR_BORDER_STRONG,
                        borderwidth=1,
                        focusthickness=1,
                        focuscolor=COLOR_BRAND_TINT_2,
                        lightcolor=COLOR_BG_CARD,
                        darkcolor=COLOR_BG_CARD,
                        padding=(12, 6),
                        font=ui_font)
        style.map("TButton",
                  background=[("active", COLOR_BRAND_TINT_2),
                              ("disabled", COLOR_BG_SUBTLE)],
                  foreground=[("disabled", COLOR_BORDER_STRONG)],
                  bordercolor=[("focus", COLOR_BRAND)])

        style.configure("Accent.TButton",
                        background=COLOR_BRAND,
                        foreground="#FFFFFF",
                        bordercolor=COLOR_BRAND,
                        borderwidth=0,
                        focusthickness=0,
                        lightcolor=COLOR_BRAND,
                        darkcolor=COLOR_BRAND,
                        padding=(16, 8),
                        font=ui_font_bold)
        style.map("Accent.TButton",
                  background=[("active", COLOR_BRAND_DEEP),
                              ("disabled", "#BFDBFE")],
                  foreground=[("disabled", "#FFFFFF")])

        style.configure("Subtle.TButton",
                        background=COLOR_BG_SUBTLE,
                        foreground=COLOR_TEXT_BODY,
                        bordercolor=COLOR_BORDER,
                        padding=(10, 5),
                        font=body_font)
        style.map("Subtle.TButton",
                  background=[("active", COLOR_BG_ELEVATED)])

        style.configure("Subtle.TCheckbutton",
                        background=COLOR_BG_CARD,
                        foreground=COLOR_TEXT_BODY,
                        focuscolor=COLOR_BG_CARD,
                        indicatorcolor=COLOR_BG_CARD,
                        padding=(4, 2),
                        font=body_font)
        style.map("Subtle.TCheckbutton",
                  background=[("active", COLOR_BG_CARD)],
                  indicatorcolor=[("selected", COLOR_BRAND),
                                 ("pressed", COLOR_BRAND_DEEP)])

        style.configure("Treeview",
                        rowheight=32,
                        font=ui_font,
                        background=COLOR_BG_CARD,
                        fieldbackground=COLOR_BG_CARD,
                        foreground=COLOR_TEXT_BODY,
                        bordercolor=COLOR_BORDER_SUBTLE,
                        borderwidth=1)
        style.configure("Treeview.Heading",
                        font=(FONT_FAMILY_UI, 10, "bold"),
                        background=COLOR_BG_SUBTLE,
                        foreground=COLOR_TEXT_PRIMARY,
                        padding=(10, 8),
                        bordercolor=COLOR_BORDER_SUBTLE,
                        borderwidth=0,
                        relief="flat")
        style.map("Treeview.Heading",
                  background=[("active", COLOR_BG_ELEVATED)])
        style.map("Treeview",
                  background=[("selected", COLOR_BRAND_TINT)],
                  foreground=[("selected", COLOR_TEXT_PRIMARY)])

        style.configure("TSpinbox",
                        fieldbackground=COLOR_BG_CARD,
                        background=COLOR_BG_CARD,
                        foreground=COLOR_TEXT_BODY,
                        bordercolor=COLOR_BORDER,
                        arrowcolor=COLOR_TEXT_MUTED,
                        padding=(6, 4),
                        font=ui_font)
        style.configure("TCombobox",
                        fieldbackground=COLOR_BG_CARD,
                        background=COLOR_BG_CARD,
                        foreground=COLOR_TEXT_BODY,
                        bordercolor=COLOR_BORDER,
                        arrowcolor=COLOR_TEXT_MUTED,
                        padding=(6, 4),
                        font=ui_font)
        style.map("TCombobox",
                  fieldbackground=[("readonly", COLOR_BG_CARD)],
                  foreground=[("readonly", COLOR_TEXT_BODY)])
        style.configure("TEntry",
                        fieldbackground=COLOR_BG_CARD,
                        background=COLOR_BG_CARD,
                        foreground=COLOR_TEXT_BODY,
                        bordercolor=COLOR_BORDER,
                        padding=(8, 6),
                        font=ui_font)
        style.map("TEntry",
                  bordercolor=[("focus", COLOR_BRAND)])

        style.configure("TSeparator", background=COLOR_BORDER_SUBTLE)

    def _create_widgets(self):
        root_frame = ttk.Frame(self.root, style="App.TFrame")
        root_frame.pack(fill="both", expand=True,
                        padx=self.APP_PAD_X, pady=self.APP_PAD_Y)

        self._build_top_bar(root_frame)
        self._build_stat_cards(root_frame)
        self._build_toolbar(root_frame)
        self._build_schedule_strip(root_frame)
        self._build_body(root_frame)
        self._build_status_bar(root_frame)

    def _build_top_bar(self, parent):
        bar = ttk.Frame(parent, style="Card.TFrame", padding=(18, 14))
        bar.pack(fill="x", pady=(0, self.GAP))

        # Brand mark -- render the real favicon.ico as an anti-aliased
        # PIL image so the icon is crisp at any DPI.  Falls back to a
        # plain SDT text mark if Pillow is unavailable.
        mark_frame = tk.Frame(bar, bg=COLOR_BG_CARD)
        mark_frame.pack(side="left", anchor="w")

        # Load the highest-resolution frame from the bundled favicon.ico
        # (16/32/48/64/128/256).  Background stays transparent so the
        # TopBar card color shows through any alpha in the source
        # image -- the SDT logo blends with the card, no white box.
        favicon_chip = None
        if PIL_AVAILABLE:
            # 48-px matches the toolbar and the 16/32/48/64/128/256
            # frames packed into favicon.ico.
            favicon_img = HIGH_RES_FAVICON(48)
            if favicon_img is not None:
                from PIL import ImageTk
                favicon_chip = ImageTk.PhotoImage(favicon_img)
        if favicon_chip is not None:
            mark = tk.Label(mark_frame, image=favicon_chip,
                            bg=COLOR_BG_CARD, bd=0)
            mark.image = favicon_chip  # prevent GC
            mark.pack(side="left")
        else:
            canvas = tk.Canvas(mark_frame, width=36, height=36,
                               bg=COLOR_BG_CARD, highlightthickness=0, bd=0)
            canvas.pack(side="left")
            canvas.create_oval(2, 2, 34, 34, fill=COLOR_BRAND_TINT,
                               outline=COLOR_BRAND, width=2)
            canvas.create_text(18, 19, text="SDT", fill=COLOR_BRAND_DARK,
                               font=(FONT_FAMILY_UI, 9, "bold"))

        text = ttk.Frame(bar, style="Card.TFrame")
        text.pack(side="left", padx=(12, 0), anchor="w")
        ttk.Label(text, text="SDT \u7f51\u7edc\u8bbe\u5907\u5de1\u68c0\u63a7\u5236\u53f0",
                  style="Brand.TLabel").pack(anchor="w")
        ttk.Label(
            text,
            text="\u6279\u91cf Telnet / SSH \u914d\u7f6e\u91c7\u96c6 \u00b7 \u5b9e\u65f6\u65e5\u5fd7 \u00b7 \u5b9a\u65f6\u8c03\u5ea6",
            style="CardHint.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        right = ttk.Frame(bar, style="Card.TFrame")
        right.pack(side="right", anchor="e")
        files = ttk.Frame(right, style="Card.TFrame")
        files.pack(side="left", padx=(0, 14))
        ttk.Label(files, textvariable=self.devices_file_var,
                  style="Muted.TLabel").pack(anchor="e")
        ttk.Label(files, textvariable=self.commands_file_var,
                  style="Muted.TLabel").pack(anchor="e", pady=(2, 0))
        self.view_logs_btn = ttk.Button(right, text="\u67e5\u770b\u65e5\u5fd7",
                                        command=self._open_logs)
        self.view_logs_btn.pack(side="left")

    def _build_stat_cards(self, parent):
        cards = ttk.Frame(parent, style="App.TFrame")
        cards.pack(fill="x", pady=(0, self.GAP))
        for col in range(4):
            cards.columnconfigure(col, weight=1)

        self._stat_card(cards, "\u8bbe\u5907\u603b\u6570", self.total_var,
                        "\u5df2\u52a0\u8f7d\u7684\u8bbe\u5907", COLOR_BRAND, column=0)
        self._stat_card(cards, "\u5de1\u68c0\u6210\u529f", self.success_var,
                        "\u672c\u6b21\u4f1a\u8bdd\u7d2f\u8ba1", COLOR_SUCCESS, column=1)
        self._stat_card(cards, "\u5de1\u68c0\u5931\u8d25", self.failed_var,
                        "\u672c\u6b21\u4f1a\u8bdd\u7d2f\u8ba1", COLOR_DANGER, column=2)
        self._stat_card(cards, "\u6b63\u5728\u5de1\u68c0", self.running_var,
                        "\u5c1a\u672a\u5f00\u59cb", COLOR_WARNING, column=3)

    def _stat_card(self, parent, title, value, hint, accent, *, column):
        card = tk.Frame(parent, bg=COLOR_BG_CARD,
                        highlightbackground=COLOR_BORDER,
                        highlightthickness=1, bd=0)
        card.grid(row=0, column=column, sticky="nsew",
                  padx=(0 if column == 0 else 6, 0))
        card.columnconfigure(1, weight=1)

        stripe = tk.Frame(card, bg=accent, width=4)
        stripe.grid(row=0, column=0, sticky="ns")

        inner = ttk.Frame(card, style="Card.Inner.TFrame",
                          padding=(14, 12, 16, 12))
        inner.grid(row=0, column=1, sticky="nsew")

        ttk.Label(inner, text=title, style="CardTitle.TLabel").pack(anchor="w")
        value_label = ttk.Label(inner, textvariable=value,
                                style="CardValue.TLabel")
        value_label.pack(anchor="w", pady=(4, 0))
        value_label.configure(foreground=accent)
        ttk.Label(inner, text=hint, style="CardHint.TLabel").pack(anchor="w",
                                                                  pady=(2, 0))
        return card

    def _build_toolbar(self, parent):
        bar = ttk.Frame(parent, style="Card.TFrame", padding=(14, 10))
        bar.pack(fill="x", pady=(0, self.GAP))

        self.start_btn = ttk.Button(bar, text="\u5f00\u59cb\u5de1\u68c0",
                                    style="Accent.TButton",
                                    command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(bar, text="\u505c\u6b62\u5de1\u68c0",
                                   command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y",
                                                   padx=12, pady=2)

        self.load_devices_btn = ttk.Button(bar, text="\u52a0\u8f7d\u8bbe\u5907",
                                           command=self._load_devices)
        self.load_devices_btn.pack(side="left")
        self.load_commands_btn = ttk.Button(bar, text="\u52a0\u8f7d\u547d\u4ee4",
                                            command=self._load_commands)
        self.load_commands_btn.pack(side="left", padx=(8, 0))

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y",
                                                   padx=12, pady=2)
        ttk.Label(bar, text="\u5e76\u53d1",
                  style="CardHint.TLabel").pack(side="left")
        self.concurrency_spinbox = ttk.Spinbox(
            bar, from_=1, to=50, width=5,
            textvariable=self.concurrency_var, style="TSpinbox")
        self.concurrency_spinbox.pack(side="left", padx=(6, 14))
        ttk.Label(bar, text="\u8f93\u51fa\u7f16\u7801",
                  style="CardHint.TLabel").pack(side="left")
        self.encoding_combo = ttk.Combobox(
            bar, textvariable=self.encoding_var,
            values=["\u81ea\u52a8\u68c0\u6d4b", "UTF-8", "GB18030",
                    "GBK", "GB2312", "Big5"],
            state="readonly", width=11, style="TCombobox")
        self.encoding_combo.pack(side="left", padx=(6, 0))

        self.strict_host_keys_check = ttk.Checkbutton(
                bar,
                text="\u4e25\u683c\u4e3b\u673a\u5bc6\u94a5\u6821\u9a8c",
                variable=self.strict_host_keys_var,
                style="Subtle.TCheckbutton",
                cursor="hand2",
        )
        self.strict_host_keys_check.pack(side="left", padx=(12, 0))

        self.running_chip = tk.Frame(
            bar, bg=COLOR_BG_SUBTLE,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1, bd=0)
        self.running_chip.pack(side="right")
        tk.Label(
            self.running_chip, text="\u5b9e\u65f6\u8fdb\u5ea6",
            bg=COLOR_BG_SUBTLE, fg=COLOR_TEXT_MUTED,
            font=(FONT_FAMILY_UI, 9)).pack(side="left", padx=(10, 6), pady=4)
        self.progress = ModernProgressbar(
            self.running_chip, variable=self.progress_var, maximum=100,
            bar_height=8, corner_radius=4,
            trough_color=COLOR_BG_ELEVATED, fill_color=COLOR_BRAND)
        self.progress.pack(side="left", fill="x", expand=True,
                           padx=(0, 10), pady=4)
        self.progress.configure(width=240)

    def _build_schedule_strip(self, parent):
        strip = ttk.Frame(parent, style="Card.TFrame", padding=(14, 10))
        strip.pack(fill="x", pady=(0, self.GAP))

        # --------------------------------------------------------------
        # Toggle + label.  The switch image and the label live in the
        # same horizontal sub-frame so they share a baseline; we avoid
        # a fixed-height container which was clipping the toggle in v1.
        # --------------------------------------------------------------
        switch_row = tk.Frame(strip, bg=COLOR_BG_CARD)
        switch_row.pack(side="left")

        self.schedule_toggle = tk.Label(
            switch_row, bg=COLOR_BG_CARD, bd=0,
            highlightthickness=0, cursor="hand2",
        )
        # pady matches the surrounding combobox label vertical centre.
        self.schedule_toggle.pack(side="left", padx=(0, 8), pady=2)

        self.schedule_switch_frame = switch_row  # kept for backwards-compat
        self.schedule_label = ttk.Label(
            switch_row,
            textvariable=self.schedule_check_text_var,
            style="Schedule.TLabel", cursor="hand2",
        )
        self.schedule_label.pack(side="left", pady=2)
        for widget in (switch_row, self.schedule_toggle, self.schedule_label):
            widget.bind("<Button-1>",
                        lambda _event: self._on_schedule_check())
        self._draw_schedule_switch()

        ttk.Separator(strip, orient="vertical").pack(side="left", fill="y",
                                                     padx=14, pady=2)
        ttk.Label(strip, text="\u6bcf",
                  style="Schedule.TLabel").pack(side="left")
        self.schedule_frequency_combo = ttk.Combobox(
            strip, textvariable=self.schedule_frequency_var,
            values=["\u6708", "\u5468", "\u5929"], state="readonly",
            width=4, style="TCombobox")
        self.schedule_frequency_combo.pack(side="left", padx=(6, 4))

        # Day-of-month picker (visible only for monthly).
        self.schedule_day_label = ttk.Label(strip, text="\u53f7",
                                            style="Schedule.TLabel")
        self.schedule_day_combo = ttk.Combobox(
            strip, textvariable=self.schedule_day_var,
            values=[str(d) for d in range(1, 32)], state="readonly",
            width=4, style="TCombobox")

        # Weekday picker (visible only for weekly).  The dropdown
        # itself shows Chinese labels ("\u4e00" ... "\u65e5") so no
        # accompanying "周" label is needed.
        self.schedule_weekday_combo = ttk.Combobox(
            strip, textvariable=self.schedule_weekday_var,
            values=WEEKDAY_LABELS, state="readonly",
            width=4, style="TCombobox",
        )

        self.schedule_hour_combo = ttk.Combobox(
            strip, textvariable=self.schedule_hour_var,
            values=[f"{h:02d}" for h in range(24)], state="readonly",
            width=4, style="TCombobox")
        self.schedule_hour_combo.pack(side="left", padx=(6, 0))
        ttk.Label(strip, text="\u65f6",
                  style="Schedule.TLabel").pack(side="left", padx=(2, 0))
        self.schedule_minute_combo = ttk.Combobox(
            strip, textvariable=self.schedule_minute_var,
            values=[f"{m:02d}" for m in range(60)], state="readonly",
            width=4, style="TCombobox")
        self.schedule_minute_combo.pack(side="left", padx=(6, 0))
        ttk.Label(strip, text="\u5206",
                  style="Schedule.TLabel").pack(side="left", padx=(2, 0))
        ttk.Label(strip, text="\u6267\u884c\u5de1\u68c0",
                  style="Schedule.TLabel").pack(side="left", padx=(10, 0))

        self.schedule_frequency_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._on_schedule_frequency_change())
        self.schedule_hour_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._toggle_schedule())
        self.schedule_minute_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._toggle_schedule())
        self.schedule_day_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._toggle_schedule())
        self.schedule_weekday_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._toggle_schedule())
        self._update_schedule_day_visibility()
        ttk.Separator(strip, orient="vertical").pack(side="right", fill="y",
                                                     padx=14, pady=2)
        self.next_schedule_label = ttk.Label(
            strip, textvariable=self.next_schedule_var,
            style="CardHint.TLabel")
        self.next_schedule_label.pack(side="right")

    def _build_body(self, parent):
        body = ttk.Panedwindow(parent, orient="horizontal")
        body.pack(fill="both", expand=True, pady=(0, self.GAP))
        left = ttk.Frame(body, style="Card.TFrame", padding=0)
        right = ttk.Frame(body, style="Card.TFrame", padding=0)
        body.add(left, weight=3)
        body.add(right, weight=2)

        left_header = ttk.Frame(left, style="Card.TFrame",
                                padding=(16, 12, 16, 8))
        left_header.pack(fill="x")
        ttk.Label(left_header, text="\u8bbe\u5907\u5217\u8868",
                  style="CardTitle.TLabel").pack(side="left")
        chip = tk.Frame(left_header, bg=COLOR_BRAND_TINT,
                        highlightbackground=COLOR_BRAND_TINT_2, bd=0)
        chip.pack(side="left", padx=(8, 0))
        tk.Label(
            chip, textvariable=self.visible_count_var,
            bg=COLOR_BRAND_TINT, fg=COLOR_BRAND_DARK,
            font=(FONT_FAMILY_UI, 9, "bold"), padx=10, pady=2).pack()

        self.clear_all_btn = ttk.Button(
            left_header, text="\u53d6\u6d88\u5168\u9009", style="Subtle.TButton",
            command=lambda: self._set_all_selected(False))
        self.clear_all_btn.pack(side="right")
        self.invert_btn = ttk.Button(
            left_header, text="\u53cd\u9009", style="Subtle.TButton",
            command=self._invert_selected)
        self.invert_btn.pack(side="right", padx=(6, 0))
        self.select_all_btn = ttk.Button(
            left_header, text="\u5168\u9009", style="Subtle.TButton",
            command=lambda: self._set_all_selected(True))
        self.select_all_btn.pack(side="right", padx=(6, 0))

        search_frame = ttk.Frame(left, style="Subtle.TFrame",
                                 padding=(16, 8, 16, 8))
        search_frame.pack(fill="x")
        search_inner = ttk.Frame(search_frame, style="Subtle.TFrame")
        search_inner.pack(fill="x")
        tk.Label(
            search_inner, text="\u641c\u7d22", bg=COLOR_BG_SUBTLE,
            fg=COLOR_TEXT_MUTED, font=(FONT_FAMILY_UI, 9)).pack(side="left",
                                                                padx=(0, 6))
        self.search_entry = ttk.Entry(search_inner,
                                      textvariable=self.search_var,
                                      style="TEntry")
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<Escape>",
                               lambda _event: self._clear_search())
        self.clear_search_btn = ttk.Button(
            search_inner, text="\u6e05\u7a7a", style="Subtle.TButton",
            command=self._clear_search)
        self.clear_search_btn.pack(side="left", padx=(8, 0))
        self.search_var.trace_add("write", self._on_search_changed)

        tree_frame = ttk.Frame(left, style="Card.TFrame",
                               padding=(12, 0, 12, 12))
        tree_frame.pack(fill="both", expand=True)
        columns = ("name", "host", "protocol", "status")
        self.device_tree = ttk.Treeview(
            tree_frame, columns=columns, show="tree headings",
            selectmode="browse", style="Treeview")
        self._create_selection_images()
        self.device_tree.tag_configure("even", background="#FFFFFF")
        self.device_tree.tag_configure("odd", background=COLOR_BG_SUBTLE)

        headings = {
            "name": "\u8bbe\u5907\u540d\u79f0",
            "host": "\u5730\u5740\uff1a\u7aef\u53e3",
            "protocol": "\u534f\u8bae",
            "status": "\u72b6\u6001",
        }
        self.device_tree.heading("#0", text="")
        self.device_tree.column("#0", width=44, minwidth=44, stretch=False,
                                anchor="center")
        widths = {"name": 150, "host": 150, "protocol": 80, "status": 110}
        for column in columns:
            self.device_tree.heading(column, text=headings[column])
            # Left-align every data column so multi-line host
            # strings and longer device names read naturally.
            self.device_tree.column(
                column, width=widths[column],
                anchor="w",
                stretch=True)
        scroll = ttk.Scrollbar(tree_frame, orient="vertical",
                               command=self.device_tree.yview)
        self.device_tree.configure(yscrollcommand=scroll.set)
        self.device_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.device_tree.bind("<Button-1>", self._on_tree_click)

        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        log_header = ttk.Frame(right, style="Card.TFrame",
                               padding=(16, 12, 16, 8))
        log_header.grid(row=0, column=0, sticky="ew")
        ttk.Label(log_header, text="\u8fd0\u884c\u65e5\u5fd7",
                  style="CardTitle.TLabel").pack(side="left")
        ttk.Label(log_header, text="\u5b9e\u65f6\u8f93\u51fa\u5de1\u68c0\u8fc7\u7a0b\u4e0e\u7ed3\u679c",
                  style="CardHint.TLabel").pack(side="left", padx=(8, 0))

        log_frame = tk.Frame(right, bg=COLOR_BG_CARD)
        log_frame.grid(row=1, column=0, sticky="nsew", padx=12)
        log_inner = tk.Frame(
            log_frame, bg=COLOR_BG_SUBTLE,
            highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0)
        log_inner.pack(fill="both", expand=True)
        self.log_text = tk.Text(
            log_inner, state="disabled", wrap="word",
            font=(FONT_FAMILY_MONO_FALLBACK, 9),
            bg=COLOR_BG_SUBTLE, fg=COLOR_TEXT_BODY,
            relief="flat", bd=0, padx=14, pady=12,
            insertbackground=COLOR_BRAND,
            selectbackground=COLOR_BRAND_TINT_2,
            selectforeground=COLOR_TEXT_PRIMARY)
        log_scroll = ttk.Scrollbar(log_inner, orient="vertical",
                                   command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        # ------------------------------------------------------------
        # Log colour tags: ported from network_inspection/ui/theme.py
        # LOG_COLORS so log levels read consistently across both tools.
        # ------------------------------------------------------------
        self.log_text.tag_configure(
            LOG_TAG_TIMESTAMP,
            foreground=LOG_COLOR_TIMESTAMP,
        )
        for level in LOG_TAG_LEVELS:
            self.log_text.tag_configure(
                f"level-{level}",
                foreground=LOG_COLORS[level],
            )

    def _build_status_bar(self, parent):
        bar = tk.Frame(parent, bg=COLOR_BG_CARD,
                       highlightbackground=COLOR_BORDER,
                       highlightthickness=1, bd=0)
        bar.pack(fill="x")
        inner = ttk.Frame(bar, style="Card.Inner.TFrame", padding=(16, 8))
        inner.pack(fill="x")
        inner.columnconfigure(1, weight=1)
        self.status_dot = tk.Canvas(
            inner, width=12, height=12, bg=COLOR_BG_CARD,
            highlightthickness=0, bd=0)
        self.status_dot.grid(row=0, column=0, sticky="w")
        self._draw_status_dot(running=False)
        self.status_label = ttk.Label(inner, textvariable=self.status_var,
                                      style="Status.TLabel")
        self.status_label.grid(row=0, column=1, sticky="w", padx=(8, 0))

    def _create_selection_images(self):
        self.selected_image = self.icons.checkbox(True, size=18)
        self.unselected_image = self.icons.checkbox(False, size=18)

    def _draw_schedule_switch(self):
        enabled = self.schedule_enabled_var.get()
        # Slightly taller switch to align with the 9pt label baseline.
        image = self.icons.switch_track(enabled, size=(36, 20))
        if image is not None:
            self.schedule_toggle.configure(image=image, text="")
            return
        self.schedule_toggle.configure(
            image="", text="\u25cf",
            fg=COLOR_BRAND if enabled else "#94A3B8",
            font=(FONT_FAMILY_FALLBACK, 12))

    def _draw_status_dot(self, running, success=True):
        self.status_dot.delete("all")
        if running:
            color = COLOR_WARNING
        elif success:
            color = COLOR_SUCCESS
        else:
            color = COLOR_TEXT_MUTED
        self.status_dot.create_oval(2, 2, 10, 10, fill=color, outline=color)

    def _load_defaults(self):
        # Detect first launch BEFORE ensure_directories() runs.
        # The seeder creates config/ so the next launch will
        # see the directory already present and skip the prompt.
        first_run = self._is_first_run()
        ensure_directories()
        config = load_project()
        self._apply_config(config)
        if first_run:
            # Defer the README dialog until after the main window
            # is fully built; wait_window() needs a real Tk root.
            self.root.after(500, self._show_first_run_guide)

    def _is_first_run(self):
        """
        True when the config/ tree does not exist before this
        method runs.  ensure_directories() then seeds a template
        so the next launch is not a first run.
        """
        return not CONFIG_DIR.exists()

    def _show_first_run_guide(self):
        """
        Pop the README.txt in a scrollable Toplevel so the
        operator can read the quick-start before clicking anywhere.
        """
        readme = CONFIG_DIR / "README.txt"
        if not readme.exists():
            return
        try:
            text = readme.read_text(encoding="utf-8")
        except OSError:
            return
        win = tk.Toplevel(self.root)
        win.title("Welcome to SDT Network Device Inspection")
        win.geometry("720x520")

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill="both", expand=True)

        # Header: file path so the operator can locate it.
        ttk.Label(
            frame,
            text="Quick-start guide:  " + str(readme),
            foreground=COLOR_TEXT_MUTED,
            font=(FONT_FAMILY_UI, 9),
        ).pack(anchor="w", pady=(0, 6))

        text_widget = tk.Text(
            frame, wrap="word", height=18,
            font=(FONT_FAMILY_MONO_FALLBACK, 9),
            relief="flat", bd=1,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            highlightcolor=COLOR_BRAND,
            padx=8, pady=8,
        )
        text_widget.insert("1.0", text)
        text_widget.configure(state="disabled")
        text_widget.pack(fill="both", expand=True)

        def _close():
            win.destroy()
        ttk.Button(
            frame, text="Got it", command=_close,
            style="Accent.TButton",
        ).pack(pady=(12, 0))
        win.bind("<Return>", lambda _e: _close())
        win.bind("<Escape>", lambda _e: _close())

        # Center the dialog over the main window.
        self.root.update_idletasks()
        try:
            x = self.root.winfo_x() + (self.root.winfo_width() - win.winfo_width()) // 2
            y = self.root.winfo_y() + (self.root.winfo_height() - win.winfo_height()) // 2
            win.geometry("+{x}+{y}".format(x=x, y=y))
        except Exception:
            pass
        win.focus_set()
        win.transient(self.root)
        win.grab_set()
        win.wait_window()
        self._show_warnings(config.warnings)

    def _apply_config(self, config):
        self.devices = config.devices
        self.device_types = config.device_types
        self.commands_by_type = config.commands_by_type
        self.devices_file_var.set(
            f"\u8bbe\u5907\u5217\u8868\uff1a{config.devices_file or '\u672a\u52a0\u8f7d'}")
        self.commands_file_var.set(
            f"\u547d\u4ee4\u914d\u7f6e\uff1a{config.commands_file or '\u6309\u8bbe\u5907\u7c7b\u578b\u52a0\u8f7d'}")
        self._refresh_tree()
        self._update_stats()
        if self.devices and self.commands_by_type:
            self.status_var.set("\u914d\u7f6e\u52a0\u8f7d\u5b8c\u6210\uff0c\u53ef\u4ee5\u5f00\u59cb\u5de1\u68c0")
        else:
            self.status_var.set("\u914d\u7f6e\u4e0d\u5b8c\u6574\uff0c\u8bf7\u68c0\u67e5\u8bbe\u5907\u5217\u8868\u548c\u547d\u4ee4\u6587\u4ef6")

    def _show_warnings(self, warnings):
        for warning in warnings:
            self.logger.warning(warning)

    def _load_devices(self):
        path = filedialog.askopenfilename(
            title="\u9009\u62e9\u8bbe\u5907\u5217\u8868",
            initialdir=str(CONFIG_DIR),
            filetypes=[("CSV/TXT \u6587\u4ef6", "*.csv *.txt"),
                       ("\u6240\u6709\u6587\u4ef6", "*.*")])
        if not path:
            return
        devices, warnings = load_devices(Path(path), self.device_types)
        self.devices = devices
        self.devices_file_var.set(f"\u8bbe\u5907\u5217\u8868\uff1a{path}")
        self._refresh_tree()
        self._update_stats()
        self._show_warnings(warnings)
        self.status_var.set(f"\u5df2\u52a0\u8f7d {len(devices)} \u53f0\u8bbe\u5907")

    def _load_commands(self):
        path = filedialog.askopenfilename(
            title="\u9009\u62e9\u5de1\u68c0\u547d\u4ee4\u6587\u4ef6",
            initialdir=str(COMMANDS_DIR),
            filetypes=[("\u6587\u672c\u6587\u4ef6", "*.txt"),
                       ("\u6240\u6709\u6587\u4ef6", "*.*")])
        if not path:
            return
        commands, warnings = load_commands(Path(path))
        for type_id in self.device_types or {"sdt": None}:
            self.commands_by_type[type_id] = commands
        self.commands_file_var.set(f"\u547d\u4ee4\u914d\u7f6e\uff1a{path}")
        self._show_warnings(warnings)
        self.status_var.set(f"\u5df2\u52a0\u8f7d {len(commands)} \u6761\u5de1\u68c0\u547d\u4ee4")

    def _refresh_tree(self):
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        self.tree_items.clear()
        self.visible_indices.clear()
        query = self.search_var.get().strip().casefold()
        visible_count = 0
        for index, device in enumerate(self.devices):
            type_name = device.display_type(self.device_types)
            searchable = (
                f"{device.name} {device.host} {type_name} "
                f"{device.protocol} {device.port}").casefold()
            if query and query not in searchable:
                continue
            iid = f"device-{index}"
            item = self.device_tree.insert(
                "", "end", iid=iid,
                image=(self.selected_image if device.selected
                       else self.unselected_image),
                text="" if PIL_AVAILABLE else ("\u2713" if device.selected
                                               else ""),
                values=(
                    device.name,
                    f"{device.host}:{device.port}",
                    device.protocol.upper(),
                    "\u5f85\u5de1\u68c0",
                ),
                tags=("even" if visible_count % 2 == 0 else "odd",))
            self.visible_indices[iid] = index
            self.tree_items[device.name + "\0" + device.host
                            + f"\0{index}"] = item
            visible_count += 1
        self.visible_count_var.set(
            f"\u663e\u793a {visible_count}/{len(self.devices)}")

    def _on_search_changed(self, *_args):
        self._refresh_tree()

    def _clear_search(self):
        self.search_var.set("")

    def _on_tree_click(self, event):
        if self.inspection_running:
            return
        row = self.device_tree.identify_row(event.y)
        column = self.device_tree.identify_column(event.x)
        if not row or column != "#0":
            return
        index = self.visible_indices.get(row)
        if index is None or index >= len(self.devices):
            return
        self.devices[index].selected = not self.devices[index].selected
        self._refresh_tree()

    def _set_all_selected(self, selected):
        if self.inspection_running:
            return
        for device in self.devices:
            device.selected = selected
        self._refresh_tree()

    def _invert_selected(self):
        if self.inspection_running:
            return
        for device in self.devices:
            device.selected = not device.selected
        self._refresh_tree()

    def _update_stats(self):
        self.total_var.set(str(len(self.devices)))
        self.success_var.set(str(self.success_count))
        self.failed_var.set(str(self.failed_count))
        if self.inspection_running:
            running = sum(1 for d in self.devices if d.selected)
            self.running_var.set(str(running))
        else:
            self.running_var.set("\u2014")

    def _selected_encodings(self):
        mapping = {
            "UTF-8": ("utf-8", "gb18030", "gbk"),
            "GB18030": ("gb18030", "gbk", "utf-8"),
            "GBK": ("gbk", "gb18030", "utf-8"),
            "GB2312": ("gb2312", "gb18030", "utf-8"),
            "Big5": ("big5", "utf-8", "gb18030"),
        }
        return mapping.get(self.encoding_var.get(), DEFAULT_ENCODINGS)

    def _sync_schedule_check_text(self):
        self.schedule_check_text_var.set("\u542f\u7528\u5b9a\u65f6\u5de1\u68c0")
        self._draw_schedule_switch()

    def _on_schedule_check(self):
        self.schedule_enabled_var.set(not self.schedule_enabled_var.get())
        self._sync_schedule_check_text()
        self._toggle_schedule()

    def _on_schedule_frequency_change(self):
        self._update_schedule_day_visibility()
        self._toggle_schedule()

    def _update_schedule_day_visibility(self):
        freq = self.schedule_frequency_var.get()
        is_monthly = (freq == "\u6708")
        is_weekly = (freq == "\u5468")

        # Day-of-month widgets (monthly).
        if is_monthly:
            if not self.schedule_day_combo.winfo_manager():
                self.schedule_day_combo.pack(
                    side="left", before=self.schedule_hour_combo,
                    padx=(6, 0))
                self.schedule_day_label.pack(
                    side="left", before=self.schedule_hour_combo,
                    padx=(2, 0))
        else:
            self.schedule_day_combo.pack_forget()
            self.schedule_day_label.pack_forget()

        # Weekday combo (weekly).  The accompanying label was
        # removed because the dropdown now displays Chinese
        # weekday names ("\u4e00" ... "\u65e5") directly.
        if is_weekly:
            if not self.schedule_weekday_combo.winfo_manager():
                self.schedule_weekday_combo.pack(
                    side="left", before=self.schedule_hour_combo,
                    padx=(6, 0))
        else:
            self.schedule_weekday_combo.pack_forget()
            if hasattr(self, "schedule_weekday_label"):
                self.schedule_weekday_label.pack_forget()

    def _toggle_schedule(self):
        self._sync_schedule_check_text()
        if not self.schedule_enabled_var.get():
            self.scheduler.disable()
            self._update_schedule_display()
            self.logger.info("\u5b9a\u65f6\u5de1\u68c0\u5df2\u5173\u95ed")
            return
        frequency_name = self.schedule_frequency_var.get()
        frequency_map = {
            "\u5929": "daily", "\u5468": "weekly", "\u6708": "monthly",
        }
        frequency = frequency_map.get(frequency_name)
        time_of_day = (f"{self.schedule_hour_var.get()}:"
                       f"{self.schedule_minute_var.get()}")
        try:
            if frequency is None:
                raise ValueError("\u8bf7\u9009\u62e9\u6bcf\u5929 / \u6bcf\u5468 / \u6bcf\u6708")
            day_of_month = int(self.schedule_day_var.get())
            weekday_label = self.schedule_weekday_var.get()
            weekday = WEEKDAY_INDEX.get(weekday_label, 1)
            self.scheduler.enable(
                frequency=frequency,
                time_of_day=time_of_day,
                day_of_month=day_of_month,
                weekday=weekday,
            )
        except ValueError as exc:
            self.schedule_enabled_var.set(False)
            self._sync_schedule_check_text()
            self.scheduler.disable()
            self._update_schedule_display()
            messagebox.showerror("\u5b9a\u65f6\u4efb\u52a1\u914d\u7f6e\u9519\u8bef", str(exc))
            return
        self._update_schedule_display()
        weekday_cn = self.schedule_weekday_var.get() or WEEKDAY_LABELS[0]
        if frequency == "monthly":
            message = (f"\u5b9a\u65f6\u5de1\u68c0\u5df2\u542f\u7528\uff0c\u6bcf\u6708 "
                       f"{day_of_month} \u53f7 {time_of_day} \u5de1\u68c0")
        elif frequency == "weekly":
            message = (f"\u5b9a\u65f6\u5de1\u68c0\u5df2\u542f\u7528\uff0c\u6bcf\u5468 "
                       f"{weekday_cn} {time_of_day} \u5de1\u68c0")
        else:
            message = f"\u5b9a\u65f6\u5de1\u68c0\u5df2\u542f\u7528\uff0c\u6bcf\u5929 {time_of_day} \u5de1\u68c0"
        self.logger.info(message)
        self.status_var.set(
            f"{message}\uff0c\u4e0b\u4e00\u6b21\uff1a"
            f"{self.scheduler.display_next_run()}")

    def _update_schedule_display(self):
        self.next_schedule_var.set(
            f"\u4e0b\u6b21\u5de1\u68c0\uff1a{self.scheduler.display_next_run()}")

    def _scheduler_tick(self):
        if self.scheduler.is_due():
            self.scheduler.mark_triggered()
            self._update_schedule_display()
            if self.inspection_running or self.service.running:
                self.logger.warning(
                    "\u5b9a\u65f6\u5de1\u68c0\u5230\u671f\uff0c\u4f46\u5f53\u524d\u5df2\u6709\u5de1\u68c0\u4efb\u52a1\uff0c\u5df2\u8df3\u8fc7\u672c\u6b21")
            else:
                self.logger.info("\u5b9a\u65f6\u4efb\u52a1\u5df2\u5230\u671f\uff0c\u5f00\u59cb\u81ea\u52a8\u5de1\u68c0")
                self._start(automatic=True)
        if self.root.winfo_exists():
            self.scheduler_tick_id = self.root.after(1000,
                                                     self._scheduler_tick)

    def _start(self, automatic=False):
        if self.inspection_running or self.service.running:
            return False
        selected = [d for d in self.devices if d.selected]
        if not selected:
            if automatic:
                self.logger.warning("\u5b9a\u65f6\u5de1\u68c0\u8df3\u8fc7\uff1a\u6ca1\u6709\u9009\u4e2d\u7684\u8bbe\u5907")
            else:
                messagebox.showwarning("\u65e0\u6cd5\u5f00\u59cb",
                                       "\u8bf7\u81f3\u5c11\u9009\u62e9\u4e00\u53f0\u8bbe\u5907")
            return False
        if not self.commands_by_type:
            if automatic:
                self.logger.warning("\u5b9a\u65f6\u5de1\u68c0\u8df3\u8fc7\uff1a\u6ca1\u6709\u53ef\u6267\u884c\u7684\u5de1\u68c0\u547d\u4ee4")
            else:
                messagebox.showwarning("\u65e0\u6cd5\u5f00\u59cb",
                                       "\u6ca1\u6709\u53ef\u6267\u884c\u7684\u5de1\u68c0\u547d\u4ee4")
            return False
        try:
            concurrency = int(self.concurrency_var.get())
            if not 1 <= concurrency <= 50:
                raise ValueError
        except ValueError:
            if automatic:
                self.logger.error(
                    "\u5b9a\u65f6\u5de1\u68c0\u542f\u52a8\u5931\u8d25\uff1a\u5e76\u53d1\u6570\u5fc5\u987b\u662f 1 \u5230 50 \u4e4b\u95f4\u7684\u6574\u6570")
            else:
                messagebox.showerror("\u914d\u7f6e\u9519\u8bef",
                                     "\u5e76\u53d1\u6570\u5fc5\u987b\u662f 1 \u5230 50 \u4e4b\u95f4\u7684\u6574\u6570")
            return False

        self.success_count = self.failed_count = self.cancelled_count = 0
        self.progress.set(0, animate=False)
        self.inspection_running = True
        for item in self.device_tree.get_children():
            values = list(self.device_tree.item(item, "values"))
            if values:
                values[-1] = "\u7b49\u5f85"
                self.device_tree.item(item, values=values)
        self._set_controls(False)
        self._update_stats()
        self._draw_status_dot(running=True)
        self.status_var.set(
            "\u5b9a\u65f6\u4efb\u52a1\u6b63\u5728\u542f\u52a8\u5de1\u68c0..."
            if automatic else "\u6b63\u5728\u542f\u52a8\u5de1\u68c0...")
        try:
            self.service.start(
                self.devices, self.device_types,
                self.commands_by_type, concurrency,
                self._selected_encodings(),
                strict_host_keys=self.strict_host_keys_var.get(),
            )
        except Exception as exc:
            self.inspection_running = False
            self._set_controls(True)
            self._update_stats()
            self._draw_status_dot(running=False, success=False)
            if automatic:
                self.logger.error(f"\u5b9a\u65f6\u5de1\u68c0\u542f\u52a8\u5931\u8d25: {exc}")
            else:
                messagebox.showerror("\u542f\u52a8\u5931\u8d25", str(exc))
            return False
        return True

    def _stop(self):
        if not self.inspection_running:
            return
        if not messagebox.askyesno(
            "\u786e\u8ba4\u505c\u6b62",
            "\u786e\u5b9a\u505c\u6b62\u5f53\u524d\u5de1\u68c0\u5417\uff1f\n\u6240\u6709\u8fde\u63a5\u4f1a\u7acb\u5373\u65ad\u5f00\u3002"):
            return
        self.status_var.set("\u6b63\u5728\u505c\u6b62\u5de1\u68c0\u2026\u6b63\u5728\u65ad\u5f00\u8fde\u63a5")
        self.stop_btn.configure(state="disabled")
        self._append_log("[\u4fe1\u606f] \u7528\u6237\u53d1\u8d77\u505c\u6b62\uff0c\u6b63\u5728\u7acb\u5373\u65ad\u5f00\u6240\u6709\u8fde\u63a5\u3002")
        self.root.update_idletasks()
        self.service.stop()

    def _set_controls(self, enabled):
        state = "normal" if enabled else "disabled"
        self.start_btn.configure(state=state)
        self.stop_btn.configure(state="disabled" if enabled else "normal")
        self.concurrency_spinbox.configure(state=state)
        self.encoding_combo.configure(
            state="readonly" if enabled else "disabled")
        self.load_devices_btn.configure(state=state)
        self.load_commands_btn.configure(state=state)
        self.select_all_btn.configure(state=state)
        self.invert_btn.configure(state=state)
        self.clear_all_btn.configure(state=state)
        self.search_entry.configure(state=state)
        self.clear_search_btn.configure(state=state)
        self.schedule_frequency_combo.configure(
            state="readonly" if enabled else "disabled")
        self.schedule_day_combo.configure(
            state="readonly" if enabled else "disabled")
        self.schedule_hour_combo.configure(
            state="readonly" if enabled else "disabled")
        self.schedule_minute_combo.configure(
            state="readonly" if enabled else "disabled")

    def _on_event(self, event):
        if event.kind == "log":
            self._append_log(event.message)
        elif event.kind == "started":
            self.status_var.set(event.message)
        elif event.kind == "device_started":
            self._set_device_status(event.device_name, "\u8fde\u63a5\u4e2d")
            self._update_stats()
        elif event.kind == "device_finished":
            if event.result:
                if event.result.status is ResultStatus.SUCCESS:
                    self.success_count += 1
                    status = "\u6210\u529f"
                elif event.result.status is ResultStatus.CANCELLED:
                    self.cancelled_count += 1
                    status = "\u5df2\u53d6\u6d88"
                else:
                    self.failed_count += 1
                    status = "\u5931\u8d25"
                self._set_device_status(event.device_name, status)
                self._update_stats()
                if event.result.log_file:
                    self._append_log(f"\u7ed3\u679c\u6587\u4ef6\uff1a{event.result.log_file}")
        elif event.kind == "progress":
            percent = (int(event.completed * 100 / event.total)
                       if event.total else 0)
            self.progress.set(percent, animate=True)
            self.status_var.set(event.message)
            self._update_stats()
        elif event.kind == "finished":
            self.inspection_running = False
            self.progress.set(100 if event.total else 0,
                              animate=bool(event.total))
            self.status_var.set(event.message)
            self._set_controls(True)
            self._update_stats()
            self._draw_status_dot(running=False,
                                  success=(self.failed_count == 0))

    def _set_device_status(self, name, status):
        # Match by name.  If the row vanished (e.g. CSV
        # reloaded mid-run) silently skip rather than
        # corrupting the first row that happens to share
        # a name with the finished device.
        for index, device in enumerate(self.devices):
            if device.name != name:
                continue
            item = f"device-{index}"
            if self.device_tree.exists(item):
                values = list(self.device_tree.item(item, "values"))
                values[-1] = status
                self.device_tree.item(item, values=values)
            return

    def _level_of_message(self, message):
        """
        Classify a log message by its text content.  The InspectionEvent
        emitted by AppLogger does not yet carry a level field, so we
        look for Chinese / English keywords here.  Returns one of the
        keys in widgets.LOG_COLORS (INFO, WARNING, ERROR, ...).
        """
        if not message:
            return "INFO"
        lower = message.lower()
        error_kw = ("error", "failed", "exception",
                      "failed", "失败", "错误", "异常", "超时", "timeout")
        if any(kw in message or kw in lower for kw in error_kw):
            return "ERROR"
        warn_kw = ("warn", "warning", "警告")
        if any(kw in message or kw in lower for kw in warn_kw):
            return "WARNING"
        ok_kw = ("success", "succeeded", "successful",
                  "成功", "完成")
        if any(kw in message or kw in lower for kw in ok_kw):
            return "SUCCESS"
        return "INFO"

    def _append_log(self, message):
        """
        Insert a log message into the runtime log panel.

        Tag scheme (matches network_inspection for cross-tool
        consistency):
            * log-timestamp  - HH:MM:SS prefix in muted slate
            * level-<LEVEL>  - INFO / WARNING / ERROR / SUCCESS foreground
        """
        from datetime import datetime
        if not isinstance(message, str):
            message = "" if message is None else str(message)
        if not message:
            return
        level = self._level_of_message(message)
        tag = f"level-{level}"
        timestamp = datetime.now().strftime("%H:%M:%S")
        timestamp_tag = LOG_TAG_TIMESTAMP

        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[" + timestamp + "] ", timestamp_tag)
        self.log_text.insert("end", message + "\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # Cap how many events one poll tick will process.  Without
    # this, a worker that emits thousands of log events in a
    # single command read can block the UI for a perceptible
    # number of frames because every widget update has to wait
    # for the whole backlog to drain.  200 is enough to keep the
    # log panel scrolling smoothly under the typical 5-device
    # 5-command workload and still leaves ~2 ticks' worth of
    # headroom before the queue hits its 10k ceiling.
    _POLL_BATCH_LIMIT = 200

    def _poll_events(self):
        try:
            for _ in range(self._POLL_BATCH_LIMIT):
                self._on_event(self.events.get_nowait())
        except Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(100, self._poll_events)

    def _open_logs(self):
        ensure_directories()
        try:
            open_in_file_manager(LOG_DIR)
        except OSError as exc:
            messagebox.showerror("\u6253\u5f00\u5931\u8d25", str(exc))

    def _on_close(self):
        if self.inspection_running:
            if not messagebox.askyesno("\u9000\u51fa",
                                       "\u5de1\u68c0\u4ecd\u5728\u8fd0\u884c\uff0c\u786e\u5b9a\u9000\u51fa\u5417\uff1f"):
                return
            # Blocking stop so in-flight log files finish writing.
            self.service.stop(join=True, join_timeout=5.0)
        self.scheduler.disable()
        if self.scheduler_tick_id is not None:
            try:
                self.root.after_cancel(self.scheduler_tick_id)
            except tk.TclError:
                pass
        self.root.destroy()


def run():
    ensure_directories()
    root = tk.Tk()
    InspectionUI(root)
    root.mainloop()


if __name__ == "__main__":
    run()
