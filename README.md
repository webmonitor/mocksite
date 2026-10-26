# webmonitor-mocksite

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

一个通用、可控制、可复现的 mock 网站，供任何内容监控/采集系统做开发、回归验证和演示。它不绑定特定平台：页面提供稳定的 CSS 与 XPath 选择器，状态通过 HTTP API 与浏览器后台控制。

开发者先让监控平台采集正常页面、建立基线，再通过管理 API 改变价格、列表、页面结构或响应行为，检查平台实际提取了什么、是否正确识别变化，以及失败后能否恢复。

> **当前状态：阶段 0–5 已完成，站点可一条命令启动。** 商品详情页（static/SSR，真实电商结构含诱饵价格节点与懒加载评价）、React/Vue 列表、动态分页页、JSON 数据、健康检查、管理 API、向导式管理后台（含内嵌实时预览）、生产镜像与 Compose 服务均已落地，可离线运行且不依赖外部 CDN。阶段 6 的扩展故障与安全探针（`/flaky`、`/slow`、单页覆盖、私网探针）尚未实现；已完成范围见 [变更记录](changelog/README.md)。

文档入口：[交付计划与任务进度](plan/README.md) · [变更记录](changelog/README.md)。本 README 定义目标契约，`plan/` 跟踪待实施任务，`changelog/` 记录已经发生的变更。

## 1. 项目目标与边界

mocksite 负责产生受控输入，并给出可核对的页面状态；监控平台负责采集、提取、比较、调度和通知。

| 需要验证的问题 | mocksite 提供的条件 |
|---|---|
| 内容是否真的发生变化 | 固定初始数据与明确的状态切换 |
| HTTP 与浏览器采集有何差异 | 无 JS 页面、React/Vue 客户端渲染页面、动态列表 |
| 空内容、节点缺失和结构变化能否区分 | 独立场景，每次只改变指定条件 |
| 分页是否完整、重复记录如何处理 | 固定顺序、稳定行 ID、可控分页与重复行 |
| 故障期间及恢复后平台如何表现 | 可显式启停的 500、延迟和确定性失败序列 |
| 出口限制是否生效 | 固定的私网重定向和子资源探针 |

任何采集方都可以接入：页面同时提供 CSS 与 XPath 选择器，便于不同技术栈（HTTP 抓取、无头浏览器、Selenium 等）验证各自的提取与等待逻辑。各平台的错误码、重试策略和告警能力由其自身契约决定，mocksite 只负责输入可复现。

本项目不实现监控引擎、邮件发送、多用户与权限管理、任意脚本执行或真实网站的反爬绕过。**首轮交付必须包含可用的管理后台和管理 API**：日常开发与演示通过浏览器操作，自动化验证通过同一套 API 控制。

mocksite 不替代任何采集方自带的 smoke fixture，两者互不依赖：这里的页面与数据契约面向通用验证，使用方按需接入即可。

## 2. 使用流程

一次完整验证按以下顺序执行：

1. 打开管理后台，输入管理 token，重置 mocksite 并查看状态及版本，确认使用默认数据。
2. 在监控平台配置目标 URL 和选择器，完成首次采集并确认基线已建立。
3. 在后台选择并应用一个场景，查看返回的前后状态版本；自动化脚本执行相同管理 API 请求。
4. 触发或等待下一次采集，核对页面内容、提取结果和平台事件。
5. 故障场景结束后显式恢复，再采集一次，确认恢复后的行为。

mocksite 不负责等待平台采集完成。验证脚本必须以平台的运行结果为准，不能仅凭固定休眠时间判定成功。邮件链路只在显式启用邮件验证时检查。

一个实例只服务一组串行场景。需要并行验证时，为每组测试启动独立实例，避免共享状态相互覆盖。

## 3. 页面与数据契约

### 3.1 页面形态

