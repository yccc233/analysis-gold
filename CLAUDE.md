# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

黄金基金智能交易辅助决策系统。自动完成：黄金价格趋势调研 → 实时价格获取 → 波动分析与决策评级 → 邮件通知，全流程定时循环执行。

## Project Structure

```
main.py                # 唯一启动入口，编排全流程并定时循环
start.sh               # 启动脚本（自动激活 venv）
.env                   # 密钥与配置（GOLDAPI_KEY, TAVILY_API_KEY, SMTP_*）
gold/                  # 黄金价格获取模块
├── config.py          # 常量（单位换算、FX TTL、DB/FX缓存路径）
├── db.py              # SQLite 数据层（init_db, insert_price, get_latest_price, get_history）
├── api.py             # GoldAPI + FX 汇率调用 + fetch_and_store
├── gold_prices.db     # 运行时生成
└── .fx_cache.json     # 运行时生成
research/              # Tavily 调研模块
└── tavily.py          # 搜索+爬取，自动重试2次，结构化输出
analysis/              # 波动分析与决策模块
└── decision.py        # 数据统计 + DeepSeek大模型综合分析 + 降级规则兜底
notify/                # 邮件通知模块
└── email.py           # QQ邮箱 SMTP SSL，星级>3时触发
utils/                 # 公共工具
├── dotenv.py          # load_dotenv（无外部依赖）
└── logger.py          # 统一日志（控制台 + logs/gtm.log）
logs/                  # 日志目录（运行时生成）
```

## Running

```bash
# 直接启动（定时循环，默认每小时执行一次）
python main.py

# 通过脚本启动（自动激活 venv）
bash start.sh

# 自定义间隔（通过 .env 中 POLL_INTERVAL=秒数）
```

## Architecture

- **数据流**: main.py 定时循环 → research/tavily.py (Tavily调研) → gold/api.py (实时金价) → analysis/decision.py (综合分析评级) → notify/email.py (邮件通知)
- **模块职责**:
  - `gold/`: 价格获取与存储。GoldAPI(XAU/USD) + Open ER-API(USD→CNY) → 换算为 元/克 → SQLite。FX汇率缓存TTL 6小时。
  - `research/`: Tavily API 搜索+爬取。关键词覆盖价格趋势、支撑压力位、美元指数关联。失败自动重试2次，仍失败则仅基于价格数据分析。
  - `analysis/`: 计算7日/30日均价、波动率、支撑位/压力位、趋势形态，组装完整Prompt调用DeepSeek大模型从技术面/基本面/市场情绪三维度综合分析，输出决策评级(1-5星)。API失败时降级为规则打分兜底。
  - `notify/`: QQ邮箱 SMTP SSL。仅评级>3星时触发。标题格式: `黄金基金决策提醒-YYYY-MM-DD HH:MM-★★★★`。
  - `utils/`: load_dotenv、统一日志（含模块名、时间、异常原因）。

## Configuration (.env)

```
GOLDAPI_KEY=xxx              # 必需 — GoldAPI.net API Key
TAVILY_API_KEYS=tvly-key1,tvly-key2  # 必需 — Tavily Key，多个逗号分隔轮换使用
SMTP_HOST=smtp.qq.com        # 邮件 SMTP 主机
SMTP_PORT=465                # SMTP 端口
SMTP_USER=xxx@qq.com         # 发件邮箱
SMTP_PASSWORD=xxx            # QQ邮箱授权码
NOTIFY_TO=xxx@xxx.com        # 收件邮箱
POLL_INTERVAL=3600           # 可选 — 轮询间隔秒数（默认3600）
LLM_API_URL=https://api.deepseek.com/v1/chat/completions  # 必需 — 大模型API地址
LLM_API_KEY=sk-xxx          # 必需 — DeepSeek API Key
LLM_MODELS=deepseek-chat,deepseek-reasoner  # 必需 — 模型列表，逗号分隔，轮换使用
```

## Coding Conventions

- Python 3, 4-space indentation, snake_case.
- 仅依赖标准库，无外部包。
- 所有黄金价格统一以 元/克 为单位，保留2位小数。
- 日志通过 utils/logger.py 统一管理，不直接 print。
