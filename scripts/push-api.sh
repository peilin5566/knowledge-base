#!/usr/bin/env bash
# GitHub API 通道推送脚本（绕过被代理拦截的 github.com git 端点）
# 背景：本机代理可访问 api.github.com，但 github.com 的 git smart-http 被拦截（502），
#       导致 `git push` / `git fetch` 失败。本脚本改用 REST API 完成同样操作。
# 用法：
#   bash scripts/push-api.sh              # 推送本地所有已提交但未上传的改动
#   bash scripts/push-api.sh --pull       # 先从远端拉取（覆盖工作区）
#   bash scripts/push-api.sh --status     # 只查看本地与远端差异

set -uo pipefail

REPO="peilin5566/knowledge-base"
API="https://api.github.com"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

log() { echo "$@"; }

# ---- 取令牌：优先环境变量，其次 git credential manager ----
get_token() {
  if [[ -n "${GH_TOKEN:-}" ]]; then echo "$GH_TOKEN"; return; fi
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then echo "$GITHUB_TOKEN"; return; fi
  printf "protocol=https\nhost=github.com\n\n" | git credential fill 2>/dev/null | sed -n 's/^password=//p'
}
TOKEN="$(get_token)"
if [[ -z "$TOKEN" ]]; then
  log "[错误] 未找到 GitHub 凭证。请设置 GH_TOKEN 环境变量，或先执行一次 git push 触发登录。"
  exit 1
fi

api() {
  local method="$1" path="$2" data="${3:-}"
  if [[ -n "$data" ]]; then
    curl -sS --max-time 40 -X "$method" -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" -H "X-GitHub-Api-Version: 2022-11-28" \
      -d "$data" "$API$path"
  else
    curl -sS --max-time 40 -X "$method" -H "Authorization: Bearer $TOKEN" \
      -H "X-GitHub-Api-Version: 2022-11-28" "$API$path"
  fi
}

remote_sha() {
  api GET "/repos/$REPO/git/ref/heads/main" \
    | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('object',{}).get('sha',''))" 2>/dev/null
}

# ---- 列出本地相对远端有改动的文件（已跟踪文件）----
changed_files() {
  local base="$1"
  git diff --name-only "$base" HEAD -- . ':(exclude)node_modules' ':(exclude)public' ':(exclude).quartz' 2>/dev/null
}

status_mode() {
  local rsha; rsha="$(remote_sha)"
  local lsha; lsha="$(git rev-parse HEAD)"
  log "本地 HEAD : $lsha"
  log "远端 main : ${rsha:-<获取失败>}"
  if [[ "$lsha" == "$rsha" ]]; then
    log "状态：完全同步 ✅"
  else
    log "状态：存在差异"
    log "远端领先的提交（需拉取）："
    git log --oneline HEAD.."$rsha" 2>/dev/null | sed 's/^/    /' | head -20
    log "本地领先的提交（需推送）："
    git log --oneline "$rsha"..HEAD 2>/dev/null | sed 's/^/    /' | head -20
  fi
}

pull_mode() {
  local rsha; rsha="$(remote_sha)"
  [[ -z "$rsha" ]] && { log "[错误] 无法获取远端 SHA"; exit 1; }
  log "正在通过 API 下载远端快照..."
  local tarball="/tmp/kb_sync_$$.tar.gz"
  curl -sSL --max-time 120 -H "Authorization: Bearer $TOKEN" \
    -o "$tarball" "$API/repos/$REPO/tarball/main" || { log "[错误] 下载失败"; exit 1; }
  local tmpd; tmpd="$(mktemp -d)"
  tar -xzf "$tarball" -C "$tmpd"
  local src; src="$(find "$tmpd" -maxdepth 1 -mindepth 1 -type d | head -1)"
  # 同步受版本控制的目录（保留 .git 与本地构建产物）
  for d in content .github scripts docs public; do
    [[ -d "$src/$d" ]] || continue
    mkdir -p "$d"
    rsync -a --delete --exclude='.DS_Store' "$src/$d/" "$d/" 2>/dev/null \
      || cp -r "$src/$d/." "$d/"
  done
  [[ -f "$src/README.md" ]] && cp "$src/README.md" README.md
  rm -rf "$tmpd" "$tarball"
  log "已从远端同步工作区。差异已体现在 git status 中。"
}

push_mode() {
  local rsha; rsha="$(remote_sha)"
  [[ -z "$rsha" ]] && { log "[错误] 无法获取远端 SHA"; exit 1; }

  local files; files="$(changed_files "$rsha")"
  # 补充未跟踪但需纳管的新文件（排除构建产物与依赖）
  local untracked
  untracked="$(git ls-files --others --exclude-standard -- content .github scripts docs 2>/dev/null)"
  local all
  all="$(printf '%s\n%s\n' "$files" "$untracked" | sed '/^$/d' | sort -u)"

  if [[ -z "$all" ]]; then
    log "没有需要上传的变更 ✅"
    return 0
  fi

  log "准备上传以下文件："
  echo "$all" | sed 's/^/    /'

  local current="$rsha"
  local count=0
  for f in $all; do
    [[ -f "$f" ]] || continue
    local payload fsha newblob
    payload="$(python -c "
import json,base64
d=open(r'''$f''','rb').read()
print(json.dumps({'message':'同步：更新 $f','content':base64.b64encode(d).decode(),'branch':'main','sha':'$current'}))
")"
    # 若文件在远端已存在，需带上其 blob sha 作为乐观锁
    fsha="$(api GET "/repos/$REPO/contents/$f" | python -c "import sys,json; print(json.load(sys.stdin).get('sha',''))" 2>/dev/null)"
    if [[ -n "$fsha" ]]; then
      payload="$(python -c "
import json,base64
d=open(r'''$f''','rb').read()
print(json.dumps({'message':'同步：更新 $f','content':base64.b64encode(d).decode(),'branch':'main','sha':'$fsha'}))
")"
    fi
    local resp; resp="$(api PUT "/repos/$REPO/contents/$f" "$payload")"
    newblob="$(echo "$resp" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('content',{}).get('sha','') or d.get('message',''))" 2>/dev/null)"
    if [[ -n "$newblob" && "$newblob" != *"message"* && "$newblob" != *"does not match"* ]]; then
      count=$((count+1))
      log "  ✓ $f"
      current="$(remote_sha)"
    else
      log "  ✗ $f -> $newblob"
    fi
  done
  log ""
  log "已上传 $count 个文件。"
  log "新远端 HEAD：$(remote_sha)"
}

case "${1:---push}" in
  --status) status_mode ;;
  --pull)   pull_mode ;;
  --push)   push_mode ;;
  *) log "用法: bash scripts/push-api.sh [--push|--pull|--status]"; exit 1 ;;
esac
