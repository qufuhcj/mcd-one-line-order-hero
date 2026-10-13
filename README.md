# 🍔 一句话麦麦省钱点单侠 · MCD One-Line Order Hero

> 🌟 **正在参加「麦当劳程序员节创意开发大赛」，榜单按 ⭐ Star 数排名**
> 如果它能帮你省下一顿饭钱，请点一下右上角的 **Star** —— 每个 Star 都是点单侠继续替你砍价的动力！🍔✨

> 💬 对 AI 说一句：**"两个人，60 块预算，想吃辣，半小时内送到"**
> 🏪 自动选店 → 🎫 一键领券 → 🧮 最优凑单 → 💰 比价下单 → 🛵 订单跟踪，全流程一个 Skill 搞定。

基于[麦当劳 MCP](https://github.com/M-China/mcd-mcp-server) 能力开发的点餐全链路 Copilot。市面上大多数省钱工具止步于"告诉你怎么点划算"，本项目的差异是：**算完直接帮你把单买了**。🛒

## 🤔 为什么是它

| 😩 痛点 | 🙈 传统做法 | 🦸 一句话麦麦省钱点单侠 |
|---|---|---|
| 凑单凑到头大 | 自己在小程序里反复加减商品 | 🧠 优化引擎在预算硬约束下秒出 Top-3 组合 |
| 优惠券散落各处 | 手动翻券包、逐个试 | 🎫 `auto-bind-coupons` 一键领满 + 多方案核价对比 |
| 配送费刺客 | 结算时才发现超预算 | 💸 核价阶段就对比"外送 vs 自取"，提前告诉你哪样更省 |
| 点完就忘 | 自己刷订单状态 | 🛵 支付后自动跟踪，取餐码/配送进度主动推送 |

## ✨ 功能特性

- 🧮 **预算约束凑单优化器**（`scripts/meal_optimizer.py`，纯标准库零依赖）
  - 主食 × 饮料 × 小食 × 甜品全组合枚举 + 多目标打分：口味偏好 × 预算利用率 × 营养均衡
  - 支持忌口硬约束（如"不要牛肉"）、人均热量上限、省钱/丰盛双模式
- 🔗 **全链路闭环**：选店 → 领券 → 凑单 → `calculate-price` 核价 → `create-order` 下单 → `query-order` 跟踪 → `cancel-order` 售后
- 🎯 **券 + 积分 + 套餐替换** 三重叠加精算，输出方案对比表（原价/券后/配送费/实付/热量）
- 🎭 **麦门人格彩蛋**：基于历史订单生成你的"点餐人格卡"，一键分享
- 🗺️ **全场景覆盖**：麦乐送、到店自取、得来速、预约单

## 🚀 快速开始

### 1️⃣ 申请 MCP Token
前往[麦当劳 MCP 开放平台](https://open.mcd.cn/mcp)，手机号登录后在控制台激活 Token。🔑

### 2️⃣ 配置 MCP Client
以 WorkBuddy 为例（Cursor / Cherry Studio / Trae 同理）：在自定义连接器中添加 MCP，填入 `mcp-config.example.json` 的内容，并将 `${MCD_MCP_TOKEN}` 替换为你的真实 Token（**真实配置文件请勿提交到仓库**）。

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": { "Authorization": "Bearer YOUR_MCP_TOKEN" }
    }
  }
}
```

### 3️⃣ 安装 Skill
将本仓库的 `SKILL.md` 与 `scripts/` 放入你的技能目录：
- 💼 WorkBuddy 用户级技能：`~/.workbuddy/skills/mcd-order-hero/`
- 🧩 其他 MCP Client：参考 `SKILL.md` 的工作流，将其作为系统提示词/规则文件加载

### 4️⃣ 开点！
直接在对话框里说人话即可：

```
两个人，60 块预算，想吃辣，半小时内送到
→ [🏪 选店 → 🎫 领券 → 🧮 引擎凑单 → 💰 3 套方案核价对比 → ✅ 确认后下单 → 🔗 输出支付链接]
```

## ⚙️ 优化引擎独立使用

引擎可脱离 AI 单独跑（方便调试与复现）：

```bash
# 2 人 60 元，偏好辣和鸡肉，输出 Top 3
python3 scripts/meal_optimizer.py --menu examples/sample_menu.json \
    --budget 60 --people 2 --like spicy,chicken --top 3

# 1 人 25 元，忌牛肉，省钱模式，JSON 输出
python3 scripts/meal_optimizer.py --menu examples/sample_menu.json \
    --budget 25 --avoid beef --mode saver --json
```

📊 实测输出：

```
【方案 1】人均 ¥27.00 × 2人 = ¥54.00（预算 ¥60，剩余 ¥6.00）
  组合：麦香鸡(¥15) + 麦辣鸡翅2块(¥12)
【方案 2】人均 ¥30.00 × 2人 = ¥60.00（预算 ¥60，剩余 ¥0.00）
  组合：麦辣鸡腿汉堡(¥22) + 小杯玉米杯(¥8)
```

## 📁 项目结构

```
mcd-one-line-order-hero/
├── SKILL.md                  # 🧠 Skill 编排指令（AI 的工作流大脑）
├── scripts/
│   └── meal_optimizer.py     # 🧮 凑单优化引擎（纯标准库）
├── examples/
│   └── sample_menu.json      # 📋 示例菜单（联调用）
├── MCP_INTEGRATION.md        # 🔗 麦当劳 MCP 集成说明（调用链与时序图）
├── mcp-config.example.json   # 🔑 MCP 配置模板（环境变量占位符）
├── CONTEST_DECLARATION.md    # 📜 参赛声明（官方原文）
└── README.md
```

## 👥 目标用户

- 💼 每次点麦当劳都要纠结"怎么凑最划算"的打工人
- 👨‍👩‍👧‍👦 多人拼单、需要按人头控预算的小团队
- 🤖 想体验"AI Agent 真正替我办事"的开发者

## 🙏 支持一下

读到这里还没点 Star 的朋友，你的预算允许，但点单侠的排名不允许 😢 → **右上角 ⭐ Star 一下**，让更多人用一句话吃上省钱麦麦！

## 📜 声明

本项目为麦当劳程序员创意开发大赛参赛作品，由作者独立开发，非麦当劳官方产品。餐品信息、价格及供应状态以麦当劳官方渠道实时结果为准；营养信息仅供参考，不构成医疗建议。使用麦当劳 MCP 服务须遵守其[服务规则](https://cdn.mcd.cn/cms/pages/MCPServerRules.html)。
