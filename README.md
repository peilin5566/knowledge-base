# 四维知识库

个人知识库：**科技 · 金融 · 医疗 · 人工智能** 四条主线，本地写作 + Git 版本化 + 每日自动情报入库 + GitHub Pages 免费托管。

底层：[Quartz 4](https://quartz.jzhao.xyz)（双链、反链、关系图谱、全文搜索、标签页、RSS）。

---

## 一、首次部署（4 步，约 10 分钟）

> 前置：已安装 [Git](https://git-scm.com/) 与 [Node.js 20+](https://nodejs.org/)。

### 1. 在 GitHub 上创建空仓库

打开 https://github.com/new ，仓库名建议 `knowledge-base`，**Public**（免费 Pages 需要公开），
**不要**勾选初始化 README / .gitignore / license。

### 2. 替换仓库地址占位符

把仓库根目录下两处 `YOUR_USERNAME` 换成你的 GitHub 用户名：

- `quartz.config.ts` → `baseUrl`
- `quartz.layout.ts` → 页脚链接

```bash
# 例如用户名是 zhangsan
sed -i "s/YOUR_USERNAME/zhangsan/g" quartz.config.ts quartz.layout.ts
```

（Windows 可用编辑器全局替换，或在 git bash 里执行上面的命令。）

### 3. 推送代码

```bash
cd knowledge-base
git init
git add -A
git commit -m "初始化知识库"
git branch -M main
git remote add origin https://github.com/<你的用户名>/knowledge-base.git
git push -u origin main
```

### 4. 开启 GitHub Pages

仓库页面 → **Settings → Pages → Source** 选 **GitHub Actions**，保存。
约 1–2 分钟后 Actions 跑完，访问：

```
https://<你的用户名>.github.io/knowledge-base/
```

之后每次 `git push` 都会自动重新构建发布。

---

## 二、目录结构

```
content/
  index.md                 首页
  科技/ 金融/ 医疗/ 人工智能/   四大主线（各自 index.md 为入口）
  方法论/知识库使用手册.md      写作规范与流程
  daily/
    arxiv/     arXiv 论文日报（每日 07:00 北京时间）
    policy/    医疗政策与指南（每日 08:30）
    markets/   金融行情日报（每日 22:00）
    trending/  科技开源趋势（每日 09:00）
  templates/   笔记模板（不会发布）
  private/     本地私有笔记（不会发布，也不会上传）
scripts/       四个自动抓取脚本（纯标准库，无需安装依赖）
.github/workflows/  部署与四条每日情报管道
```

---

## 三、日常写作

1. 用 [Obsidian](https://obsidian.md) 打开 `content/` 目录（`Open folder as vault`）
2. 新建笔记时套用 `templates/` 里的模板
3. 写完：

```bash
git add . && git commit -m "笔记：xxx" && git push
```

Frontmatter 规范见 `content/方法论/知识库使用手册.md`。

**不发布的方式**：frontmatter 写 `draft: true`，或放进 `content/private/`。

---

## 四、每日情报管道

| 工作流 | 时间（北京） | 生成内容 |
|---|---|---|
| `daily-arxiv.yml` | 07:00 | AI / 医疗 AI 最新论文卡片 |
| `daily-policy.yml` | 08:30 | PubMed 指南 + 卫健委动态 + WHO 要闻 |
| `daily-trending.yml` | 09:00 | GitHub Trending 热门项目 |
| `daily-markets.yml` | 22:00 | 黄金白银 / BTC ETH / 主要股指 |

首次部署后可手动触发验证：仓库 → **Actions** → 选对应工作流 → **Run workflow**。

### 自定义抓取范围

直接改脚本顶部常量：

- `scripts/fetch_arxiv.py` → `AI_QUERY`、`MED_QUERY`、`KEYWORDS`
- `scripts/fetch_policy.py` → `PUBMED_TERM`、`NHC_URLS`，或在 `daily-policy.yml` 的 env 里填 `POLICY_RSS`
- `scripts/fetch_trending.py` → 在 `daily-trending.yml` 的 env 里填 `LANGS`（如 `python,typescript`）
- `scripts/fetch_markets.py` → `TARGETS`、`COINS`

行情数据源采用主备双通道：Yahoo Finance（主）/ Stooq（备）、CoinGecko（主）/ Coinbase（备）；
某一路失败只影响对应单元格，不会中断生成。

---

## 五、本地预览

```bash
npm install              # 首次
npx quartz build --serve
```

浏览器打开 http://localhost:8080 ，改文件即时热更新。

---

## 六、网络受限环境下的推送（代理环境必读）

某些网络环境下，代理允许访问 `api.github.com` 但拦截 `github.com` 的 git 端点，
导致 `git push` / `git fetch` 报 `CONNECT tunnel failed, response 502`。
本仓库为此准备了两个 API 通道脚本（纯 Python 标准库，无需额外依赖）：

```bash
# 查看本地与远端差异
bash scripts/push-api.sh --status

# 从远端拉取（用 API tarball 覆盖工作区）
bash scripts/push-api.sh --pull

# 推送本地已提交的改动（用 REST API 逐文件提交）
bash scripts/push-api.sh --push

# 深度对齐：把远端 commit/tree/blob 对象写入本地 git 库，使本地 SHA 与远端完全一致
python scripts/sync_git_objects.py
```

令牌来源优先级：环境变量 `GH_TOKEN` / `GITHUB_TOKEN` → Git Credential Manager 已登录的凭证。

**验证是否受影响：**

```bash
curl -s -o /dev/null -w "api: %{http_code}\n" https://api.github.com/   # 200 即 API 通
git ls-remote origin                                                  # 报 502 即 git 端点被拦
```

若 API 通而 git 端点不通，用上面的脚本替代 `git push` / `git pull` 即可，
内容与历史都能保持一致。

---

## 七、常见问题

**Actions 构建失败？**
多半是 `package-lock.json` 未提交或 Node 版本问题；确认 `npm ci` 能本地跑通，再看 Actions 日志。

**推送被拒绝？**
确认仓库是空的（未初始化 README），或先 `git pull --rebase origin main`。

**每日情报没提交？**
Actions 需要写权限：Settings → Actions → General → Workflow permissions → 选 **Read and write permissions**。

**想绑自己的域名？**
Settings → Pages → Custom domain 填入域名，并在 DNS 加一条 CNAME 指向 `<用户名>.github.io`；
同时把 `quartz.config.ts` 的 `baseUrl` 改成该域名。

---

## 八、数据所有权

所有内容都是本地 Markdown 纯文本，仓库即备份。建议再加一层异地备份：

```bash
git clone --mirror https://github.com/<用户名>/knowledge-base.git  # 放到移动硬盘或其他远端
```

---

本项目基于 MIT 协议的 [Quartz](https://github.com/jackyzha0/quartz) 构建。
