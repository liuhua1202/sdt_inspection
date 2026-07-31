# SDT Inspection \u2014 Light-theme Design System

The Tkinter UI for `sdt_app` is built on a small, cohesive design system
rather than ad-hoc colors.  All colors, fonts, motion and spacing come
from named tokens exposed in `sdt_app/widgets.py`.  The same tokens
are reused by the `ttk` style block in `sdt_app/ui.py`.

The UI is **light-mode first** and follows a clean, low-saturation
"enterprise dashboard" aesthetic.

---

## 1. Layout regions (top to bottom)

```
┌──────────────────────────────────────────────────────────────────┐
│  Top bar            brand mark + title + files + view logs       │
├──────────────────────────────────────────────────────────────────┤
│  Stat cards        total / success / failed / running            │
├──────────────────────────────────────────────────────────────────┤
│  Toolbar           start / stop / load / concurrency / encoding │
│                     + inline live-progress chip                  │
├──────────────────────────────────────────────────────────────────┤
│  Schedule strip    toggle + frequency + time + next run          │
├──────────────────────────────────────────────────────────────────┤
│  Body (paned)      device list (left)  |  log (right)            │
├──────────────────────────────────────────────────────────────────┤
│  Status bar        status dot + status text                      │
└──────────────────────────────────────────────────────────────────┘
```

Spacing follows an 8pt grid (`GAP = 10` between major regions,
`padx = 16` / `pady = 14` around the whole app).

---

## 2. Color tokens (light theme)

| Token              | Hex        | Use                                    |
|--------------------|-----------|----------------------------------------|
| `COLOR_BG_APP`     | `#F4F6FB` | Window background                      |
| `COLOR_BG_CARD`    | `#FFFFFF` | Card / panel surface                   |
| `COLOR_BG_SUBTLE`  | `#F8FAFC` | Inside-card subtle background          |
| `COLOR_BG_ELEVATED`| `#F1F5F9` | Hover, progress track, focused combobox|
| `COLOR_BORDER`     | `#E2E8F0` | Card outline                           |
| `COLOR_BORDER_SUBTLE` | `#EEF2F7`| Table grid lines, separators          |
| `COLOR_BORDER_STRONG` | `#CBD5E1`| Focused / hovered border              |
| `COLOR_TEXT_PRIMARY`  | `#0F172A`| Titles                                |
| `COLOR_TEXT_BODY`     | `#1F2937`| Body copy                             |
| `COLOR_TEXT_MUTED`    | `#64748B`| Labels / hints                        |
| `COLOR_BRAND`         | `#2563EB`| Primary CTA / progress fill           |
| `COLOR_BRAND_DEEP`    | `#1D4ED8`| CTA hover                             |
| `COLOR_BRAND_DARK`    | `#1E3A8A`| Headings on light surfaces            |
| `COLOR_BRAND_TINT`    | `#EFF6FF`| Brand 50 background (chips, focus)    |
| `COLOR_BRAND_TINT_2`  | `#DBEAFE`| Brand 100 background / hover         |
| `COLOR_SUCCESS`       | `#16A34A`| Success text & accents                |
| `COLOR_SUCCESS_BG`    | `#DCFCE7`| Success tinted background             |
| `COLOR_DANGER`        | `#DC2626`| Failure text & accents                |
| `COLOR_DANGER_BG`     | `#FEE2E2`| Failure tinted background             |
| `COLOR_WARNING`       | `#D97706`| In-flight accent (warning amber)      |
| `COLOR_WARNING_BG`    | `#FEF3C7`| Warning tinted background             |
| `COLOR_INFO`          | `#0EA5E9`| Info accent                            |
| `COLOR_PROGRESS_TRACK`| `#E2E8F0`| Progress trough                        |
| `COLOR_PROGRESS_FILL` | `#2563EB`| Progress fill                          |

All pairs satisfy WCAG AA contrast against their intended background
(text 4.5:1 minimum, large text 3:1).

