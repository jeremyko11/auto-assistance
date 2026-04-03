# 虚拟资料商业化项目 — 落地执行指南

> 目标：把「虚拟资料」从个人研究项目，变成可持续盈利的小生意

---

## 一、项目架构

```
auto-assistance/                 # 自动化助手主目录
├── material_pool.py             # 素材池管理（SQLite存储）
├── setup_schedules.bat          # 定时任务配置脚本
├── dispatcher/
│   ├── content_dispatcher.py   # 分发调度中心（核心引擎）
│   ├── cli.py                  # 交互菜单
│   └── poster.py              # 平台发布器
├── content_pool/               # 内容存储
│   ├── materials.db           # SQLite数据库
│   ├── raw/                   # 原始素材
│   ├── refined/               # 提炼后素材
│   ├── products/              # 知识产品
│   └── queue_*.json           # 待发布队列
└── 虚拟资料商业化项目_README.md # 本文档
```

---

## 二、快速启动

### 第一步：配置定时任务（推荐）

```powershell
# 以管理员身份运行
cd C:\Users\jeremyko11\WorkBuddy\Claw\auto-assistance
setup_schedules.bat
```

选择 `[1]` 配置每日完整流水线（推荐新手）

### 第二步：手动测试流程

```powershell
cd C:\Users\jeremyko11\WorkBuddy\Claw\auto-assistance

# 1. 运行完整流水线（首次跳过爬虫）
python dispatcher/content_dispatcher.py --mode full --skip-crawl

# 2. 查看日报
python dispatcher/content_dispatcher.py --mode report

# 3. 查看状态
python dispatcher/content_dispatcher.py --status

# 交互式菜单
python dispatcher/cli.py
python scripts/dispatcher/content_dispatcher.py --mode report
```

---

## 三、流水线各阶段说明

### 阶段1：爬取 (`--mode crawl`)

| 平台 | 脚本 | 频率 | 状态 |
|------|------|------|------|
| 抖音 | `douyin_crawler.py` | 每6小时 | ✅ 就绪 |
| 微博 | `weibo_crawler.py` | 每6小时 | ✅ 就绪 |
| 今日头条 | `toutiao_crawler.py` | 每6小时 | ✅ 就绪 |
| 微信公众号 | `wechat_crawler.py` | 待开发 | ⏳ |

### 阶段2：提炼 (`--mode refine`)

- 从原始素材池读取待处理内容
- 调用讯飞星辰LLM进行原子化提炼
- 输出：金句、案例、认知观点、行动指南
- 自动去重 + 风险标注

### 阶段3：改写 (`--mode rewrite`)

- 按平台格式改写（微博/小红书/抖音/公众号）
- 每条原子素材生成多平台版本
- 保存在素材池的 `platform_tags` 字段

### 阶段4：分发 (`--mode dispatch`)

- 微博：可接入API自动发布
- 小红书：生成文案，待手动发布
- 抖音：生成口播稿，待手动录制

---

## 四、核心模块详解

### 4.1 material_pool.py — 素材池管理

**数据模型：**

```
RawMaterial (原始素材)
├── platform / author / title / content
├── url / tags
└── status: pending → processing → processed

AtomMaterial (原子素材)
├── raw_id / type (quote/case/cognition/action)
├── content / platform_tags (各平台改写版本)
├── risk_level / shelf_life
└── hot_score / used_count

Product (知识产品)
├── name / type (ebook/report/collection)
├── price / content
├── atoms[] (关联的原子素材)
└── status: draft → published
```

**常用操作：**

```python
from scripts.material_pool import MaterialPool

pool = MaterialPool()

# 添加原始素材
pool.add_raw_material("微博", "九边", "标题", "正文内容...")

# 查询原子素材
atoms = pool.query_atoms(
    tags=["认知", "职场"],
    atom_types=["quote", "case"],
    risk_max=1,
    limit=50
)

# 创建产品
pool.create_product("认知升级电子书", "ebook", 49.0, "# Markdown内容...")

# 查看统计
print(pool.get_pool_stats())
```

### 4.2 content_dispatcher.py — 分发调度中心

**命令行用法：**

