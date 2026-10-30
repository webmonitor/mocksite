# webmonitor-mocksite

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

一个可控、可复现的 mock 目标站，用来验证内容监控/采集系统是否**抓对了页面、识别了数据变化、能回到基线**。站点不绑定采集技术栈：同一份页面同时提供稳定的 CSS 与 XPath 选择器，状态通过 HTTP 管理 API 和浏览器控制台修改。

演示主题是**单条高校通知公告**，结构对齐 `notice.xidian.edu.cn` / `notice.ysu.edu.cn` 这类真实门户。WebMonitor 的真实用法就是盯住一条通知，内容一变就发邮件；因此这里只提供一条通知详情页，不提供列表、分页或多条数据。

> **当前状态（2026-10-30）**
>
> - 已完成：阶段 0 工具链、阶段 1 状态内核、阶段 2 双端口 HTTP、阶段 3 单页管理后台、阶段 5 容器与运行、阶段 9 单条通知收敛。
> - 运行形态：**一个进程、一个事件循环、两个 uvicorn 监听器共享同一个 `StateStore`**；站点 `9000`，管理 `9001`。
> - 站点内容：一条通知详情页（static/SSR）、点击次数 JSON、健康检查、本地页面资产。
> - 管理端：单页控制台（场景、手动编辑、实时预览、事实摘要）与 `/_admin/*` API。
> - 构建方式：**只从本仓库源码构建，不发布 GHCR 镜像**；`compose.yaml` 构建本地的 `mocksite:local`。
> - 未实现：阶段 6/P4 的 `/flaky`、`/slow`、私网重定向与子资源探针。故障注入、列表/分页、React/Vue 目标页、结构性破坏场景均已移除或不在范围内（见 [变更记录](changelog/README.md)）。
>
> 本 README 是当前目标契约；[交付计划](plan/README.md) 跟踪已完成与未实现项；[变更记录](changelog/README.md) 是按日期保留的历史记录，其中的数字是当日实测，不代表本次文档整理重新验证过。

文档入口：[交付计划与任务进度](plan/README.md) · [变更记录](changelog/README.md) · [浏览器验收](tests/acceptance/README.md)。

## 1. 项目目标与边界

mocksite 负责产生受控输入，并给出可核对的页面状态；监控平台负责采集、提取、比较、调度和通知。

| 需要验证的问题 | mocksite 提供的条件 |
|---|---|
| 内容是否真的发生变化 | 固定默认数据 + 绝对覆盖的场景，每次只改指定字段 |
| HTTP 与浏览器采集有何差异 | 服务端渲染正文，点击次数由页面脚本异步填充 |
| 采集器是否选对节点 | 金额、日期、标题都存在形状相似但语义不同的诱饵节点 |
| 数据改回原值后平台如何表现 | 场景不叠加；`baseline`/reset 恢复与默认值逐字节相同的业务内容 |
| 管理端口是否真正隔离 | 基础 Compose 只发布 9000；9001 仅控制网络/开发 overlay 可达 |
| Agent 出口限制是否生效 | Agent 部署方把 egress 接入与 mocksite 共享的 Docker 网络，并只放行 `site:9000` |

任何采集方都可以接入：页面同时给出 CSS 与 XPath，便于 HTTP 抓取、无头浏览器、Selenium 等验证各自的提取与等待逻辑。各平台的错误码、重试策略和告警能力由平台自身契约决定。

本项目不实现监控引擎、邮件发送、多用户与权限管理、任意脚本执行或真实网站的反爬绕过。mocksite 也不替代采集方自带的 smoke fixture。

## 2. 使用流程

一次完整验证按以下顺序执行：

1. 打开管理后台，输入 `MOCKSITE_TOKEN`，确认状态、`revision` 和默认数据。
2. 在监控平台配置目标 URL 与选择器，完成首次采集并建立基线。
3. 在后台应用一个场景（或手动编辑通知字段），确认右侧实时预览和返回的 `revision` 已变化。
4. 触发或等待平台下一次采集，核对页面内容、提取结果和平台事件。
5. 验证结束后显式恢复：应用 `baseline` 或点击“恢复默认（reset）”，再采集一次确认回到基线。

mocksite 不等待平台采集完成。验证脚本必须以平台的运行结果为准，不能仅凭固定休眠时间判定成功。一个实例只服务一组串行场景；需要并行验证时，为每组测试启动独立实例。

## 3. 页面与数据契约

### 3.1 页面形态

