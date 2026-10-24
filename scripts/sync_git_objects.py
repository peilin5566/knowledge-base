#!/usr/bin/env python3
"""
GitHub API 通道的 git 对象同步器 v3（精确 SHA 对齐）
背景：github.com 的 git smart-http 被代理拦截（CONNECT 502），但 api.github.com 可用。
      本脚本通过 REST API 重建远端的 commit/tree/blob 对象写入本地 git 库，
      使本地 HEAD 与远端 SHA 逐字节一致。

关键点：commit 对象里 author/committer 的时区偏移（如 +0800）无法从 API 直接读到
      （API 统一归一化为 UTC），因此对候选时区做暴力枚举，反解出与远端一致的偏移量。
用法：
      python scripts/sync_git_objects.py          # 同步并对齐
      python scripts/sync_git_objects.py --check  # 仅检查差异
"""
import base64
import datetime
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

REPO = "peilin5566/knowledge-base"
API = "https://api.github.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_WORKERS = 12

# 候选时区偏移（15 分钟粒度，覆盖 -12:00 ~ +14:00）
TZ_CANDIDATES = []
for _h in range(-12, 15):
    for _m in (0, 15, 30, 45):
        _off = _h * 60 + _m
        _sign = "+" if _off >= 0 else "-"
        _a = abs(_off)
        TZ_CANDIDATES.append(f"{_sign}{_a // 60:02d}{_a % 60:02d}")
TZ_CANDIDATES = sorted(set(TZ_CANDIDATES))
# 高频时区优先命中，绝大多数提交用这几个即可，减少枚举开销
TZ_COMMON = ["+0000", "+0800", "-0700", "-0500", "+0530", "+0900", "+0200", "+0100"]


def get_token():
    for env in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(env):
            return os.environ[env]
    try:
        out = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True, text=True, timeout=20,
        ).stdout
        for line in out.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


TOKEN = get_token()
if not TOKEN:
    sys.exit("未找到 GitHub 凭证，请设置 GH_TOKEN 环境变量")

_cache = {}


def api(path):
    if path in _cache:
        return _cache[path]
    req = urllib.request.Request(
        API + path,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "kb-sync",
        },
    )
    last = None
    for _ in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read().decode())
                _cache[path] = data
                return data
        except Exception as e:
            last = e
    raise RuntimeError(f"API 失败 {path}: {last}")


