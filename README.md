# 每日职位抓取 (Job Tracker)

一个**可插拔**的职位抓取框架：从多个远程/技术职位平台抓取最新职位，应用筛选后归档为 Markdown，可选推送到个人微信（PushPlus / Server酱）。支持订阅（每日自动）+ 搜索（关键词过滤）两种模式。

> 设计思路与 [info-scraper](https://github.com/kabbmam-netizen/info-scraper) / [news-daily](https://github.com/kabbmam-netizen/news-daily) 一脉相承：纯 API 抓取，无数据库、无付费 API；源做成模块，加源只需新建一个文件 + 配置一条。

## 当前数据源

| 模块 | 来源 | 抓什么 |
|------|------|--------|
| `remoteok` | RemoteOK API | 全球远程技术岗 |
| `remotive` | Remotive API | 远程各类岗（开发/设计/支持等） |
| `fourdayweek` | 4 Day Week API | 4 天工作制职位 |

加新源：在 `src/sources/` 下新建一个继承 `BaseJobSource` 的模块，自动注册，无需改其他代码。

> **覆盖说明**：以上 3 个源覆盖**英文远程/技术岗**。中文职位（BOSS/拉勾等）需 Playwright 爬虫，作为后续增强。职位数据天然分散在各平台，"全网"不现实，这里是"多源聚合"。

## 两种使用模式

- **订阅**（默认）：每天抓所有源 -> 应用 config.yml 里的 filters -> 去重 -> 归档 + 微信推送
  ```bash
  python -m src.main
  ```
- **搜索**：在订阅基础上，额外按关键词过滤（标题+公司+标签匹配）
  ```bash
  python -m src.main --search "Python"
  ```

## 筛选

在 `config.yml` 的 `filters` 块配置（对订阅和搜索都生效）：

```yaml
filters:
  keyword_include: ["Python", "Backend"]   # 只保留提到这些词的职位
  keyword_exclude: ["Intern", "Junior"]     # 排除提到这些词的
  salary_min: 80000                          # 排除年薪上限低于此值的（USD）
```

留空列表即关闭该筛选。`salary_min=0` 表示不过滤薪资。

## 本地运行

```bash
pip install -r requirements.txt
python -m src.main
```

生成的摘要存放在 `digests/` 目录。设置 `WEBHOOK_URL` 环境变量后会同时推送：

```bash
# Windows PowerShell
$env:WEBHOOK_URL="https://www.pushplus.plus/send?token=xxx"
python -m src.main

# Linux / macOS
export WEBHOOK_URL="https://www.pushplus.plus/send?token=xxx"
python -m src.main
```

## 加一个新数据源

1. 在 `src/sources/` 下新建 `mysource.py`：

   ```python
   from .base import BaseJobSource
   from ..items import JobItem

   class MySource(BaseJobSource):
       name = "mysource"            # 必须与 config.yml 的 block 名一致
       display_name = "我的来源"
       emoji = "🔖"

       def fetch(self, config: dict):
           # 抓取逻辑，失败返回 []，不要抛异常
           return [JobItem(title=..., url=..., company=..., ...)]
   ```

2. 在 `config.yml` 加配置块：

   ```yaml
   sources:
     mysource:
       enabled: true
       # ...你的配置
   ```

3. 完成。下次运行自动发现并抓取该源。

## 部署到 GitHub Actions

1. 把项目推到 GitHub 仓库
2. （可选）配 webhook secret：仓库 **Settings -> Secrets and variables -> Actions -> New repository secret**，Name 填 `WEBHOOK_URL`，Value 填 PushPlus / Server酱 / 企业微信 / 钉钉地址
3. 手动触发验证：**Actions** -> `Daily Job Scrape` -> `Run workflow`（可填关键词触发搜索模式）
4. 之后每天北京时间早上 6 点自动运行

## 获取 Webhook 地址

### PushPlus（推送到个人微信，推荐）
微信扫码登录 https://www.pushplus.plus/ 并关注公众号 + **完成实名认证**（未实名无法发送），拿到 token，拼成 `https://www.pushplus.plus/send?token={token}` 作为 `WEBHOOK_URL`。

### Server酱（推送到个人微信）
微信扫码登录 https://sct.ftqq.com/ 拿到 SendKey，拼成 `https://sctapi.ftqq.com/{sendkey}.send`。

### 企业微信群 / 钉钉
见 `.env.example` 顶部说明。

## 项目结构

```
job-scraper/
├── .github/workflows/daily-scrape.yml   # GitHub Actions 定时任务
├── digests/                             # 生成的每日摘要（自动提交）
├── src/
│   ├── main.py                          # 入口：发现源 -> 抓取 -> 筛选 -> 去重 -> 推送
│   ├── config.py                        # 读取 config.yml（含 filters）
│   ├── items.py                         # JobItem 数据类
│   ├── notifiers.py                     # PushPlus/Server酱/企业微信/钉钉 推送
│   └── sources/
│       ├── __init__.py                  # 源注册表（自动发现）
│       ├── base.py                      # BaseJobSource 抽象基类
│       ├── remoteok.py                  # RemoteOK
│       ├── remotive.py                  # Remotive
│       └── fourdayweek.py               # 4 Day Week
├── config.yml                           # 数据源配置 + 筛选规则
├── requirements.txt
└── README.md
```

## 工作原理

1. `config.yml` 定义各数据源配置 + 全局筛选规则
2. `src/sources/__init__.py` 自动发现 `src/sources/` 下所有 `BaseJobSource` 子类
3. 每个 enabled 的源调用 `fetch()`，失败返回 `[]` 不影响其他源
4. 应用 `filters`（关键词包含/排除 + 薪资）+ 可选 `--search` 关键词
5. 按 URL 跨源去重、按时间倒序、截断到 `max_total_items`
6. 生成 Markdown 归档 + 微信推送（前 N 条速览）
7. GitHub Actions 把摘要提交回仓库（push 冲突自动 rebase 重试）

## License

MIT - 可自由使用、修改、分发。