| 路径 | 内容与渲染方式 | 主要验证点 |
|---|---|---|
| `/static/notice` | 通知详情页：状态提交时预渲染完整 HTML，请求时直接返回；点击次数由脚本异步填充 | HTTP 提取基线、诱饵节点、缓存页 |
| `/ssr/notice` | 同一份详情页，每次请求根据当前状态渲染 | 服务端实时渲染与静态页的一致性 |
| `/api/views` | 点击次数 JSON：`{"views": 128, "revision": 0}` | 脚本异步填充的计数 |
| `/health` | `{"status":"ok"}` | 进程存活，不随业务数据变化 |
| `/static/shared/*` | 页面脚本、样式表、附件图标 | 离线可用，不依赖 CDN |

`/static/notice` 与 `/ssr/notice` 使用同一个通知对象。页面刻意贴近真实高校门户，包含以下**容易误选**的结构；它们在所有场景下都保持不变：

- 除 `#current-fee`（现行标准，唯一应监控的金额）外，还有 `#previous-fee`（调整前标准）、`.unit-fee strong`（首小时后每 30 分钟加收，约为现行标准的 1/4）、`.cap-fee strong`（单日封顶，约为 1/10）、`.previous-fee-note`（原标准与差额说明段）。这些节点都能被选择器选中并返回数值，选错不会报错，只会静默取到错误金额。
- **同一发布时刻被渲染多次**：`#date-badge`（`10月20日`）、`#published-date-cn`（`2026年10月20日`）、`#published-at`（`2026-10-20 14:32`），页面还含同值的 `#published-timestamp`。这些节点全部由 `published_at` 派生，永远不会互相矛盾，但都**不是**执行日期。真正的执行日期是 `#effective-date`（`2026-11-01`）。
- **点击次数由脚本异步填充**：静态 HTML 里 `#view-count` 是空节点，`notice.js` 请求 `/api/views` 后才写入并设置 `data-loaded="true"`，对齐真实门户的 `_showDynClicks`。用 HTTP 抓取拿到的是空字符串。
- **上一篇/下一篇标题**（`#prev-notice`、`#next-notice`）是页面导航，包含另一条通知的标题；整页文本比对会把它们当成本页内容。
- **撤回不是 404**：`status="withdrawn"` 时页面顶部出现 `#withdrawn-banner`，状态行 `data-status="withdrawn"`；正文与标准照常渲染。
- 正文是 `#notice-body` 下逐段 `<p>`；附件条目携带 `data-kind` 与文件大小；状态行是 `.status-line[data-status]`。

所有业务数据响应携带 `X-Mocksite-Revision` 与 `Cache-Control: no-store`。

### 3.2 默认数据

```json
{
  "notice": {
    "id": "notice-54493",
    "title": "关于调整校园停车收费标准的通知",
    "department": "后勤保障部",
    "doc_no": "校后保〔2026〕42 号",
    "category": "学校通知",
    "current_fee": "128.50",
    "previous_fee": "199.00",
    "currency": "CNY",
    "published_at": "2026-10-20 14:32",
    "effective_date": "2026-11-01",
    "view_count": 128,
    "status": "published",
    "body": [
      "为缓解校园停车压力、规范停车秩序，经2026年第12次校长办公会研究通过，决定调整校园停车收费标准。现将有关事项通知如下。",
      "一、调整范围。本次调整适用于长安、雁塔两校区的道路泊位与校内公共停车场，教工住宅区自有车位不在此次调整范围内。",
      "二、收费标准。小型车首小时由 199.00 元调整为 128.50 元，首小时后每30分钟加收 32.12 元；单日累计不超过 12.85 元。中型车、大型车按车型系数另行计收。",
      "三、执行时间。本通知自 2026 年 11 月 1 日起执行，执行前按原标准计收。",
      "四、其他事项。军车、警车、消防车、救护车等特种车辆按规定免费停放；新能源汽车继续执行半价优惠。",
      "请各单位做好宣传解释工作。如有疑问，请联系后勤保障部交通管理科，电话：029-81891818。"
    ],
    "attachments": [
      {"id": "att-1", "name": "校园停车收费标准调整表.pdf", "src": "/static/shared/img/attachment-pdf.svg", "kind": "pdf", "size_text": "184 KB"},
      {"id": "att-2", "name": "2026年第12次校长办公会纪要.pdf", "src": "/static/shared/img/attachment-pdf.svg", "kind": "pdf", "size_text": "312 KB"},
      {"id": "att-3", "name": "停车收费标准公示回执.doc", "src": "/static/shared/img/attachment-doc.svg", "kind": "doc", "size_text": "96 KB"},
      {"id": "att-4", "name": "意见征集汇总表.xls", "src": "/static/shared/img/attachment-xls.svg", "kind": "xls", "size_text": "72 KB"}
    ],
    "prev_title": "关于CURA中国大学生路跑联赛期间临时交通管制的通知",
    "next_title": "关于举办第二届“百班千人国防尖兵挑战赛”的通知"
  }
}
```

数据约束：