| 目标路径 | 内容与渲染方式 | 主要验证点 |
|---|---|---|
| `/static/product` | 真实电商详情页：状态提交时生成完整 HTML，请求时直接返回；评价区由 JS 分页渲染 | 多重价格节点中挑对目标、HTTP 提取基线 |
| `/ssr/product` | 同一份详情页，每次请求根据当前状态生成完整 HTML | 服务端渲染内容提取 |
| `/react/list` | React 在浏览器中请求数据并渲染列表 | JS 执行、就绪等待、列表提取 |
| `/vue/list` | Vue 在浏览器中请求数据并渲染列表 | 相同数据在另一框架下的采集 |
| `/dynamic/deals` | 浏览器加载首屏，点击“加载更多”追加下一页 | 异步加载、分页聚合、结束判断 |
| `/api/data` | 返回当前商品、列表与评价的 JSON 数据 | 前端数据源与人工核对 |
| `/api/reviews?page=N` | 评价分页 JSON（1 起始） | 不经 DOM 分页验证评价 |
| `/health` | 返回 `{"status":"ok"}` | 进程存活，不受场景故障影响 |

`/static/product` 与 `/ssr/product` 使用同一个商品对象；三种列表页面使用同一组列表数据。商品价格和列表行价格是不同字段，不要求五种页面提取出相同价格。

商品详情页刻意贴近真实电商站点，包含以下**容易误选**的结构（这些结构在所有场景下都保持不变）：

- 除 `#current-price` 外还有 `#original-price`（划线价）、`.installment-price strong`（分期，约现价 1/4）、`.unit-price strong`（每 100 g，约现价 1/10）、`.msrp-price`（标价段）。这些节点都能被选择器选中并返回数值，选错不会报错，只会静默取到错误金额。
- 评分同时以星级字符与 `#rating-value` 数字节点呈现；从星级反推会得到错误结果。
- 图库、规格、变体、推荐位是页面装饰，不是监控目标。
- 评价区由浏览器端分页加载：静态 HTML 只有骨架屏，`#reviews[data-ready="true"]` 在第一页评价真正渲染后才出现。

所有业务数据响应携带 `X-Mocksite-Revision`，标识此次读取的状态版本。CSR 的 HTML 外壳不代表列表已就绪：数据加载成功后才设置 `data-ready="true"`，并在渲染根节点记录实际数据版本 `data-revision`。加载失败时显示错误状态，不设置就绪标记。

`/api/data` 是目标站的数据源，不代表监控平台已经支持直接监控 JSON。直接采集 JSON 的能力需单独确认。

### 3.2 默认数据

```json
{
  "product": {
    "id": "coffee",
    "name": "Fixture Coffee Roaster — Ethiopia Guji 1kg",
    "brand": "Fixture Roasters",
    "sku": "FX-COF-GUJI-1KG",
    "current_price": "128.50",
    "original_price": "199.00",
    "currency": "USD",
    "rating": "4.6",
    "review_count": 128,
    "stock_status": "in_stock",
    "stock_count": 42,
    "description": "A washed Ethiopian single origin …",
    "highlights": ["Single origin, washed process, Guji zone", "…"],
    "images": [{"id": "img-1", "alt": "…", "src": "/static/shared/img/coffee-natural.svg", "color": "natural"}],
    "variants": [{"id": "size-1kg", "label": "1 kg", "kind": "size", "available": true}],
    "specs": [{"label": "Origin", "value": "Ethiopia, Guji zone"}]
  },
  "items": [
    {"id": "A", "name": "Alpha", "price": "10.00"},
    {"id": "B", "name": "Beta", "price": "20.00"},
    {"id": "C", "name": "Gamma", "price": "30.00"}
  ],
  "page_size": 2,
  "reviews": [
    {"id": "rev-1", "author": "Dana R.", "rating": 5, "date": "2026-09-14", "title": "…", "body": "…", "verified": true}
  ],
  "review_page_size": 2
}
```

数据约束：

