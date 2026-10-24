#!/usr/bin/env python3
"""
GitHub API 通道的 git 对象同步器（并行 + 缓存版）
用途：当 github.com 的 git smart-http 端点被代理拦截（CONNECT 502）时，
      通过 REST API 把远端的 commit / tree / blob 对象写入本地 git 对象库，
      使本地 HEAD 与远端 SHA 完全对齐，git log / git diff 正常工作。
优化：blob 全局缓存（同一 blob 只下载一次）、树遍历并行下载。
用法：
      python scripts/sync_git_objects.py          # 同步
      python scripts/sync_git_objects.py --check  # 仅检查
"""
import base64
import json
import os
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = "peilin5566/knowledge-base"
API = "https://api.github.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_WORKERS = 12


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
    """带缓存的 API 调用"""
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
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read().decode())
                _cache[path] = data
                return data
        except Exception as e:
            if attempt == 2:
                raise
    return None


def git(*args, input_bytes=None, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(
        ["git", *args], cwd=ROOT, input=input_bytes,
        capture_output=True, timeout=300, env=e,
    )


_blob_done = set()
_blob_lock_present = set()


def write_blob(sha, content_bytes):
    p = git("hash-object", "-w", "--stdin", input_bytes=content_bytes)
    got = p.stdout.decode().strip()
    if got != sha:
        raise RuntimeError(f"blob SHA 不匹配：远端 {sha} 本地 {got}")
    return sha


def fetch_blobs_parallel(blobs):
    """并行下载 blob 列表 [(sha, path)]"""
    todo = [(s, p) for s, p in blobs if s not in _blob_done]
    if not todo:
        return
    print(f"  下载 {len(todo)} 个 blob（并行 {MAX_WORKERS}）...", flush=True)
    done = 0

    def work(item):
        sha, path = item
        blob = api(f"/repos/{REPO}/git/blobs/{sha}")
        data = base64.b64decode(blob["content"])
        write_blob(sha, data)
        return sha

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(work, it): it for it in todo}
        for fut in as_completed(futures):
            try:
                sha = fut.result()
                _blob_done.add(sha)
                done += 1
                if done % 25 == 0:
                    print(f"    {done}/{len(todo)}", flush=True)
            except Exception as e:
                print(f"    ! 失败 {futures[fut][1]}: {e}", flush=True)
    print(f"  blob 完成 {done}/{len(todo)}", flush=True)


def sync_tree(tree_sha):
    """递归拉取 tree；并行下载 blob 后再组装"""
    t = api(f"/repos/{REPO}/git/trees/{tree_sha}")

    blobs = []      # (sha, path, mode)
    subtrees = []   # (sha, name, mode)
    commitlinks = []

    for e in t["tree"]:
        if e["type"] == "blob":
            blobs.append((e["sha"], e["path"], e["mode"]))
        elif e["type"] == "tree":
            subtrees.append((e["sha"], e["path"], e["mode"]))
        elif e["type"] == "commit":
            commitlinks.append((e["mode"], "commit", e["sha"], e["path"]))

    fetch_blobs_parallel([(s, p) for s, p, _ in blobs])

    entries = []
    # 必须沿用远端原始 mode，否则 tree SHA 会与远端不一致
    for sha, path, mode in blobs:
        entries.append((mode, "blob", sha, path))
    for sha, path, mode in subtrees:
        sub = sync_tree(sha)
        entries.append(("040000", "tree", sub, path))
    for e in commitlinks:
        entries.append(e)

    lines = []
    for mode, otype, sha, name in sorted(entries, key=lambda x: x[3]):
        lines.append(f"{mode} {otype} {sha}\t{name}")
    payload = ("\n".join(lines) + "\n").encode()
    p = git("mktree", input_bytes=payload)
    if p.returncode != 0:
        raise RuntimeError(f"mktree 失败: {p.stderr.decode()}")
    return p.stdout.decode().strip()


def build_commit(commit_sha):
    c = api(f"/repos/{REPO}/git/commits/{commit_sha}")
    tree_sha = sync_tree(c["tree"]["sha"])
    parents = [build_commit(p["sha"]) for p in c.get("parents", [])]

    au, co = c["author"], c["committer"]
    env = {
        "GIT_AUTHOR_NAME": au["name"],
        "GIT_AUTHOR_EMAIL": au["email"],
        "GIT_AUTHOR_DATE": au["date"],
        "GIT_COMMITTER_NAME": co["name"],
        "GIT_COMMITTER_EMAIL": co["email"],
        "GIT_COMMITTER_DATE": co["date"],
    }
    args = ["commit-tree", tree_sha]
    for p in parents:
        args += ["-p", p]
    p = git(*args, input_bytes=c["message"].encode(), env=env)
    if p.returncode != 0:
        raise RuntimeError(f"commit-tree 失败: {p.stderr.decode()}")
    got = p.stdout.decode().strip()
    if got != commit_sha:
        print(f"  ! commit SHA 不匹配 远端={commit_sha} 本地={got}", flush=True)
    return got


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

    print("\n通过 API 重建远端 git 对象...\n", flush=True)
    built = build_commit(remote_head)

    if built != remote_head:
        print(f"\n重建 SHA 与远端不一致（远端 {remote_head} / 本地 {built}），已放弃切换引用。")
        return 2

    # 保护工作区：先 stash 未提交改动，避免 reset --hard 丢失本地工作
    dirty = git("status", "--porcelain").stdout.decode().strip()
    if dirty:
        print("\n检测到未提交改动，先 stash 保护...")
        git("stash", "push", "-u", "-m", f"sync_git_objects 自动备份 {remote_head[:8]}")

    git("update-ref", "refs/heads/main", built, local_head)
    git("update-ref", "refs/remotes/origin/main", built)
    git("reset", "--hard", built)
    git("clean", "-fd", "-e", "node_modules", "-e", "public", "-e", ".quartz")

    # 恢复之前 stash 的本地改动
    stash_out = git("stash", "list").stdout.decode()
    if stash_out.strip():
        git("stash", "pop")

    print(f"\n同步后本地 HEAD: {git('rev-parse','HEAD').stdout.decode().strip()}")
    print("git log:")
    print(git("log", "--oneline", "-12").stdout.decode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