- 金额以**十进制字符串**传输与渲染，后端使用 `Decimal`；非负、有限、最多 64 字符，不接受浮点、指数或负号。
- 通知 ID、标题、发布单位、文号、分类、附件名等文本为非空字符串，最多 256 字符；正文每段最多 2000 字符，最多 40 段；附件最多 20 个。
- `published_at` 是**唯一的发布时刻**，格式 `YYYY-MM-DD HH:MM`（门户风格，不是 RFC 3339）；页面上的中文日期、徽章和时间戳全部由它派生。
- `effective_date` 是 `YYYY-MM-DD`，只有它决定新标准何时执行。
- 通知状态为 `published | withdrawn`；币种为三个大写 ASCII 字母。
- `view_count` 是 0–10000000 的整数，只由页面脚本异步呈现。
- 所有插入 HTML 的文本必须转义；模板不得把数据解释为 HTML。

### 3.3 选择器约定

页面结构在所有场景下保持稳定，因此选择器始终可用。下表由 `src/mocksite/site/pages.py` 单一来源维护，并通过 `GET /_admin/meta` 提供给后台。

| 目标 | 角色 | CSS | XPath |
|---|---|---|---|
| 现行标准 | 主要 | `#notice #current-fee` | `//*[@id="notice"]//*[@id="current-fee"]` |
| 执行日期 | 主要 | `#notice #effective-date` | `//*[@id="notice"]//*[@id="effective-date"]` |
| 正文段落 | 主要 | `#notice-body p` | `//*[@id="notice-body"]/p` |
| 通知标题 | 辅助 | `#notice #notice-title` | `//*[@id="notice"]//*[@id="notice-title"]` |
| 文号 | 辅助 | `#notice-doc-no` | `//*[@id="notice-doc-no"]` |
| 发布单位 | 辅助 | `#notice-department` | `//*[@id="notice-department"]` |
| 通知状态 | 辅助 | `#notice-status` | `//*[@id="notice-status"]` |
| 附件条目 | 辅助 | `#attachments .attachment-item` | `//*[@id="attachments"]//li[contains(@class,"attachment-item")]` |
| 点击次数就绪标记 | 就绪 | `#view-count[data-loaded="true"]` | `//*[@id="view-count" and @data-loaded="true"]` |
| 原标准（划线价） | 诱饵 | `#notice #previous-fee` | `//*[@id="notice"]//*[@id="previous-fee"]` |
| 折算单位费 | 诱饵 | `.unit-fee strong` | `//*[contains(@class,"unit-fee")]//strong` |
| 单日封顶 | 诱饵 | `.cap-fee strong` | `//*[contains(@class,"cap-fee")]//strong` |
| 原标准说明段 | 诱饵 | `.previous-fee-note` | `//*[contains(@class,"previous-fee-note")]` |
| 日期徽章（发布时间） | 诱饵 | `#date-badge` | `//*[@id="date-badge"]` |
| 中文发布日期 | 诱饵 | `#published-date-cn` | `//*[@id="published-date-cn"]` |
| 发布时间戳 | 诱饵 | `#published-at` | `//*[@id="published-at"]` |
| 上一篇标题 | 诱饵 | `#prev-notice` | `//*[@id="prev-notice"]` |

「角色」的含义：**主要**是通常应当监控的节点；**就绪**是等待渲染完成的判据；**辅助**是可选监控的补充字段；**诱饵**形状相似但语义不同，误选会得到错误数据。

选择器、示例 HTML 和实际页面需要一起验收，避免文档中的 XPath 与真实 DOM 层级不符。页面资产随站点分发，不依赖 CDN；离线要求指镜像准备完成后的运行阶段。

## 4. 状态与场景

### 4.1 状态规则

单实例使用进程内状态，包含业务数据和只读 `revision`。采用单进程服务；重启后恢复默认数据，版本重新计数。状态只有两个顶层键：`business`、`revision`；`PATCH` 只接受 `business`。

每次成功写入都在同一把锁内完成“校验 → 渲染静态页 → 提交 → 版本递增”；请求读取一致的状态快照。非法输入不修改状态，也不推进版本。静态页面缓存随状态一起提交，不存在“状态已更新、静态页面仍旧”的窗口。

管理 API 返回的版本用于串行验证和结果关联，不承担多客户端并发编辑控制。多请求的浏览器采集期间应保持状态不变；若发现页面数据版本不一致，验证脚本应重新建立该次验证条件。

### 4.2 场景语义

每个预设场景都从默认状态构造完整目标状态，再一次性提交。重复应用同一场景得到相同业务内容，只有 `revision` 递增；场景之间不隐式叠加。组合条件通过状态 PATCH 显式设置。