- 价格以十进制字符串传输与渲染，后端使用 Decimal；非负、有限，最多 64 字符，不经过浮点转换。
- 商品与列表行的 ID、名称是非空字符串，最多 256 字符；币种为三个大写 ASCII 字母。
- 列表最多 100 行，默认 ID 唯一、顺序固定；重复行只能通过专用故障场景注入。
- `page_size` 是 1–100 的整数；页数由列表长度计算，不维护可与数据冲突的 `total_pages`。`review_page_size` 同理为 1–50，评价页数派生。
- 评分是 0–5 的十进制字符串；星级字符仅为装饰，不作为数据来源。
- 库存状态为 `in_stock | low_stock | out_of_stock | preorder`；`out_of_stock` 时加入购物车按钮禁用，页面其余部分照常渲染。
- 评价最多 50 条，`date` 为 `YYYY-MM-DD`，`rating` 为 1–5 整数。
- 动态页面首次加载第一页；每次点击只追加下一页，加载期间禁用按钮，末页后隐藏按钮。空列表也应进入就绪状态。
- 所有插入 HTML 的文本必须转义；CSR 使用框架的文本渲染能力，不把数据解释为 HTML。

### 3.3 选择器约定

页面结构在所有场景下保持稳定，因此选择器始终可用。

| 目标 | 角色 | CSS | XPath |
|---|---|---|---|
| 商品现价 | 主要 | `#product #current-price` | `//*[@id="product"]//*[@id="current-price"]` |
| 商品名称 | 辅助 | `#product #product-name` | `//*[@id="product"]//*[@id="product-name"]` |
| 商品 SKU | 辅助 | `#product-sku` | `//*[@id="product-sku"]` |
| 库存状态 | 辅助 | `#stock-status` | `//*[@id="stock-status"]` |
| 评分（数字） | 辅助 | `#product #rating-value` | `//*[@id="product"]//*[@id="rating-value"]` |
| 评价总数 | 辅助 | `#review-count` | `//*[@id="review-count"]` |
| 规格表行 | 辅助 | `#specs .spec-table tbody tr` | `//*[@id="specs"]//tbody/tr` |
| 评价区就绪标记 | 就绪 | `#reviews[data-ready="true"]` | `//*[@id="reviews" and @data-ready="true"]` |
| 评价条目 | 主要 | `#reviews-list li.review-item` | `//*[@id="reviews-list"]/li[contains(concat(" ", normalize-space(@class), " "), " review-item ")]` |
| 原价（划线价） | 诱饵 | `#product #original-price` | `//*[@id="product"]//*[@id="original-price"]` |
| 分期价 | 诱饵 | `.installment-price strong` | `//*[contains(@class,"installment-price")]//strong` |
| 单位价 | 诱饵 | `.unit-price strong` | `//*[contains(@class,"unit-price")]//strong` |
| 标价段 | 诱饵 | `.msrp-price` | `//*[contains(@class,"msrp-price")]` |
| 列表就绪标记 | 就绪 | `#app[data-ready="true"]` | `//*[@id="app" and @data-ready="true"]` |
| 列表行 | 主要 | `#inventory tbody tr.item` | `//*[@id="inventory"]/tbody/tr[contains(concat(' ', normalize-space(@class), ' '), ' item ')]` |
| 行内价格（相对当前行） | 主要 | `td.price` | `.//td[contains(concat(' ', normalize-space(@class), ' '), ' price ')]` |
| 下一页按钮 | 辅助 | `#load-more` | `//*[@id="load-more"]` |

「角色」的含义：**主要**是通常应当监控的节点；**就绪**是等待渲染完成的判据；**辅助**是可选监控的补充字段；**诱饵**形状相似但语义不同，误选会得到错误数据。该分类由 `site/pages.py` 单一来源维护，并通过 `GET /_admin/meta` 提供给后台。

列表行使用 `data-id` 保存稳定业务 ID。选择器、示例 HTML 和实际页面需要一起验收，避免文档中的 XPath 与真实 DOM 层级不符。

React/Vue 及其他运行时资产随站点分发，不依赖 CDN。依赖版本、来源、完整性校验和许可证信息应随资产记录；离线要求指镜像准备完成后的运行阶段。

## 4. 状态与场景

### 4.1 状态规则