def git(*args, input_bytes=None, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(
        ["git", *args], cwd=ROOT, input=input_bytes,
        capture_output=True, timeout=300, env=e,
    )


_blob_done = set()


def write_blob(sha, content_bytes):
    p = git("hash-object", "-w", "--stdin", input_bytes=content_bytes)
    got = p.stdout.decode().strip()
    if got != sha:
        raise RuntimeError(f"blob SHA 不匹配：远端 {sha} 本地 {got}")
    return sha


def fetch_blobs_parallel(blobs):
    todo = [(s, p) for s, p in blobs if s not in _blob_done]
    if not todo:
        return

    def work(item):
        sha, _p = item
        blob = api(f"/repos/{REPO}/git/blobs/{sha}")
        write_blob(sha, base64.b64decode(blob["content"]))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        list(ex.map(work, todo))
    _blob_done.update(s for s, _ in todo)


def sync_tree(tree_sha):
    """递归重建 tree，返回 tree sha（与远端核对）"""
    t = api(f"/repos/{REPO}/git/trees/{tree_sha}")
    blobs, subtrees, commitlinks = [], [], []
    for e in t["tree"]:
        if e["type"] == "blob":
            blobs.append((e["sha"], e["path"], e["mode"]))
        elif e["type"] == "tree":
            subtrees.append((e["sha"], e["path"]))
        elif e["type"] == "commit":
            commitlinks.append((e["mode"], "commit", e["sha"], e["path"]))

    fetch_blobs_parallel([(s, p) for s, p, _ in blobs])

    entries = [(mode, "blob", sha, path) for sha, path, mode in blobs]
    for sha, path in subtrees:
        entries.append(("040000", "tree", sync_tree(sha), path))
    entries.extend(commitlinks)

    lines = [f"{m} {t} {s}\t{n}" for m, t, s, n in sorted(entries, key=lambda x: x[3])]
    p = git("mktree", input_bytes=("\n".join(lines) + "\n").encode())
    if p.returncode != 0:
        raise RuntimeError(f"mktree 失败: {p.stderr.decode()}")
    got = p.stdout.decode().strip()
    if got != tree_sha:
        raise RuntimeError(f"tree SHA 不匹配：远端 {tree_sha} 本地 {got}")
    return got


def parse_ts(date_str):
    """'2026-10-24T05:13:17Z' -> epoch 秒"""
    return int(datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
               .replace(tzinfo=datetime.timezone.utc).timestamp())


def build_commit_bytes(tree_sha, parent_shas, author, committer, message, tz_a, tz_c):
    lines = [f"tree {tree_sha}"]
    lines += [f"parent {p}" for p in parent_shas]
    lines.append(
        f"author {author['name']} <{author['email']}> {parse_ts(author['date'])} {tz_a}")
    lines.append(
        f"committer {committer['name']} <{committer['email']}> {parse_ts(committer['date'])} {tz_c}")
    body = message if message.endswith("\n") else message + "\n"
    return ("\n".join(lines) + "\n\n" + body).encode()


def commit_sha_of(raw):
    return hashlib.sha1(b"commit %d\0" % len(raw) + raw).hexdigest()


def solve_commit(c, tree_sha, parent_shas):
    """暴力枚举时区与换行组合，反解出与远端一致的 commit 对象
    关键点：
      1) author 与 committer 的时区偏移可能不同，需独立组合。
      2) API 返回的 message 不含尾部换行，而 git 对象里的 commit 消息
         通常带一个换行；两种都要尝试。"""
    target = c["sha"]
    raw_msg = c["message"]
    msg_variants = [raw_msg]
    if raw_msg.endswith("\n"):
        msg_variants.append(raw_msg.rstrip("\n"))
    msg_variants.append(raw_msg + "\n")
    # 去重但保持顺序
    seen, msg_bodies = set(), []
    for m in msg_variants:
        b = m.encode()
        if b not in seen:
            seen.add(b)
            msg_bodies.append(b)

    header = f"tree {tree_sha}\n" + "".join(f"parent {p}\n" for p in parent_shas)
    a_ts = parse_ts(c["author"]["date"])
    c_ts = parse_ts(c["committer"]["date"])
    a_ident = f"{c['author']['name']} <{c['author']['email']}>"
    c_ident = f"{c['committer']['name']} <{c['committer']['email']}>"

    # 先试高频时区（覆盖绝大多数提交），命中即返回；否则再全量枚举
    for pool in (TZ_COMMON, TZ_CANDIDATES):
        for tz_a in pool:
            a_line = f"author {a_ident} {a_ts} {tz_a}\n".encode()
            for tz_c in pool:
                c_line = f"committer {c_ident} {c_ts} {tz_c}\n".encode()
                mid = header.encode() + a_line + c_line + b"\n"
                for body in msg_bodies:
                    raw = mid + body
                    if commit_sha_of(raw) == target:
                        return raw, tz_a, tz_c
        if pool is TZ_COMMON:
            continue
    return None, None, None


def main():
    check_only = "--check" in sys.argv
    remote_head = api(f"/repos/{REPO}/git/ref/heads/main")["object"]["sha"]
    local_head = git("rev-parse", "HEAD").stdout.decode().strip()

    print(f"远端 HEAD: {remote_head}")
    print(f"本地 HEAD: {local_head}")
    if remote_head == local_head:
        print("已完全对齐 ✅")
        return 0
    if check_only:
        print("存在差异（--check 模式）")
        return 1

    print("\n收集远端提交链...", flush=True)
    commits = {}

    def collect(sha, depth=0):
        if sha in commits or depth > 40:
            return
        c = api(f"/repos/{REPO}/git/commits/{sha}")
        commits[sha] = c
        for p in c.get("parents", []):
            collect(p["sha"], depth + 1)

    collect(remote_head)
    print(f"  共 {len(commits)} 个提交")

    built = {}
    print("\n重建对象（tree → commit，暴力反解时区）...", flush=True)
    # 必须按拓扑序（父提交在前）处理，否则父对象尚未就绪
    def depth(sha, seen=None):
        seen = seen or set()
        if sha in seen:
            return 0
        seen.add(sha)
        c = commits.get(sha)
        if not c:
            return 0
        ps = c.get("parents", [])
        return 1 + max([depth(p["sha"], seen) for p in ps], default=0)

    ordered = sorted(commits.keys(), key=lambda s: (depth(s), s))
    for sha in ordered:
        c = commits[sha]
        parent_shas = [p["sha"] for p in c.get("parents", [])]
        for ps in parent_shas:
            if ps not in built:
                sys.exit(f"父提交未就绪: {ps}")
        tree_sha = sync_tree(c["tree"]["sha"])
        raw, tz_a, tz_c = solve_commit(c, tree_sha, parent_shas)
        if raw is None:
            print(f"  ! 无法反解 {sha[:8]} 的时区/元数据")
            return 2
        p = git("hash-object", "-w", "-t", "commit", "--stdin", input_bytes=raw)
        got = p.stdout.decode().strip()
        if got != sha:
            print(f"  ! 写入校验失败 {sha[:8]} != {got[:8]}")
            return 2
        built[sha] = got
        print(f"  ✓ {sha[:8]} (author {tz_a} / committer {tz_c})", flush=True)

    if built.get(remote_head) != remote_head:
        print("远端 HEAD 未能正确重建，放弃切换引用。")
        return 2

    dirty = git("status", "--porcelain").stdout.decode().strip()
    if dirty:
        print("\n检测到未提交改动，先 stash 保护...")
        git("stash", "push", "-u", "-m", f"sync_git_objects 自动备份 {remote_head[:8]}")

    git("update-ref", "refs/heads/main", remote_head, local_head)
    git("update-ref", "refs/remotes/origin/main", remote_head)
    git("reset", "--hard", remote_head)
    git("clean", "-fd", "-e", "node_modules", "-e", "public", "-e", ".quartz")

    if git("stash", "list").stdout.decode().strip():
        git("stash", "pop")

    print(f"\n同步后本地 HEAD: {git('rev-parse','HEAD').stdout.decode().strip()}")
    print("git log:")
    print(git("log", "--oneline", "-12").stdout.decode())
    print(git("status", "-sb").stdout.decode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