| 场景名 | 分组 | 受控变化 | 核对重点 |
|---|---|---|---|
| `baseline` | 基线 | 恢复默认数据 | 基线输入明确 |
| `no_change` | 基线 | 保持默认业务数据，仅版本变化 | 版本元数据不应被误选为业务字段 |
| `fee_change` | 收费 | 现行标准 `128.50` → `96.00` | 两个通知页均变化；正文、日期、原标准不变 |
| `fee_increase` | 收费 | 现行标准 `128.50` → `158.00` | 上调方向的变更同样被识别 |
| `notice_withdrawn` | 内容 | 状态 `published` → `withdrawn` | 撤回横幅出现，标准与正文不变（不是 404） |
| `effective_date_shift` | 内容 | 执行日期 `2026-11-01` → `2026-12-01` | 只有执行日期变化；发布时间渲染不变 |
| `title_change` | 内容 | 标题追加“补充”字样 | 标题提取而非整页文本比对 |
| `view_count_grow` | 内容 | 点击次数 `128` → `1531` | 脚本异步计数不应被当成内容变化 |

每个场景在服务端还带 `title`（中文标题）、`outcome`（采集方会看到什么）、`data_impact`（哪个数据字段变化）、`group`（分组）与 `compare_with_baseline`，通过 `GET /_admin/scenarios` 返回。后台直接渲染这些字段，不维护第二份文案。

**范围界定：本项目的场景只切换页面数据，不改变页面结构。** 所有场景下 DOM 骨架完全相同——`#current-fee`、`#previous-fee`、`#effective-date`、`#notice-body`、`#attachments` 等节点始终存在，只有文本与数值变化。不存在“节点缺失”“ID 改名”“单元格 class 改名”这类结构性场景，也没有 `presentation` 层；`PATCH /_admin/state` 只接受 `business`。

提取器的健壮性（选择器写错、节点消失、页面改版）由使用方自己的测试覆盖，不属于本项目的输入契约。

场景不会自动回滚。验证脚本改过数据后，再调用 `baseline` 或 reset 恢复，消除“还没采集就回滚了”的时序不确定性。

**故障注入不在范围内。** 早期版本提供过 500/延迟注入（`outage`、`slow_site`），现已删除：采集方如何处理超时、重试与 5xx 是它自己的契约，不属于“输入”；把它混进 mocksite 会让“内容变了”和“网络挂了”两类信号无法区分。验证失败路径请使用采集方自带的 fixture 或网关层。`PATCH` 收到 `faults` 会返回 400，旧客户端会立刻失败而不是静默忽略。

### 4.3 未实现扩展（P4，不阻塞当前使用）

以下能力尚未实现，文档不把它们描述为可用：

- **瞬时失败序列**：`/flaky` 使用固定序列，例如 `500, 500, 200`；按端点请求计数推进，序列耗尽后持续返回 200，reset 清零。不使用随机失败率。
- **单请求延迟**：`/slow?ms=3000` 仅影响当前请求；只接受 0–30000 的整数，非法输入返回 400。
- **安全探针**：`/redirect-private?target=loopback|metadata|ipv6` 只接受固定枚举；`/private-resource` 在页面内请求固定私网子资源。验证必须走监控平台的真实采集出口。

## 5. 管理后台与 API 契约

### 5.1 管理后台

后台入口为管理端口的 `/`，与管理 API 同源部署。开发者不需要编写 curl 请求，就能完成“查看状态 → 修改数据或切换场景 → 打开目标页面 → 恢复默认”的完整流程。

后台是**单页控制台**：左侧场景与数据编辑，右侧常驻目标页实时预览，顶部一行是刷新、恢复默认与退出。

```
┌─ 场景（基线 / 收费标准 / 通知内容）─┬─ 实时预览 ─┐
├─ 手动编辑通知字段 ─────────────────┤  revision  │
└───────────────────────────────────┴─ 事实摘要 ─┘
```

| 区域 | 内容 | 操作结果 |
|---|---|---|
| 连接与认证 | 输入管理 token、连接状态、退出 | 认证成功后读取状态；认证失败显示可读错误，不展示受保护数据 |
| 场景 | 按“基线 / 收费标准 / 通知内容”分组的场景卡片 | 应用前二次确认；每张卡片显示中文标题、采集方会看到什么、哪个数据字段变化；成功后显示 `revision N → N+1` |
| 手动编辑 | 通知全部业务字段（含正文，每行一段） | 保存后当前状态不再对应任何预设场景；字段错误就地标红并保留草稿 |
| 实时预览 | 目标页 iframe，标签切换 `/static/notice`、`/ssr/notice` | 任何变更后自动重载；以 1180 px 桌面宽度渲染再缩放，保证金额区与侧栏并排可见 |
| 事实摘要 | 当前 revision、生效场景、现行标准、点击次数 | 只读展示；手动编辑后标记“手动编辑的状态” |
| 操作反馈 | 提交中、成功、字段错误、认证失效、网络失败 | 请求期间禁用重复提交；失败时保留编辑内容，不伪报保存成功 |