单实例使用进程内状态，包含业务数据、故障控制项和只读 `revision`。采用单进程服务；重启后恢复默认数据，版本重新计数。状态只有三个顶层键：`business`、`faults`、`revision`；`PATCH` 只接受前两个。

每次成功写入都在锁内完成校验、状态提交及版本递增；请求读取一致的状态快照。非法输入不修改状态，也不推进版本。静态页面缓存随状态一起提交，不能出现“状态已更新、静态页面仍旧”的窗口。

管理 API 返回的版本用于串行验证和结果关联，不承担多客户端并发编辑控制。多请求的浏览器采集期间应保持状态不变；若发现页面数据版本不一致，验证脚本应重新建立该次验证条件。

### 4.2 场景语义

每个预设场景都从默认状态构造完整目标状态，再一次性提交。重复应用同一场景得到相同内容，只有版本递增；场景之间不隐式叠加。组合条件通过状态 PATCH 显式设置。

| 场景名 | 分组 | 受控变化 | 核对重点 |
|---|---|---|---|
| `baseline` | 基线 | 恢复默认数据和正常响应 | 基线输入明确，故障已清除 |
| `no_change` | 基线 | 保持默认业务数据，仅版本变化 | 在默认基线下，业务字段不变；版本元数据不应被误选为业务字段 |
| `price_change` | 价格 | 商品现价 `128.50` → `96.00` | 两个商品页均变化；列表不变 |
| `price_increase` | 价格 | 商品现价 `128.50` → `158.00` | 涨价方向的变更同样被识别 |
| `item_price_change` | 价格 | A 行价格 `10.00` → `12.50` | React、Vue、动态列表的同一行均变化；商品现价不变 |
| `stock_out` | 内容 | 库存状态 `in_stock` → `out_of_stock`，数量归零 | 库存字段变化，价格不变；购物车按钮禁用 |
| `rating_change` | 内容 | 评分 `4.6` → `3.2`，评价数 `128` → `131` | 评分与评价数同时变化 |
| `reviews_empty` | 内容 | 评价列表变为空 | 评价区正常加载但 0 条，商品数据不变 |
| `reviews_grow` | 内容 | 评价从 5 条增至 7 条 | 分页从 3 页变成 4 页 |
| `empty_list` | 列表 | 列表数据变为 `[]` | 列表成功加载但无记录，与加载失败不同 |
| `duplicate_rows` | 列表 | 在输出列表末尾追加一条 A 行副本 | 重复业务 ID 的检测与覆盖校验 |
| `pagination_grow` | 列表 | 在默认列表后追加 D、E 行，页大小仍为 2 | 动态列表从两页增至三页，原有行保持稳定 |
| `outage` | 故障 | 目标页面及 `/api/data` 返回 500 | 采集失败如何记录；管理 API 仍可用于恢复 |
| `slow_site` | 故障 | 目标页面及 `/api/data` 延迟 8000ms | 配置的采集超时小于延迟时，实际超时行为 |

每个场景在服务端还带 `title`（中文标题）、`outcome`（采集方会看到什么）、`data_impact`（哪个数据字段变化）、`group`（分组）与 `compare_with_baseline`，通过 `GET /_admin/scenarios` 返回。后台直接渲染这些字段，不维护第二份文案。

**范围界定：本项目的场景只切换页面数据，不改变页面结构。** 所有场景下每个页面的 DOM 骨架完全相同——`#current-price`、`#original-price`、`#rating-value`、`#gallery-image`、`#reviews` 等节点始终存在，只有文本与数值变化。不存在「节点缺失」「ID 改名」「单元格 class 改名」这类结构性破坏场景：验证目标是「数据变了平台是否识别」，而不是「DOM 被改写后提取器如何反应」。因此状态中也没有呈现控制项（`presentation`）这一层，`PATCH /_admin/state` 只接受 `business` 与 `faults`。

提取器的健壮性（选择器写错、节点消失、页面改版）由使用方自己的测试覆盖，不属于本项目的输入契约。

