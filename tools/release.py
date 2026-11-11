"""FrameBoost 发布工具 —— 纯 GitHub REST API 实现，不依赖 git 协议。

（本机代理只放行 api.github.com / uploads.github.com，github.com 的 git 通道被拦；
 另外 Git Data API 拒绝 >50MB 的请求体，所以 47MB 的 zip 无法提交进仓库，
 二进制一律走 Release 附件，仓库里只放源码。）

用法（项目根目录）:
    python tools/release.py --check                     # 看远端当前状态
    python tools/release.py --dry-run                   # 演练：打包+算差异，不写远端
    python tools/release.py                             # 完整发布（发 Release）
    python tools/release.py --sync-source               # 发布同时把源码提交进仓库
    python tools/release.py --skip-build                # 复用 dist 里已有 zip
    python tools/release.py --version 1.6.0 --notes "…" # 指定版本与说明

认证：优先环境变量 GH_TOKEN，否则读 Windows 凭据管理器里的 GitHub 凭据。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

OWNER, REPO_NAME = "XiaoLiang0820", "DP-Harness-Upload"
REPO = f"{OWNER}/{REPO_NAME}"
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"


# --------------------------------------------------------------------------- #
# 基础
# --------------------------------------------------------------------------- #
def say(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def human(n: float) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} GB"


def get_token() -> str:
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if tok:
        return tok.strip()
    p = subprocess.run(["git", "credential", "fill"],
                       input="protocol=https\nhost=github.com\n\n",
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace",
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0",
                            "GCM_INTERACTIVE": "Never"})
    for line in p.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise RuntimeError("取不到 GitHub 凭据：请设置 GH_TOKEN，或在命令行执行一次 git push 让凭据管理器记住 token")


def api(method: str, path: str, tok: str, body=None, base: str = API,
        timeout: int = 120, retries: int = 3):
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
    last = ""
    for attempt in range(retries):
        req = urllib.request.Request(base + path, data=data, method=method)
        req.add_header("Authorization", "Bearer " + tok)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "FrameBoost-release")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                payload = json.loads(raw or b"{}")
            except Exception:
                payload = {"raw": raw[:200].decode("utf-8", "replace")}
            if e.code in (500, 502, 503, 504) and attempt < retries - 1:
                last = f"{e.code} {payload.get('message')}"
                time.sleep(2 * (attempt + 1))
                continue
            return e.code, payload
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = str(e)
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return 0, {"message": last}
    return 0, {"message": last}


# --------------------------------------------------------------------------- #
# 版本 / 构建
# --------------------------------------------------------------------------- #
def read_version() -> str:
    text = open(os.path.join(PROJECT, "app", "version.py"), encoding="utf-8").read()
    m = re.search(r'^VERSION\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        raise RuntimeError("app/version.py 里找不到 VERSION")
    return m.group(1)


def build() -> None:
    spec = os.path.join(PROJECT, "FrameBoost.spec")
    say("PyInstaller 打包中（约 1-3 分钟）…")
    if os.path.exists(spec):
        args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "FrameBoost.spec"]
    else:
        args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                "--windowed", "--onedir", "--name", "FrameBoost",
                "--icon", os.path.join("assets", "icon.ico"), "run.py"]
    p = subprocess.run(args, cwd=PROJECT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        tail = ((p.stdout or "") + (p.stderr or ""))[-1200:]
        raise RuntimeError("打包失败：\n" + tail)
    say("打包完成")


def make_zip(version: str) -> str:
    app_dir = os.path.join(PROJECT, "dist", "FrameBoost")
    if not os.path.isdir(app_dir):
        raise RuntimeError(f"找不到打包产物：{app_dir}")
    out = os.path.join(PROJECT, "dist", f"FrameBoost_v{version}.zip")
    if os.path.exists(out):
        os.remove(out)
    say("压缩 dist/FrameBoost …")
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, _d, files in os.walk(app_dir):
            for fn in files:
                full = os.path.join(root, fn)
                z.write(full, os.path.join("FrameBoost", os.path.relpath(full, app_dir)))
                n += 1
    say(f"压缩完成：{n} 文件 / {human(os.path.getsize(out))}")
    return out


def blob_sha(path: str) -> str:
    size = os.path.getsize(path)
    h = hashlib.sha1(f"blob {size}\0".encode())
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# 远端状态
# --------------------------------------------------------------------------- #
def head(tok: str) -> tuple[str, str]:
    code, ref = api("GET", f"/repos/{REPO}/git/ref/heads/main", tok)
    if code != 200:
        raise RuntimeError(f"读取 main 失败：{code} {ref.get('message')}")
    return ref["object"]["sha"], ref["object"].get("url", "")


def tree_of(commit_sha: str, tok: str) -> list[dict]:
    code, t = api("GET", f"/repos/{REPO}/git/trees/{commit_sha}", tok)
    if code != 200:
        raise RuntimeError(f"读取 tree 失败：{code}")
    return t.get("tree", [])


def release_by_tag(tag: str, tok: str):
    code, rel = api("GET", f"/repos/{REPO}/releases/tags/{tag}", tok)
    return rel if code == 200 else None


def check(tok: str) -> None:
    sha, _ = head(tok)
    code, commit = api("GET", f"/repos/{REPO}/git/commits/{sha}", tok)
    say(f"main HEAD: {sha[:7]}  «{commit.get('message', '').strip()}»")
    for e in tree_of(sha, tok):
        say(f"  {e['type']:5} {human(e.get('size', 0)):>10}  {e['path']}")
    code, rels = api("GET", f"/repos/{REPO}/releases?per_page=100", tok)
    if code == 200:
        say(f"Releases: {len(rels)} 个")
        for r in rels[:6]:
            assets = ", ".join(f"{a['name']}({human(a['size'])})" for a in r.get("assets", []))
            say(f"  {r['tag_name']:10} {r['published_at'][:16]}  {assets}")


# --------------------------------------------------------------------------- #
# 用 Git Data API 提交（替代 git push）
# --------------------------------------------------------------------------- #
SRC_SKIP_DIRS = {"dist", "build", ".git", "__pycache__", ".venv", "venv",
                 "_release", "node_modules", ".idea", ".vscode"}
SRC_SKIP_EXT = (".pyc", ".pyo", ".log", ".zip")
SRC_MAX_MB = 40


def collect_source() -> list[tuple[str, str, int]]:
    """收集要提交的源码文件（相对路径, 绝对路径, 大小）."""
    out = []
    for root, dirs, names in os.walk(PROJECT):
        dirs[:] = [d for d in dirs if d not in SRC_SKIP_DIRS]
        rel_root = os.path.relpath(root, PROJECT)
        rel_root = "" if rel_root == "." else rel_root
        for n in names:
            if n.endswith(SRC_SKIP_EXT):
                continue
            full = os.path.join(root, n)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            if size > SRC_MAX_MB * 1024 * 1024:
                say(f"  跳过超大文件 {n}（{human(size)}）")
                continue
            rel = os.path.join(rel_root, n).replace("\\", "/") if rel_root else n
            out.append((rel, full, size))
    out.sort()
    return out


def sync_source(version: str, tok: str, dry: bool) -> None:
    """把项目源码提交进仓库（二进制走 Release，不提交 dist/）。"""
    parent, _ = head(tok)
    existing = {e["path"]: e for e in tree_of(parent, tok)}
    files = collect_source()
    say(f"源码同步：本地 {len(files)} 个文件，远端 HEAD {parent[:7]}")

    changed = [(rel, full) for rel, full, _sz in files
               if existing.get(rel, {}).get("sha") != blob_sha(full)]
    total = sum(os.path.getsize(f) for _r, f in changed)
    say(f"  需上传 {len(changed)} 个（{human(total)}），未变 {len(files) - len(changed)} 个")

    if not changed:
        say("  源码无变化，跳过提交")
        return
    if dry:
        for rel, _f in changed[:12]:
            say(f"  [演练] 更新 {rel}")
        if len(changed) > 12:
            say(f"  [演练] … 另有 {len(changed) - 12} 个")
        say(f"  [演练] 将基于 {parent[:7]} 创建 commit 并更新 main")
        return

    entries = []
    for rel, full in changed:
        b64 = base64.b64encode(open(full, "rb").read()).decode()
        code, blob = api("POST", f"/repos/{REPO}/git/blobs", tok,
                         {"content": b64, "encoding": "base64"})
        if code not in (200, 201):
            raise RuntimeError(f"上传 {rel} 失败：{code} {blob.get('message')}")
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})

    code, new_tree = api("POST", f"/repos/{REPO}/git/trees", tok,
                         {"base_tree": parent, "tree": entries})
    if code not in (200, 201):
        raise RuntimeError(f"创建 tree 失败：{code} {new_tree.get('message')}")

    code, commit = api("POST", f"/repos/{REPO}/git/commits", tok,
                       {"message": f"chore: sync source v{version}",
                        "tree": new_tree["sha"], "parents": [parent]})
    if code not in (200, 201):
        raise RuntimeError(f"创建 commit 失败：{code} {commit.get('message')}")

    code, res = api("PATCH", f"/repos/{REPO}/git/refs/heads/main", tok,
                    {"sha": commit["sha"], "force": False})
    if code not in (200, 201):
        raise RuntimeError(f"更新 main 失败：{code} {res.get('message')}")
    say(f"✅ 源码已提交 main → {commit['sha'][:7]}")


# --------------------------------------------------------------------------- #
# Release
# --------------------------------------------------------------------------- #
def upload_asset(tok: str, release_id: int, zip_path: str) -> dict:
    name = os.path.basename(zip_path)
    size = os.path.getsize(zip_path)
    url = (f"{UPLOADS}/repos/{REPO}/releases/{release_id}/assets"
           f"?name={urllib.parse.quote(name)}")
    say(f"上传 Release 附件 {name}（{human(size)}）…")
    for attempt in range(3):
        with open(zip_path, "rb") as f:
            req = urllib.request.Request(url, data=f, method="POST")
            req.add_header("Authorization", "Bearer " + tok)
            req.add_header("Content-Type", "application/zip")
            req.add_header("Content-Length", str(size))
            req.add_header("User-Agent", "FrameBoost-release")
            try:
                with urllib.request.urlopen(req, timeout=3600) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                body = e.read()[:300].decode("utf-8", "replace")
                if e.code in (500, 502, 503) and attempt < 2:
                    say(f"上传遇到 {e.code}，重试 {attempt + 1}/2 …")
                    time.sleep(5)
                    continue
                raise RuntimeError(f"上传附件失败：{e.code} {body}")
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt < 2:
                    say(f"上传中断（{e}），重试 {attempt + 1}/2 …")
                    time.sleep(5)
                    continue
                raise RuntimeError(f"上传附件失败：{e}")
    raise RuntimeError("上传附件失败")


def publish_release(zip_path: str, version: str, tok: str, dry: bool, notes: str) -> None:
    tag = f"v{version}"
    zname = os.path.basename(zip_path)
    rel = release_by_tag(tag, tok)

    if rel:
        say(f"Release {tag} 已存在（{len(rel.get('assets', []))} 个附件）")
        same_asset = [a for a in rel.get("assets", [])
                      if a["name"] == zname and a["size"] == os.path.getsize(zip_path)]
        if same_asset:
            say(f"附件 {zname} 已存在且大小一致，跳过上传")
            say(f"下载地址：{same_asset[0]['browser_download_url']}")
            return
        if dry:
            say(f"[演练] 将替换 Release {tag} 的附件 {zname}")
            return
        for a in rel.get("assets", []):
            if a["name"] == zname:
                say(f"删除旧附件 {a['name']}")
                api("DELETE", f"/repos/{REPO}/releases/assets/{a['id']}", tok)
        release_id = rel["id"]
    else:
        if dry:
            say(f"[演练] 将创建 Release {tag} 并上传 {zname}")
            return
        say(f"创建 Release {tag} …")
        code, rel = api("POST", f"/repos/{REPO}/releases", tok, {
            "tag_name": tag,
            "name": f"FrameBoost v{version}",
            "body": notes or f"FrameBoost v{version}",
            "draft": False, "prerelease": False,
        })
        if code not in (200, 201):
            raise RuntimeError(f"创建 Release 失败：{code} {rel.get('message')}")
        release_id = rel["id"]

    asset = upload_asset(tok, release_id, zip_path)
    say(f"✅ 附件已上传：{asset.get('name')} {human(asset.get('size', 0))} "
        f"state={asset.get('state')}")
    say(f"下载地址：{asset.get('browser_download_url')}")


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="FrameBoost 一键发布（纯 API，不需要 git）")
    ap.add_argument("--version")
    ap.add_argument("--notes", default="")
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--sync-source", action="store_true", help="同时把源码提交进仓库")
    ap.add_argument("--skip-release", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true", help="只打印远端状态")
    a = ap.parse_args()

    tok = get_token()
    code, me = api("GET", "/user", tok)
    if code != 200:
        raise RuntimeError("token 无效或已过期，请重新授权")
    say(f"已认证：{me.get('login')}")

    if a.check:
        check(tok)
        return 0

    version = a.version or read_version()
    say(f"目标版本：v{version}{'  （演练模式）' if a.dry_run else ''}")

    if a.skip_build:
        zip_path = os.path.join(PROJECT, "dist", f"FrameBoost_v{version}.zip")
        if not os.path.exists(zip_path):
            raise RuntimeError(f"没有 {zip_path}，请去掉 --skip-build")
    elif a.dry_run:
        zip_path = os.path.join(PROJECT, "dist", f"FrameBoost_v{version}.zip")
        if not os.path.exists(zip_path):
            say("[演练] 未找到现成 zip，跳过大小核对")
            zip_path = os.path.join(PROJECT, "dist", "FrameBoost_v" + read_version() + ".zip")
    else:
        build()
        zip_path = make_zip(version)

    if a.sync_source:
        sync_source(version, tok, a.dry_run)

    if not a.skip_release:
        publish_release(zip_path, version, tok, a.dry_run, a.notes)

    say("完成 🎉" if not a.dry_run else "演练结束（远端未改动）")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as e:
        print(f"\n❌ {e}", file=sys.stderr)
        raise SystemExit(1)
