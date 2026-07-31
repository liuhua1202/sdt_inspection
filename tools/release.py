#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
release.py — \u672c\u5730\u6253\u5305\u5e76\u53d1\u5e03\u5230 GitHub Releases\uff08\u6e90\u7801\u4e0d\u5165\u5e93\uff09

\u8bbe\u8ba1\u539f\u5219:
  - \u6e90\u7801\u6c38\u8fdc\u4e0d\u8fdb\u672c\u4ed3\u5e93\uff08\u516c\u5f00\u4ed3\u5e93\u53ea\u653e\u8bf4\u660e\u6587\u4ef6\uff09\uff0c\u53ef\u6267\u884c\u7a0b\u5e8f\u53ea\u901a\u8fc7 Releases \u5206\u53d1\u3002
  - token \u4ece\u73af\u5883\u53d8\u91cf GH_TOKEN / github_pat / GH_PAT \u8bfb\u53d6\uff0c\u4e0d\u5199\u5165\u4efb\u4f55\u6587\u4ef6 / \u4e0d\u8fdb .git / \u4e0d\u8fdb\u8bb0\u5fc6\u3002
  - \u53d1\u5e03\u7684 asset \u6587\u4ef6\u540d\u81ea\u52a8\u5e26\u4e0a\u7248\u672c\u53f7 (\u5982
    ``sdt_inspection_win64_v1.0.5.exe``), \u4e0e v1.0.2/3/4 \u4fdd\u6301\u4e00\u81f4\u3002

\u7528\u6cd5:
  # 1) \u5148\u7528 PyInstaller \u751f\u6210 dist/sdt_inspection \uff08onedir\uff09\u6216 dist/sdt_inspection.exe \uff08onefile\uff09
  # 2) \u8bbe\u7f6e token
  $env:GH_TOKEN="ghp_xxxx"          (PowerShell, \u4f18\u5148)
  $env:GH_PAT="ghp_xxxx"            (\u4f60\u672c\u5730\u9ed8\u8ba4\u7684\u53d8\u91cf\u540d)
  set GH_TOKEN=ghp_xxxx             (cmd)
  export GH_TOKEN=ghp_xxxx          (bash)
  # 3) \u8fd0\u884c\uff08\u7248\u672c\u53f7\u5efa\u8bae\u5e26 v \u524d\u7f00\uff09
  python tools/release.py v1.0.5