预览以桌面宽度渲染的原因：通知页在 900 px 断点会改为单列，若直接按预览面板宽度渲染，金额区会被挤到侧栏下方，恰好看不到要验证的内容。预览 iframe 带 `sandbox="allow-scripts allow-same-origin"`：脚本必须允许（点击次数由页面脚本填充），但目标页不应能操作后台。

后台复用下述 API，不维护独立业务状态或另一套场景实现。未保存的表单内容与已生效状态明确区分；服务端校验是最终依据。管理请求结果未知时先刷新状态核对，不自动重放写入。

token 由使用者输入，只保存在当前页面内存中；刷新或退出后清除，不写入 URL、`localStorage`、`sessionStorage` 或日志，也不内置进前端资产。未认证时只提供连接界面，状态与写操作仍由 API 认证保护。后台及其资产离线可用。

### 5.2 管理 API

页面服务与管理服务使用两个独立监听端口。页面端口不提供管理后台或挂载 `/_admin/*` 路由；所有管理 API 都需要 Bearer token。

| 方法 | 路径 | 目标行为 |
|---|---|---|
| `GET` | `/_admin/state` | 返回 `{revision, business}` |
| `PATCH` | `/_admin/state` | 部分修改 `business`，成功后返回完整状态 |
| `POST` | `/_admin/reset` | 恢复默认数据，推进版本，返回 `{before, after}` |
| `GET` | `/_admin/scenarios` | 列出已实现的场景、影响范围与预期页面变化 |
| `POST` | `/_admin/scenario/{name}` | 原子应用场景，返回 `{before, after}`（含版本） |
| `GET` | `/_admin/meta` | 页面目录、采集/预览地址、选择器角色与 CSS/XPath |

PATCH 中对象字段递归合并，数组整体替换；`null` 不表示删除且不允许作为字段值；`revision` 只读，未知键、类型错误、越界值均返回 400，状态保持不变。未知场景返回 404。没有语义重复的整状态 PUT 接口。

管理服务的实现要求：

- 使用 `MOCKSITE_TOKEN`；未配置或不足 32 个非空白字符时拒绝启动。部署者使用安全随机值，不将其写进仓库。
- 缺失或错误凭据返回 401，不返回状态内容；管理 API 不启用跨域访问。
- 管理写入只接受 `application/json`（`POST /_admin/reset` 允许无 body；若带 body 仍必须是 JSON），请求体最多 64 KiB；不支持的媒体类型返回 415，超限返回 413，JSON 或字段校验失败返回 400。
- 日志不输出 Authorization、请求体和完整 query；只记录方法、路由模板、状态码及版本等诊断信息。
- 状态、业务数据与页面响应使用 `Cache-Control: no-store`，避免客户端缓存干扰验证。
- 管理后台构建产物缺失时，`/` 返回 503 `admin_build_missing`，不伪造成功。

## 6. 实现与部署方案

### 6.1 技术选择

采用 Python 3.12 + FastAPI：用 schema 校验控制输入，异步处理请求，状态管理与页面渲染分别组织。一个进程持有状态并运行两个监听端口，不启用多个独立 worker，以免产生多份状态。

服务端 Jinja2 模板生成静态及 SSR HTML；页面脚本与样式表作为本地资产随包分发。管理后台使用本地 React 资产构建单页控制台，通过同源 API 读写状态，不引入独立前端服务。容器以非 root 用户运行，支持只读根文件系统，不需要数据库或外部存储。

前端统一使用 **pnpm** 管理依赖和执行构建。`web/` 共用一个 `package.json` 和一个 `pnpm-lock.yaml`，只覆盖管理后台；不使用 `package-lock.json` 或 Yarn 锁文件。

**前端代码全部在 `web/` 下，`src/` 只放 Python 后端。** 具体分工：

| 位置 | 内容 | 是否参与构建 |
|---|---|---|
| `web/admin/` | 管理后台源码（React + Vite） | 是，产物到 `web/dist` |
| `web/targets/shared/` | 框架无关的目标页脚本与样式（`notice.js`、`notice.css`、`img/attachment-*.svg`） | 否，原样分发 |
| `web/targets/manifest.json` | 本地资产清单；React/Vue 运行时删除后 `assets` 为空。不挂载、不打包，仅作仓库内清单 | 否 |