故障不会在后台定时恢复。验证脚本观察到失败后，再调用 `baseline` 或 reset 恢复，消除“还没采集就恢复了”的时序不确定性。故障发生与恢复是否发送告警，由平台配置与现有能力决定。

### 4.3 后续扩展

以下能力在基础场景通过验收后增加，不阻塞首轮交付：

- **瞬时失败序列**：`/flaky` 使用固定序列，例如 `500, 500, 200`；按该端点的请求计数推进，序列耗尽后持续返回 200，reset 清零。不使用随机失败率；重试请求同样消耗序列元素。
- **单请求延迟**：`/slow?ms=3000` 仅影响当前请求；只接受 0–30000 的整数，非法输入返回 400。此端点独立于全局延迟，避免延迟叠加。
- **单页面覆盖**：按固定路由设置数据覆盖，用于 React 页面变化、Vue 页面不变等场景。覆盖必须显式展示在状态中，reset 清除；未实现前所有页面遵循共享数据规则。
- **安全探针**：`/redirect-private?target=loopback|metadata|ipv6` 只接受固定枚举，不允许任意目标 URL；`/private-resource` 在页面内请求固定私网子资源。验证必须走监控平台的真实采集出口。

安全探针的验收目标是受限请求没有触达目标地址。子资源被阻止后，主页面仍可能提取成功；应结合出口拒绝记录或隔离探针的请求计数验证，不能仅以整次采集失败作为证据。

## 5. 管理后台与 API 契约

### 5.1 管理后台（首轮必交付）

后台入口为管理端口的 `/`，与管理 API 同源部署。开发者不需要编写 curl 请求，就能完成“查看状态 → 修改数据或切换场景 → 打开目标页面 → 恢复默认”的完整流程。

后台按**验证流程**组织，而不是按内部数据模型平铺。顶部是四步向导，右侧常驻目标页实时预览：

```
① 建立基线  →  ② 应用变更  →  ③ 核对页面  →  ④ 恢复
                                    ↑
                          右侧 iframe 实时预览目标页
```

| 区域 | 内容 | 操作结果 |
|---|---|---|
| 连接与认证 | 输入管理 token、连接状态、退出 | 认证成功后读取状态；认证失败显示可读错误，不展示受保护数据 |
| 步骤条 | 四步进度、当前生效场景、一键跳转 | 应用场景后自动推进到「核对页面」 |
| ① 建立基线 | 应用 `baseline` 场景、`reset`；当前 revision、商品价、列表行、评价数、故障 | 两者都恢复默认并清除故障，语义差异在界面内解释 |
| ② 应用变更 | 按「基线 / 价格变化 / 商品内容 / 列表与分页 / 故障注入」分组的场景卡片；手动编辑（商品字段 / 列表行 / 评价三个标签页）；故障注入控件 | 应用前二次确认；每张卡片显示中文标题、采集方会看到什么、哪个数据字段变化 |
| ③ 核对页面 | 当前 revision 与生效场景、选择器参考（按主要/就绪/辅助/诱饵分组，含 CSS、XPath、复制）、本次变更的字段级 diff | 诱饵节点被明确标注，避免误选 |
| ④ 恢复 | 恢复到基线、`reset`；当前故障与延迟 | 故障不会自动恢复，必须显式操作 |
| 实时预览 | 目标页 iframe，标签切换 `/static/product`、`/ssr/product`、列表页、JSON | 任何变更后自动重载；以 1180 px 桌面宽度渲染再缩放，保证价格区与图库并排可见 |
| 操作反馈 | 提交中、成功、字段错误、认证失效、网络失败 | 请求期间禁用重复提交；失败时保留编辑内容，不伪报保存成功 |

预览以桌面宽度渲染的原因：商品页在 900 px 断点会改为单列，若直接按预览面板宽度渲染，价格区会被挤到图库下方，恰好看不到要验证的内容。

预览 iframe 带 `sandbox="allow-scripts allow-same-origin"`：脚本必须允许（CSR 页面要在浏览器里渲染），但目标页不应能操作后台。