"""
import os
import sys
import json
import zipfile
import urllib.request
import urllib.error
import urllib.parse

# Force UTF-8 stdout so non-ASCII log lines (e.g. a \u2705 emoji) do
# not raise UnicodeEncodeError on Windows GBK / cp936 consoles.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

REPO = "liuhua1202/sdt_inspection"          # \u516c\u5f00\u5206\u53d1\u4ed3\u5e93
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_SRC = os.path.join(ROOT, "dist", "sdt_inspection")
DIST_EXE = os.path.join(ROOT, "dist", "sdt_inspection.exe")
API = "https://api.github.com"


def fail(msg):
    print("ERROR:", msg, file=sys.stderr)
    sys.exit(1)


def _headers(token, extra=None):
    h = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if extra:
        h.update(extra)
    return h


def asset_name(tag, ext):
    """Convention: ``sdt_inspection_win64_<tag>.<ext>``.

    Matches the on-disk names of the existing v1.0.2 / v1.0.3
    (zip) and v1.0.4 (exe) assets, so an operator who downloaded
    an older release sees the new one with the same shape.
    """
    return f"sdt_inspection_win64_{tag}.{ext}"


def get_release_by_tag(tag, token):
    """\u8fd4\u56de\u5df2\u5b58\u5728\u7684 release dict\uff1b\u4e0d\u5b58\u5728\u8fd4\u56de None\uff1b\u5176\u4ed6\u9519\u8bef\u76f4\u63a5\u9000\u51fa\u3002"""
    url = f"{API}/repos/{REPO}/releases/tags/{tag}"
    req = urllib.request.Request(url, headers=_headers(token))
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print("HTTPError", e.code, e.read().decode(), file=sys.stderr)
        sys.exit(1)


def create_release(tag, token, ext):
    if ext == "zip":
        install_hint = (
            f"\u89e3\u538b {asset_name(tag, 'zip')} \u540e\u8fd0\u884c\u5176\u4e2d\u7684 "
            "sdt_inspection.exe \u5373\u53ef\uff0c\u65e0\u9700\u5b89\u88c5 Python \u8fd0\u884c\u73af\u5883\u3002"
        )
    else:
        install_hint = (
            f"\u53cc\u51fb {asset_name(tag, 'exe')} \u5373\u53ef\uff1b"
            "\u9996\u6b21\u542f\u52a8\u4f1a\u81ea\u52a8\u5728\u540c\u76ee\u5f55\u751f\u6210 config/ \u4e0e InspectionLogs/\u3002"
        )
    url = f"{API}/repos/{REPO}/releases"
    data = {
        "tag_name": tag,
        "name": tag,
        "body": (
            f"SDT Inspection {tag} Windows 64 \u4f4d\u53ef\u6267\u884c\u7a0b\u5e8f\u3002\n\n"
            f"{install_hint}\n\n"
            "\u672c\u4ed3\u5e93\u4ec5\u5206\u53d1\u53ef\u6267\u884c\u7a0b\u5e8f\uff1b\u6e90\u4ee3\u7801\u4e0d\u5728\u672c\u4ed3\u5e93\u4e2d\u3002"
        ),
        "draft": False,
        "prerelease": False,
    }
    req = urllib.request.Request(
        url, data=json.dumps(data).encode(), headers=_headers(token), method="POST"
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print("HTTPError", e.code, e.read().decode(), file=sys.stderr)
        sys.exit(1)


def zip_dist(tag):
    if not os.path.isdir(DIST_SRC):
        fail(
            f"\u672a\u627e\u5230\u6253\u5305\u76ee\u5f55: {DIST_SRC}\n"
            "\u8bf7\u5148\u8fd0\u884c PyInstaller \u751f\u6210 dist/sdt_inspection\uff08onedir \u6a21\u5f0f\uff09\u3002"
        )
    name = asset_name(tag, "zip")
    zip_path = os.path.join(ROOT, name)
    n = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(DIST_SRC):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, os.path.dirname(DIST_SRC)))
                n += 1
    size_mb = round(os.path.getsize(zip_path) / 1024 / 1024, 1)
    print(f"[ok] \u6253\u5305\u5b8c\u6210: {zip_path} ({n} \u6587\u4ef6, {size_mb} MB)")
    return zip_path


def upload_asset(rel, file_path, asset_filename, token, content_type):
    names = {a["name"] for a in rel.get("assets", [])}
    if asset_filename in names:
        print(f"[skip] \u9644\u4ef6 {asset_filename} \u5df2\u5b58\u5728\u4e8e\u8be5 release\uff0c\u8df3\u8fc7\u4e0a\u4f20")
        return
    upload_url = rel["upload_url"].split("{")[0]
    with open(file_path, "rb") as f:
        data = f.read()
    url = upload_url + "?name=" + urllib.parse.quote(asset_filename)
    req = urllib.request.Request(
        url,
        data=data,
        headers=_headers(token, {"Content-Type": content_type}),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as r:
            ares = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print("HTTPError", e.code, e.read().decode(), file=sys.stderr)
        sys.exit(1)
    print(f"[ok] \u9644\u4ef6\u4e0a\u4f20: {ares.get('browser_download_url')}")


def resolve_token():
    """Accept GH_TOKEN, github_pat, or the user-level GH_PAT."""
    for name in ("GH_TOKEN", "github_pat"):
        v = os.environ.get(name)
        if v:
            return v
    # User-level env var is not inherited into child processes on
    # Windows; read it explicitly from the registry-backed store.
    try:
        import winreg  # type: ignore[import-not-found]
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
            v, _ = winreg.QueryValueEx(k, "GH_PAT")
            if v:
                return v
    except Exception:
        pass
    return None


def main():
    if len(sys.argv) < 2:
        fail("\u7528\u6cd5: python tools/release.py <\u7248\u672c\u53f7 \u4f8b\u5982 v1.0.5>")
    tag = sys.argv[1]
    if not tag.startswith("v"):
        tag = "v" + tag

    token = resolve_token()
    if not token:
        fail(
            "\u7f3a\u5c11\u73af\u5883\u53d8\u91cf GH_TOKEN / github_pat / GH_PAT\uff0c"
            "\u8bf7\u5148\u8bbe\u7f6e\u540e\u518d\u8fd0\u884c\uff08\u7528\u5b8c\u8bf7\u5728 GitHub \u64a4\u9500\uff09\u3002"
        )

    # Auto-detect build flavour: onefile wins, onedir is the fallback.
    if os.path.isfile(DIST_EXE):
        flavour = "onefile"
        file_path = DIST_EXE
        name = asset_name(tag, "exe")
        ctype = "application/vnd.microsoft.portable-executable"
    elif os.path.isdir(DIST_SRC):
        flavour = "onedir"
        file_path = zip_dist(tag)
        name = os.path.basename(file_path)
        ctype = "application/zip"
    else:
        fail(
            f"\u672a\u627e\u5230 dist/sdt_inspection.exe \u4e5f\u672a\u627e\u5230 dist/sdt_inspection/\u3002\n"
            "\u8bf7\u5148\u8fd0\u884c PyInstaller\uff1a\n"
            "  python -m PyInstaller sdt_inspection.spec            # onedir\n"
            "  python -m PyInstaller sdt_inspection_onefile.spec  # onefile"
        )

    print(f"[info] \u68c0\u6d4b\u5230\u6784\u5efa: {flavour} -> {name}")

    rel = get_release_by_tag(tag, token)
    if rel is None:
        ext = "exe" if flavour == "onefile" else "zip"
        rel = create_release(tag, token, ext)
        print(f"[ok] release \u521b\u5efa: {rel['html_url']}")
    else:
        print(f"[info] tag {tag} \u5df2\u5b58\u5728 release: {rel['html_url']}")

    upload_asset(rel, file_path, name, token, ctype)
    print("[done] \u53d1\u5e03\u5b8c\u6210")


if __name__ == "__main__":
    main()