`web/targets/` 不经过 Vite：`shared/` 由站点进程挂载在 `/static/shared`。构建 wheel 时通过 hatchling 的 `force-include` 把该子树复制进包的 `mocksite/_static/`，因此生产镜像不依赖仓库里的 `web/` 目录。运行时解析顺序为：`MOCKSITE_TARGET_ASSETS` 显式配置 → 包内 `_static` → 仓库 `web/targets`（仅便于可编辑安装）。依赖安装和前端构建均在 Docker 内执行，部署构建使用冻结锁文件安装。

Python 依赖同样在 Docker 内安装。宿主侧可选使用工作区共用的 conda 环境（`../.github/env/environment.yml`，环境名 `webmonitor`，Python 3.12），用于编辑、lint 与快速跑测试；`pyproject.toml` 的 pin 需与 `../.github/env/requirements-workspace.txt` 保持一致，容器构建仍以 `pyproject.toml` 为准。

### 6.2 构建与镜像来源

**mocksite 没有 GHCR 镜像，也不使用镜像 overlay。** 所有运行方式都从本仓库源码构建：

- `compose.yaml` 的 `site` 服务使用 `build: .` + `deploy/Dockerfile`，本地镜像名为 `mocksite:local`；
- `compose.yaml` 的 `dev` 服务使用 `deploy/dev.Dockerfile`，本地镜像名为 `mocksite-dev:local`；
- 生产镜像两阶段构建：Node 阶段冻结安装并用 Vite 构建后台，Python 阶段用 hash 锁安装依赖、安装 wheel（包含 `web/targets/shared` 的包内副本），以 UID `10001` 运行。

不要从注册表拉取 mocksite 镜像，也不要引用不存在的 tag；部署示例中的 `docker compose up --build` 是唯一受支持的方式。

### 6.3 网络边界

| 端口 | 用途 | 默认暴露方式 |
|---|---|---|
| `9000` | 目标页面、业务数据及健康检查 | 容器内监听；基础 Compose 映射到宿主 `127.0.0.1:9000` |
| `9001` | 管理后台及管理 API | 容器内监听；基础 Compose **不发布**，仅控制网络可达；本地开发 overlay 映射 `127.0.0.1:9001` |

容器内的 `127.0.0.1` 不是宿主机回环地址。本地开发启动方式必须通过开发 overlay 配置 `127.0.0.1:9001:9001`，提供可从浏览器打开的管理后台；基础 Compose 仍不发布管理端口。

端口分离不等于网络隔离。部署时需限制控制网络的参与者，并确保采集出口不能访问管理端口；token 仅用于管理后台和控制脚本，不提供给被采集页面或模型上下文。

### 6.4 接入采集方与 Agent 网络

mocksite 只负责在 `9000`（页面）与 `9001`（管理）上提供内容与状态控制，不关心采集方如何出网。采集方需要知道三件事：

- **采集地址**：容器网络内的服务名，Compose 下为 `http://site:9000`（注意是服务名，不是项目名），由 `MOCKSITE_COLLECT_ORIGIN` 决定后台展示值；
- **预览地址**：开发者浏览器可打开的地址，由 `MOCKSITE_PUBLIC_ORIGIN` 决定，默认 `http://127.0.0.1:9000`；
- **管理端口**：`9001` 不得暴露给被采集页面或采集出口，token 只交给后台与控制脚本。

**WebMonitor-Agent 联调**由 Agent 部署方自行配置，本仓库不提供 Agent 专用 overlay，也不维护 Agent 侧的网络或出口变量文件。做法是：把 Agent 的 `egress` 接入与 mocksite 共享的 Docker 网络（mocksite 的 Compose 项目网络，默认 `mocksite_default`），在 Agent 的出口代理中只放行 `http://site:9000`，并把 Agent 的 target allowlist 限定为 `http://site:9000`。Agent 的采集目标是 `http://site:9000/static/notice`，管理状态仍在宿主 `127.0.0.1:9001`；`9001` 不在放行范围。

Agent 的网络名、出口白名单和 target allowlist 都是 Agent 部署配置，不属于 mocksite 仓库；改网络名或换端口时，两侧要同步修改，不要假设默认值永远成立。若采集方自带出口代理或私网限制，放行 mocksite 的精确主机与端口属于该采集方自己的配置。

## 7. 运行方式

### 7.1 启动站点（源码构建）

```sh
cd mocksite
cp .env.example .env          # 填入 MOCKSITE_TOKEN（openssl rand -hex 32）
docker compose up --build -d --wait
curl --fail http://127.0.0.1:9000/health     # {"status":"ok"}
```

基础 Compose 只发布 `127.0.0.1:9000`（页面）。管理端口 `9001` 仅在控制网络内可达。

需要在本机浏览器打开管理后台时，叠加开发 overlay：

```sh
docker compose -f compose.yaml -f compose.dev.yaml up --build -d --wait
open http://127.0.0.1:9001        # 输入 .env 里的 MOCKSITE_TOKEN
```