后台复用下述 API，不维护独立业务状态或另一套场景实现。未保存的表单内容与已生效状态明确区分；服务端校验是最终依据。管理请求结果未知时先刷新状态核对，不自动重放写入。

token 由使用者输入，只保存在当前页面内存中；刷新或退出后清除，不写入 URL、localStorage 或日志，也不内置进前端资产。未认证时只提供连接界面，状态与写操作仍由 API 认证保护。后台及其资产离线可用，不受目标站故障注入影响。

### 5.2 管理 API

页面服务与管理服务使用两个独立监听端口。页面端口不提供管理后台或挂载 `/_admin/*` 路由；所有管理 API 都需要 Bearer token。

| 方法 | 路径 | 目标行为 |
|---|---|---|
| `GET` | `/_admin/state` | 返回业务数据、控制项及当前版本 |
| `PATCH` | `/_admin/state` | 部分修改数据或控制项，成功后返回完整状态 |
| `POST` | `/_admin/reset` | 恢复默认数据、清除故障与计数器，推进版本 |
| `GET` | `/_admin/scenarios` | 列出已实现的场景、影响范围与预期页面变化 |
| `POST` | `/_admin/scenario/{name}` | 原子应用场景，返回变更前后完整状态（含版本） |

PATCH 中对象字段递归合并，数组整体替换；`null` 不表示删除且不允许作为字段值。`revision` 只读，未知键、类型错误、越界值和互斥条件冲突均返回 400，状态保持不变。未知场景返回 404。首轮不提供语义重复的整状态 PUT 接口。

管理服务的实现要求：

- 使用 `MOCKSITE_TOKEN`；未配置或不足 32 个非空白字符时拒绝启动。部署者使用安全随机值，不将其写进仓库。
- 缺失或错误凭据返回 401，不返回状态内容；管理 API 不启用跨域访问。
- 所有管理写入只接受 `application/json`，请求体最多 64 KiB；不支持的媒体类型返回 415，超限返回 413，JSON 或字段校验失败返回 400。
- 日志不输出 Authorization、请求体和完整 query；只记录方法、路由模板、状态码及版本等诊断信息。
- 状态、业务数据与页面响应使用 `Cache-Control: no-store`，避免客户端缓存干扰验证。
- 故障注入不影响管理服务、`/health` 和本地静态资产，确保故障后仍可恢复和诊断。

## 6. 实现与部署方案

### 6.1 技术选择

采用 Python 3.12 + FastAPI：用 schema 校验控制输入，用异步处理支持延迟场景，状态管理与页面渲染分别组织。一个进程持有状态并运行两个监听端口，不启用多个独立 worker，以免产生多份状态。

服务端模板生成静态及 SSR HTML；React/Vue 使用本地固定版本资产，动态列表保持最小实现。管理后台使用本地 React 资产构建表单与场景控制界面，通过同源 API 读写状态，不引入独立前端服务。容器以非 root 用户运行，支持只读根文件系统，不需要数据库或外部存储。

前端统一使用 **pnpm** 管理依赖和执行构建。`web/` 共用一个 `package.json` 和一个 `pnpm-lock.yaml`，覆盖管理后台及 React/Vue 目标页；不使用 `package-lock.json` 或 Yarn 锁文件。

**前端代码全部在 `web/` 下，`src/` 只放 Python 后端。** 具体分工：

| 位置 | 内容 | 是否参与构建 |
|---|---|---|
| `web/admin/` | 管理后台源码（React + Vite） | 是，产物到 `web/dist` |
| `web/targets/shared/` | 框架无关的目标页脚本与样式（`list.js`、`product.js`、`shop.css`、`img/`） | 否，原样分发 |
| `web/targets/react/` | `react-list.js` + 本地 UMD React 18.3.1 / react-dom + 许可证 | 否，原样分发 |
| `web/targets/vue/` | `vue-list.js` + 本地 UMD Vue 3.5.43 + 许可证 | 否，原样分发 |
| `web/targets/manifest.json` | 本地 UMD 资产清单（来源 URL、`sha512`、字节数） | 否，原样分发 |