```powershell
# 运行完整流水线
python scripts/dispatcher/content_dispatcher.py --mode full

# 仅爬取
python scripts/dispatcher/content_dispatcher.py --mode crawl

# 仅提炼
python scripts/dispatcher/content_dispatcher.py --mode refine

# 仅改写
python scripts/dispatcher/content_dispatcher.py --mode rewrite

# 仅分发
python scripts/dispatcher/content_dispatcher.py --mode dispatch

# 生成日报
python scripts/dispatcher/content_dispatcher.py --mode report
```

---

## 五、私域转化路径

```
公域内容（抖音/微博/小红书）
        ↓ 引导"私信领取完整版"
私域添加（微信）
        ↓ 自动回复发送免费资料
种子社群（微信群/知识星球）
        ↓ 日常价值输出
付费转化（电子书/知识卡/年卡）
        ↓
深度服务（1对1咨询/定制报告）
```

### 5.1 引流内容设计

| 内容类型 | 平台 | 目的 | 引导动作 |
|----------|------|------|----------|
| 金句图 | 小红书/微博 | 吸睛 | "关注看更多" |
| 短视频 | 抖音/视频号 | 引流 | "评论区扣1领取" |
| 免费清单 | 公众号 | 沉淀 | "扫码添加微信" |
| 案例分享 | 社群 | 信任 | "了解付费产品" |

### 5.2 私域自动回复配置

建议配置微信自动回复：
```
添加好友 → 自动通过 → 发送：
"👋 感谢添加！送你一份《XXX》资料包，
包含10个亲测有效的思维模型。

回复【1】领取资料
回复【2】进入交流群
回复【3】了解付费产品"
```

---

## 六、产品矩阵

| 产品 | 价格 | 形态 | 目标客户 |
|------|------|------|----------|
| 单本电子书 | 29-99元 | PDF | 价格敏感型 |
| 专题合集 | 99-199元 | PDF | 深度用户 |
| 知识库年卡 | 699-999元/年 | 持续更新 | 高价值用户 |
| 深度报告 | 999-2999元/份 | 定制 | B端/高端C端 |
| 付费社群 | 199元/月 | 微信群 | 忠实粉丝 |

---

## 七、关键指标追踪

建议每周记录：

| 指标 | 定义 | 第一阶段目标 |
|------|------|--------------|
| 日均内容产出 | 发布内容条数 | 10条 |
| 私域新增 | 微信/社群新增人数 | 20人/天 |
| GMV | 当日成交金额 | 300元/天 |
| 转化率 | 私域→付费比例 | 1-2% |

---

## 八、下一步优化方向

### 优先级 P0（立即做）

1. **微信公众号爬虫** — 开发 `wechat_crawler.py`
2. **飞书内容管理库** — 接入飞书Bitable存储分发状态
3. **提示词迭代** — 优化LLM提炼质量

### 优先级 P1（第二阶段）

4. **自动发布API** — 微博/小红书API接入
5. **支付渠道** — 微信支付/知识星球开通
6. **代理分销** — 启动分销机制

### 优先级 P2（第三阶段）

7. **B站/小红书爬虫** — 扩展内容来源
8. **内容API化** — 第三方内容接入
9. **企业知识服务** — B端合作探索

---

## 九、常见问题

**Q: 爬虫被平台封了怎么办？**
A: 使用多账号 + 代理池，避免高频请求。建议设置请求间隔 > 30秒。

**Q: LLM提炼质量不稳定？**
A: 迭代提示词，增加示例。可以对提炼结果进行人工抽检。

**Q: 没有内容选题灵感？**
A: 使用 `/insight` skill 分析热点，或使用 `/dbs-hook` 优化开头。

**Q: 如何提高私域转化率？**
A: 关键在于建立信任。持续输出价值，不急于推销，让用户主动询问。

---

## 十、注意事项

1. **合规性**：不要爬取付费内容/私有数据，只用公开内容
2. **版权**：对原创者保持尊重，可以注明来源但不要声称原创
3. **自动化程度**：建议保留人工审核节点，避免出错
4. **数据备份**：定期备份 `material_pool.db` 和 `content_pool/` 目录

---

> 本方案会持续更新，欢迎反馈问题和建议。