overlay 只额外映射 `127.0.0.1:9001`，不改变镜像或状态。

### 7.2 管理操作

后台与脚本走同一套 API，二选一即可：

```sh
export MOCKSITE_TOKEN=$(grep ^MOCKSITE_TOKEN .env | cut -d= -f2)

python scripts/control.py state                      # 当前状态（含 revision）
python scripts/control.py scenarios                  # 场景清单
python scripts/control.py scenario fee_change        # 应用预设，输出 before/after
python scripts/control.py patch '{"business":{"notice":{"current_fee":"96.00"}}}'
python scripts/control.py pages                      # 页面、采集/预览地址与选择器
python scripts/control.py reset                      # 恢复默认数据
```

退出码：`0` 成功，`1` 请求失败（含 401/404/400），`2` 用法或 JSON 错误。脚本对 loopback 显式绕过 `*_proxy`。

### 7.3 开发与测试命令

开发工具链在 `dev` 服务中（profile `tools`，不随默认 `up` 启动），不发布任何端口：

```sh
docker compose build dev
docker compose run --rm dev python -c "import mocksite"
export MOCKSITE_TOKEN=$(grep ^MOCKSITE_TOKEN .env | cut -d= -f2)
docker compose run --rm -e MOCKSITE_TOKEN dev mocksite --check     # 只校验配置；退出码 2 = 配置错误
docker compose run --rm dev pytest -q

# 前端，在 dev 容器内
docker compose run --rm dev sh -lc 'cd web && pnpm install --frozen-lockfile'
docker compose run --rm dev sh -lc 'cd web && pnpm typecheck'
docker compose run --rm dev sh -lc 'cd web && pnpm build'      # -> web/dist
```

宿主机只跑测试/lint 时用共享 conda 环境（仍需 `env -u all_proxy -u http_proxy -u https_proxy` 绕开代理）：

```sh
env -u no_proxy -u NO_PROXY -u all_proxy -u http_proxy -u https_proxy \
  conda run -n webmonitor pytest -q
```

`pytest` 只收集 `tests/unit` 与 `tests/integration`；浏览器验收在 `tests/acceptance/`，见 7.5。

### 7.4 浏览器验收

两个脚本位于 `tests/acceptance/`（不属于 pytest），都以真实 Chromium 驱动已启动的站点，并先调用 reset 建立已知基线：

```sh
# 先启动带管理端口的栈（见 7.1 的 overlay）
export MOCKSITE_TOKEN=$(grep ^MOCKSITE_TOKEN .env | cut -d= -f2)
conda run -n webmonitor python tests/acceptance/check_admin_ui.py       # 38 项
conda run -n webmonitor python tests/acceptance/check_target_pages.py   # 47 项
```

默认访问 `http://127.0.0.1:9000` 与 `9001`，可用 `--site-origin` / `--admin-origin` / `--token` 覆盖。Playwright 包来自共享 conda 环境；首次运行前如未安装浏览器，执行 `conda run -n webmonitor python -m playwright install chromium`。最近一次完整记录（2026-10-26）为 38/38 与 47/47；本次文档整理未重新运行。

### 7.5 与 WebMonitor-Agent 的联调验收

本节是开发/验收路径；普通用户安装 Agent 不需要 clone 产品仓库，而是用 `curl` 下载发布页的部署文件并自行创建 `.env`。Agent 的默认启动统一为 `docker compose up -d --wait`，基础文件拉取公开 GHCR 镜像；源码构建用 `compose.build.yaml` 覆盖。

使用公开镜像时，Agent 的 `.env` 至少包含（显式版本，不依赖隐式默认）：

```dotenv
WEBMONITOR_IMAGE=ghcr.io/webmonitor/webmonitor-agent:1.0.0
# 或 WEBMONITOR_IMAGE=ghcr.io/webmonitor/webmonitor-agent:latest
```

以下命令从工作区根目录执行为开发验收路径。先启动 mocksite，再按 Agent 自己的默认方式启动（或源码构建）：

```sh
# 1) mocksite: site:9000 + admin:9001（本仓库源码构建）
cd mocksite
cp .env.example .env
# 在 .env 写入 MOCKSITE_TOKEN（至少 32 个非空白字符）
docker compose -f compose.yaml -f compose.dev.yaml up --build -d --wait
cd ..

# 2a) Agent 默认启动（公开镜像）
cd WebMonitor-Agent
cp .env.example .env
# 设置 POSTGRES_PASSWORD、SECRET_KEY、ADMIN_EMAIL/ADMIN_PASSWORD 与 WEBMONITOR_IMAGE
docker compose up -d --wait

# 3) 网络/出口由部署方自行配置：接入 mocksite 网络，并且只放行 site:9000
```

