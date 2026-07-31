#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
release.py — 本地打包并发布到 GitHub Releases（源码不入库）

设计原则:
  - 源码永远不进本仓库（公开仓库只放说明文件），可执行程序只通过 Releases 分发。
  - token 从环境变量 GH_TOKEN 或 github_pat 读取，不写入任何文件 / 不进 .git / 不进记忆。

用法:
  # 1) 先确保已用 PyInstaller 生成 dist/sdt_inspection（onedir）
  # 2) 设置 token（用完后请在 GitHub 撤销）
  #    Windows 已把 PAT 存入系统变量 github_pat（Machine 作用域）时可直接运行：
  $env:GH_TOKEN="ghp_xxxx"       (PowerShell，或依赖系统变量 github_pat)
  set GH_TOKEN=ghp_xxxx          (Windows cmd)
  export GH_TOKEN=ghp_xxxx       (bash)
  # 3) 运行（版本号建议带 v 前缀）
  python tools/release.py v1.0.2
"""
import os
import sys
import json
import zipfile
import urllib.request
import urllib.error
import urllib.parse

REPO = "liuhua1202/sdt_inspection"          # 公开分发仓库
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_SRC = os.path.join(ROOT, "dist", "sdt_inspection")
ZIP_NAME = "sdt_inspection_win64.zip"
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


def get_release_by_tag(tag, token):
    """返回已存在的 release dict；不存在返回 None；其他错误直接退出。"""
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


def create_release(tag, token):
    url = f"{API}/repos/{REPO}/releases"
    data = {
        "tag_name": tag,
        "name": tag,
        "body": (
            f"SDT Inspection {tag} Windows 64 位可执行程序（PyInstaller onedir 打包）。\n\n"
            f"解压 {ZIP_NAME} 后运行其中的 sdt_inspection.exe 即可，无需安装 Python 运行环境。\n\n"
            "本仓库仅分发可执行程序；源代码不在本仓库中。"
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


def zip_dist():
    if not os.path.isdir(DIST_SRC):
        fail(
            f"未找到打包目录: {DIST_SRC}\n"
            "请先运行 PyInstaller 生成 dist/sdt_inspection（onedir 模式）。"
        )
    zip_path = os.path.join(ROOT, ZIP_NAME)
    n = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(DIST_SRC):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, os.path.dirname(DIST_SRC)))
                n += 1
    size_mb = round(os.path.getsize(zip_path) / 1024 / 1024, 1)
    print(f"[ok] 打包完成: {zip_path} ({n} 文件, {size_mb} MB)")
    return zip_path


def upload_asset(rel, zip_path, token):
    names = {a["name"] for a in rel.get("assets", [])}
    if ZIP_NAME in names:
        print(f"[skip] 附件 {ZIP_NAME} 已存在于该 release，跳过上传")
        return
    upload_url = rel["upload_url"].split("{")[0]
    with open(zip_path, "rb") as f:
        data = f.read()
    url = upload_url + "?name=" + urllib.parse.quote(ZIP_NAME)
    req = urllib.request.Request(
        url,
        data=data,
        headers=_headers(token, {"Content-Type": "application/zip"}),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as r:
            ares = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print("HTTPError", e.code, e.read().decode(), file=sys.stderr)
        sys.exit(1)
    print(f"[ok] 附件上传: {ares.get('browser_download_url')}")


def main():
    if len(sys.argv) < 2:
        fail("用法: python tools/release.py <版本号 例如 v1.0.2>")
    tag = sys.argv[1]
    if not tag.startswith("v"):
        tag = "v" + tag

    token = os.environ.get("GH_TOKEN") or os.environ.get("github_pat")
    if not token:
        fail("缺少环境变量 GH_TOKEN 或 github_pat，请先设置后再运行（用完请在 GitHub 撤销）。")

    zip_path = zip_dist()

    rel = get_release_by_tag(tag, token)
    if rel is None:
        rel = create_release(tag, token)
        print(f"[ok] release 创建: {rel['html_url']}")
    else:
        print(f"[info] tag {tag} 已存在 release: {rel['html_url']}")

    upload_asset(rel, zip_path, token)
    print("[done] 发布完成 ✅")


if __name__ == "__main__":
    main()