---

## 3. Typography

| Role        | Stack                                                       |
|-------------|-------------------------------------------------------------|
| UI / labels | `"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"`      |
| Mono / log  | `"Cascadia Code", "Consolas", "Sarasa Mono SC"`            |

Sizes (pt):

* Brand title     13  bold
* Card title      10  bold
* Card value      22  bold   (large numeric readout)
* Card hint        9  regular
* Body / button   10  regular
* Log entries      9  mono

---

## 4. Components

* **StatCard** \u2014 white card with a 4px left accent stripe in the
  card's accent color, a title, a 22pt numeric readout and a hint
  line.
* **ModernProgressbar** \u2014 Canvas-drawn rounded bar with a 320ms
  60fps forward animation and instant snap on backwards/reset.
* **Brand mark** \u2014 36px circle in `COLOR_BRAND_TINT` with the
  text "SDT" in `COLOR_BRAND_DARK`.
* **Status dot** \u2014 12px canvas dot in the status bar:
  * idle success \u2192 green
  * running       \u2192 amber
  * idle with failures \u2192 muted
* **Inline glyphs** \u2014 small PIL-drawn icons for checkboxes and the
  schedule switch (capped to 18-36px), cached per (name, size, color).

---

## 5. Motion

* Forward progress change \u2192 320ms 60fps tween (`ANIMATION_STEP_MS = 16`)
* Backwards change / reset \u2192 instant snap (avoid rolling back)
* Style hover/active states use the underlying `ttk` theme \u2014 no custom
  fade-in animation is applied to keep CPU usage low during large
  inspections.

---

## 6. Refinements vs. v1

### Top-bar favicon
The brand mark uses the real `favicon.ico` rendered through PIL with
`Image.Resampling.LANCZOS` at multiple sizes (32/36/64).  The icon is
alpha-composited onto a `COLOR_BRAND_TINT` rounded chip so it reads as
a single, anti-aliased object regardless of DPI.  A hand-drawn canvas
fallback remains for hosts without Pillow.

### Schedule strip alignment
The schedule toggle and its label share a sub-frame pinned to a fixed
22px height so the switch image and 9pt label baseline line up.
The switch itself is rendered at 36 × 20 (vs. 36 × 18 in v1) for
better optical alignment with a 10pt label.

### Log colouring
`LOG_COLORS` is ported directly from
`network_inspection/ui/theme.py` so the two tools produce visually
consistent log output:

| Level    | Hex        | Use                                     |
|----------|-----------|------------------------------------------|
| DEBUG    | `#6B7280` | gray-500, debug-only traces             |
| INFO     | `#0F6FC6` | brand blue, default information        |
| WARNING  | `#EA580C` | orange-600, recoverable issues         |
| ERROR    | `#DC2626` | red-600, hard failures                  |
| SUCCESS  | `#15803D` | green-700, success paths                |
| CRITICAL | `#DC2626` | red-600, same as ERROR                  |

A leading `[HH:MM:SS]` prefix is rendered with the muted
`log-timestamp` tag (`#94A3B8`).  The log level is detected by
`_detect_log_level` which honours both the `[LEVEL]` prefix and
Chinese keywords (失败 / 错误 / 异常 → ERROR,
警告 → WARNING, 成功 → SUCCESS).

## 6. Pre-delivery checklist

* [x] Contrast 4.5:1+ for all body text on its surface
* [x] Status icons / colors always paired with text (e.g. SUCCESS card
      value tinted but also clearly labeled)
* [x] All clickable elements get cursor="hand2"
* [x] Touch-friendly hit areas \u2014 buttons padding \u2265 (10, 5)
* [x] 60fps progress animation
* [x] No reliance on color alone \u2014 the "success" badge text +
      number + accent stripe all carry meaning
* [x] Disabled controls visibly muted (not just grey-on-grey)
* [x] No emoji used as icons (custom PIL glyphs)