Agent 源码构建使用 `compose.build.yaml` 覆盖：

```sh
cd WebMonitor-Agent
docker compose -f compose.yaml -f compose.build.yaml up --build -d --wait
```

网络与出口不通过本仓库的文件接入：Agent 部署方自行把 `egress` 接到 mocksite 的 Compose 网络，并在出口代理与 target allowlist 中只放行 `site:9000`。本仓库不提供 Agent 专用 overlay、专用 Squid 配置或相应的网络变量。

无论默认镜像还是源码构建，`s3`/`egress` 辅助镜像都在本机构建。上面的 `cp .env.example .env` 是开发验收路径；普通用户按 Agent 发布页的部署说明自行创建 `.env`，不需要 clone 仓库。

GHCR 包 `ghcr.io/webmonitor/webmonitor-agent:1.0.0` 与 `ghcr.io/webmonitor/webmonitor:1.0.0` 已公开，可匿名拉取，支持 `linux/amd64` 与 `linux/arm64`；`latest` 只随稳定发布移动。旧的 `agent-api` / `agent-web` 包已删除，不要引用。

验收入口：

- Agent UI：`http://localhost:8080`
- 采集目标：`http://site:9000/static/notice`（Agent target allowlist 内的唯一目标）
- 管理状态：`http://127.0.0.1:9001/_admin/state`（mocksite 的 token，不给 Agent）

预期顺序：Agent 首次采集只建立基线、不发事件；在 mocksite 应用 `fee_change` 后，下一次采集应产生变化事件；`baseline`/reset 后回到基线。Agent 的错误码、重试和邮件投递以其自身契约为准。

### 7.6 停止

```sh
docker compose down            # 保留镜像
docker compose down --rmi local
```

状态保存在进程内存中，容器重启即恢复默认数据，`revision` 重新计数。

### 7.7 已验证的边界

以下为历史实测（2026-10-25/26，见 [变更记录](changelog/README.md)），本次文档整理未重跑：

- 镜像以 UID `10001` 运行，根文件系统只读（`read_only: true`），仅 `/tmp` 可写；实测 `/app`、`/etc` 写入被拒绝。
- 基础 Compose 下宿主机直连 `9001` 被拒绝；overlay 下才可访问。
- 容器内 `http://site:9000` 与 `http://site:9001` 均可访问（`site` 是 Compose 服务名；`mocksite` 只是项目名，不解析）。
- 已删除的列表路由 `/react/list`、`/vue/list`、`/dynamic/archive`、`/api/data` 与对应资产返回 404。

## 8. 交付顺序与验收

按依赖顺序推进；**当前首轮范围为 P1、P3（P2 已随列表页作废）**。每个阶段的验收应保留实际输出，不能只证明页面返回了 HTTP 200。

| 阶段 | 交付内容 | 完成标准 |
|---|---|---|
| P1：管理后台与通知页面 | 状态校验、管理认证、版本、reset、static/SSR、数据场景；后台认证、场景、通知编辑、实时预览与操作反馈 | 在后台完成“默认标准 → 修改 → 恢复”；非法写入不改变状态；API 返回状态与后台显示一致 |
| P2：浏览器与列表（已作废） | 列表页、分页、React/Vue 运行时 | 2026-10-26 随单条通知收敛删除；保留历史记录 |
| P3：容器与运行 | Dockerfile、基础 Compose、本地开发 overlay、控制脚本、Agent 接入说明、运行文档 | 一条命令从源码启动并可访问后台；管理端口无公网发布；说明采集方自行配置共享网络与精准出口白名单（Agent 端到端结果由 Agent 仓库记录） |
| P4：后续扩展 | `/flaky`、`/slow`、单页覆盖、安全探针 | 尚未实现；相同序列产生相同响应，受限地址未被访问 |

各阶段都需满足以下通用标准：

- **可复现**：从 reset 开始执行相同操作，得到相同业务内容；版本元数据除外。
- **状态一致**：非法请求不产生部分更新；读响应对应完整快照；重启恢复默认状态。
- **提取可验证**：通知页的正文检查原始 HTML；点击次数必须用浏览器检查脚本填充后的 DOM。
- **后台可用**：通过真实浏览器验证认证、表单保存、场景切换和重置；覆盖错误 token、非法输入、失败反馈与管理功能仍可用。
- **结果归属清楚**：mocksite 证明输入是什么；平台联调证明提取、事件与通知实际发生了什么。
- **实现与文档一致**：只有已经通过验收的能力才标记为可用；不发布虚构镜像、无效环境变量或未经验证的能力。

## 9. License

本仓库采用 [CC BY-NC 4.0](LICENSE)（署名—非商业性使用）。第三方前端资产保留各自许可证与声明。