`web/targets/` 不经过 Vite：`shared/`、`react/`、`vue/` 三个子树由站点进程分别挂载在 `/static/shared`、`/static/react`、`/static/vue`。构建 wheel 时通过 hatchling 的 `force-include` 把三个子树复制进包的 `mocksite/_static/`，因此生产镜像不依赖仓库里的 `web/` 目录。运行时解析顺序为：`MOCKSITE_TARGET_ASSETS` 显式配置 → 包内 `_static` → 仓库 `web/targets`（仅便于可编辑安装）。`package.json` 的 `packageManager` 字段已固定 pnpm `12.15.0`，锁文件由 pnpm 生成并提交。依赖安装和前端构建均在 Docker 内执行，部署构建使用冻结锁文件安装，确保使用已提交的依赖版本。构建入口为 `web/admin`（管理后台）；目标页使用随站点分发的 UMD 资产，不参与该构建。

Python 依赖同样在 Docker 内安装。宿主侧可选使用工作区共用的 conda 环境（`../.github/environment.yml`，环境名 `webmonitor`，Python 3.12），用于编辑、lint 与快速跑测试；`pyproject.toml` 的 pin 需与 `../.github/requirements-workspace.txt` 保持一致，容器构建仍以 `pyproject.toml` 为准。

### 6.2 网络边界

| 端口 | 用途 | 默认暴露方式 |
|---|---|---|
| `9000` | 目标页面、业务数据及健康检查 | 容器内监听；本地预览时映射到宿主 `127.0.0.1:9000` |
| `9001` | 管理后台及管理 API | 容器内监听；默认不发布宿主端口，仅控制网络可达 |

容器内的 `127.0.0.1` 不是宿主机回环地址。本地开发启动方式必须通过开发 overlay 配置 `127.0.0.1:9001:9001`，提供可从浏览器打开的管理后台；基础 Compose 仍不发布管理端口。不能仅靠容器内绑定回环地址实现跨容器管理。

端口分离不等于网络隔离。部署时需限制控制网络的参与者，并确保采集出口不能访问管理端口；token 仅用于管理后台和控制脚本，不提供给被采集页面或模型上下文。

### 6.3 接入采集方

mocksite 只负责在 `9000`（页面）与 `9001`（管理）上提供内容与状态控制，不关心采集方如何出网。若采集方自带出口代理或私网限制，放行 mocksite 的精确主机与端口属于该采集方自己的部署配置，不在本仓库维护；本仓库不提供任何按平台划分的接入目录。

采集方需要知道的三件事：

- 采集地址：容器网络内的服务名，compose 下为 `http://site:9000`（注意是服务名，不是 compose 项目名），由 `MOCKSITE_COLLECT_ORIGIN` 决定后台展示值；
- 预览地址：开发者浏览器可打开的地址，由 `MOCKSITE_PUBLIC_ORIGIN` 决定；
- 管理端口不得暴露给被采集页面或采集出口，token 只交给后台与控制脚本。

`compose.yaml` 现在包含可运行的 `site` 服务（生产镜像 `deploy/Dockerfile`）与按 profile 隔离的 `dev` 工具链服务；启动、认证、管理请求与关闭步骤见 §6.4。

## 6.4 运行方式

### 启动

```sh
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

### 管理操作

后台与脚本走同一套 API，二选一即可：

```sh
export MOCKSITE_TOKEN=$(grep ^MOCKSITE_TOKEN .env | cut -d= -f2)

