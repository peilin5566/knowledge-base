---
title: 四维知识库
description: 科技 · 金融 · 医疗 · 人工智能 的个人知识库
tags:
  - 首页
---

# 四维知识库

一个长期主义的知识库：本地写作、Git 版本化、每日自动情报入库、全网可访问的静态站点。

底层是 [Quartz 4](https://quartz.jzhao.xyz)，支持 **双链 `[[笔记]]`、反向链接、关系图谱、全文搜索、标签页、RSS**。

## 四大主线

| 主线 | 入口 | 关注什么 |
|---|---|---|
| 科技 | [[科技/index\|科技]] | 前沿技术、产业趋势、开源项目 |
| 金融 | [[金融/index\|金融]] | 多市场行情、投资逻辑、研报与复盘 |
| 医疗 | [[医疗/index\|医疗]] | 医务管理、政策规范、临床指南、质量安全 |
| 人工智能 | [[人工智能/index\|人工智能]] | 模型进展、Agent、医疗 AI 落地 |

## 每日情报（GitHub Actions 自动生成）

- [[daily/arxiv/index\|arXiv 论文日报]] — AI 与医疗 AI 最新论文，每日 07:00（UTC）
- [[daily/policy/index\|医疗政策与指南]] — 卫健委/医政/指南更新，每日 00:30（UTC）
- [[daily/markets/index\|金融行情日报]] — 黄金/加密/美股/港股/A股，每日 22:00（UTC）
- [[daily/trending/index\|科技开源趋势]] — GitHub Trending 热门项目，每日 09:00（UTC）

## 怎么用

1. 本地用 **Obsidian** 打开本仓库的 `content/` 目录（Vault = `content`）
2. 从 `templates/` 里挑模板新建笔记，`Ctrl+N` → 选模板
3. 写完 `git add . && git commit -m "笔记：xxx" && git push`
4. 约 1 分钟后，GitHub Actions 自动构建并发布到 Pages

> 详细规范见 [[方法论/知识库使用手册]]

## 笔记成熟度约定

- 🌱 **seedling** 草稿/灵感，随时可能改
- 🌿 **budding** 正在整理，结构已成型
- 🌳 **evergreen** 成熟笔记，可长期引用

在 frontmatter 里写 `maturity: evergreen` 即可；不写默认为 seedling。
