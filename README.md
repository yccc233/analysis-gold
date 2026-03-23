# 黄金基金智能交易辅助决策系统

自动完成：**黄金价格趋势调研 → 实时价格获取（同步汇率）→ 波动分析与决策评级 → 邮件通知**，全流程定时循环执行。

## 项目结构

```
gtm/
├── main.py                 # 唯一启动入口，定时循环编排全流程
├── start.sh                # 后台启动脚本
├── .env                    # 密钥与配置
├── .env.example            # 配置模板
├── gold/                   # 黄金价格获取模块
│   ├── api.py              # GoldAPI(XAU/USD) + FX(USD/CNY) 获取，10s超时重试3次
│   ├── db.py               # SQLite 数据层
│   └── config.py           # 常量配置
├── research/               # 调研模块
│   └── tavily.py           # Tavily API 搜索+爬取，失败自动重试2次
├── analysis/               # 分析决策模块
│   └── decision.py         # 统计计算 + DeepSeek 大模型综合分析 + 降级规则兜底
├── notify/                 # 邮件通知模块
│   └── email.py            # QQ邮箱 SMTP SSL，评级>3星触发
├── utils/                  # 公共工具
│   ├── dotenv.py           # load_dotenv（无外部依赖）
│   └── logger.py           # 统一日志（控制台 + logs/gtm.log）
└── logs/                   # 日志目录（运行时生成）
```

## 数据流

```
定时触发
    │
    ▼
Tavily 调研 ──→ 技术面/基本面/市场情绪数据
    │
    ▼
GoldAPI 金价(XAU/USD) + ER-API 汇率(USD/CNY) 同步获取
    │
    ▼
SQLite 历史数据 + 当前价格 ──→ 统计计算（7日/30日均价、波动率、支撑压力位、趋势）
    │
    ▼
组装 Prompt ──→ DeepSeek 大模型 ──→ 决策评级(1-5星) + 分析摘要
    │
    ├── 评级>3星 ──→ 邮件通知
    └── 评级≤3星 ──→ 仅记录日志
```

## 决策评级

| 星级 | 含义 |
|------|------|
| ★★★★★ 强烈推荐买入 | 技术面低位 + 基本面利好 + 市场情绪积极 |
| ★★★★☆ 推荐买入 | 两个维度支持买入，风险收益比良好 |
| ★★★☆☆ 建议观望 | 多空因素交织，方向不明朗 |
| ★★☆☆☆ 不推荐操作 | 利空因素多于利多，建议谨慎 |
| ★☆☆☆☆ 极不推荐操作 | 技术面高位 + 基本面利空 + 市场情绪悲观 |

LLM 调用失败时自动降级为规则打分兜底。

## 快速开始

### 1. 配置

```bash
cp .env.example .env
# 编辑 .env 填入各 API Key
```

必需配置：

| 变量 | 说明 |
|------|------|
| `GOLDAPI_KEY` | [GoldAPI.net](https://goldapi.net) API Key |
| `TAVILY_API_KEYS` | [Tavily AI](https://app.tavily.com) Key，多个逗号分隔轮换 |
| `LLM_API_URL` | 大模型 API 地址 |
| `LLM_API_KEY` | DeepSeek API Key |
| `LLM_MODELS` | 模型列表，逗号分隔轮换（如 `deepseek-chat,deepseek-reasoner`） |
| `SMTP_HOST/PORT/USER/PASSWORD` | QQ邮箱 SMTP 配置 |
| `NOTIFY_TO` | 收件邮箱 |

可选配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `POLL_INTERVAL` | 3600 | 轮询间隔（秒），默认1小时 |

### 2. 创建虚拟环境（可选）

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate
```

### 3. 启动

```bash
# 后台启动
bash start.sh

# 或直接前台启动
python main.py
```

## 日志

- 程序日志：`logs/gtm.log`（自动生成）
- 启动日志：`logs/gtm_startup.log`（start.sh 记录）
- 每次 LLM 调用前输出完整 System Prompt 和 User Prompt，供人工复核

## 邮件通知格式

- **触发条件**：评级 > 3星
- **标题**：`黄金基金决策提醒-YYYY-MM-DD HH:MM-★★★★`
- 邮件内容包含当前价格、评级、分析摘要、数据理由、调研理由

## 注意事项

- 所有黄金价格统一以 **元/克** 为单位，保留2位小数
- 金价与汇率**同步获取**，消除换算时间差
- 金价和汇率 API 超时后**自动重试 2 次**，间隔 2 秒
- 仅依赖 Python 标准库，无外部依赖