python scripts/control.py state                      # 当前状态（含 revision）
python scripts/control.py scenarios                  # 场景清单
python scripts/control.py scenario price_change      # 应用预设，输出 before/after
python scripts/control.py patch '{"business":{"page_size":3}}'
python scripts/control.py pages                      # 采集地址/预览地址/选择器
python scripts/control.py reset                      # 恢复默认并清除故障
```

退出码：`0` 成功，`1` 请求失败（含 401/404/400），`2` 用法或 JSON 错误。

### 停止

```sh
docker compose down            # 保留镜像
docker compose down --rmi local
```

状态保存在进程内存中，容器重启即恢复默认数据，revision 重新计数。

### 浏览器验收

两个脚本位于 `tests/acceptance/`（浏览器验收，不属于 pytest），都以真实 Chromium 驱动已启动的站点，并先调用 reset 建立已知基线：

```sh
python tests/acceptance/check_admin_ui.py       # 管理后台 42 项
python tests/acceptance/check_target_pages.py   # 目标页 62 项，并断言无任何外部请求
```

默认访问 `http://127.0.0.1:9000` 与 `9001`，可用 `--site-origin` / `--admin-origin` 覆盖。

### 已验证的边界

- 镜像以 UID `10001` 运行，根文件系统只读（`read_only: true`），仅 `/tmp` 可写；实测 `/app`、`/etc` 写入被拒绝。
- 基础 Compose 下宿主机直连 `9001` 被拒绝；overlay 下才可访问。
- 容器内 `http://site:9000` 与 `http://site:9001` 均可访问（`site` 是 compose 服务名；`mocksite` 只是项目名，不解析）。
- `/health` 在故障注入期间仍返回 200，管理 API 不受故障影响。

## 7. 交付顺序与验收

按依赖顺序推进；**首轮交付包含 P1–P3，管理后台从 P1 开始建设，在首轮结束前完成 §5.1 的全部功能。** 每个阶段的验收应保留实际输出，不能只证明页面返回了 HTTP 200。

| 阶段 | 交付内容 | 完成标准 |
|---|---|---|
| P1：管理后台与商品页面 | 状态校验、管理认证、版本、reset、static/SSR、商品变化与故障场景；后台认证、状态总览、商品编辑、场景控制与操作反馈 | 在后台完成“默认价格 → 修改 → 恢复”；非法写入不改变状态；500 期间仍可打开后台并恢复；API 返回状态与后台显示一致 |
| P2：浏览器与列表 | React/Vue、本地资产、就绪标记、动态分页、列表场景；后台列表编辑、页大小与故障控制、页面入口及选择器复制 | 浏览器离线加载并按选择器提取；通过后台修改列表后，目标页面同步变化；分页获得完整有序 ID；区分空列表、加载失败与重复行 |
| P3：容器与平台联调 | Dockerfile、基础 Compose 与本地开发 overlay、控制脚本、平台测试 overlay、运行文档；后台完整流程验收 | 一条文档化命令启动并可访问后台；管理端口无公网发布；浏览器完成 §5.1 全部操作；两个平台分别完成基线、变化、故障、恢复验证 |
| P4：扩展故障与安全验证 | 固定失败序列、单请求延迟、单页覆盖、安全探针 | 相同操作序列产生相同响应；单页覆盖不泄漏到其他页面；受限目的地址未被访问，有出口或探针证据 |

各阶段都需满足以下通用标准：

- **可复现**：从 reset 开始执行相同操作，得到相同业务内容与故障顺序；版本元数据除外。
- **状态一致**：非法请求不产生部分更新；读响应对应完整快照；重启恢复默认状态。
- **提取可验证**：商品页检查原始 HTML；CSR 页面检查浏览器渲染后的 DOM。不能要求 curl 返回已经渲染的 React/Vue 列表。
- **后台可用**：通过真实浏览器验证认证、表单保存、场景切换和重置；覆盖错误 token、非法输入、请求失败与目标站 500，确认错误反馈准确、失败不误报成功、管理功能仍可用。
- **结果归属清楚**：mocksite 证明输入是什么；平台联调证明提取、事件与通知实际发生了什么。告警次数及错误码以各平台契约为准。
- **实现与文档一致**：只有已经通过验收的能力才标记为可用；不发布虚构镜像、无效环境变量或未经验证的接入示例。

## 8. License

本仓库采用 [CC BY-NC 4.0](LICENSE)（署名—非商业性使用）。第三方前端资产保留各自许可证与声明。
