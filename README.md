# webmonitor-mocksite

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
![status: spec](https://img.shields.io/badge/status-spec%20%2F%20unimplemented-orange)

为 [WebMonitor-Agent](https://github.com/webmonitor/WebMonitor-Agent) 与 [WebMonitor](https://github.com/webmonitor/WebMonitor) 两个监控平台提供**可控制、可复现的被采集目标网站**。

一个容器，多种前端技术形态的真实网页；通过管理 API 任意切换页面“发生什么”，用来驱动、验证两个平台的采集、变化检测与告警链路。

> **状态：设计规格。** 本仓库目前只有本 README —— 它是完整的实现蓝图。接口、页面、场景、校验点均已定型，欢迎按此实现；提 PR 前请先跑通「验收清单」。

---

## 1. 为什么需要它

两个监控平台的测试痛点：

| 痛点 | mocksite 的回答 |
|---|---|
| 真实网站内容不受控，无法稳定复现“变化” | 场景（scenario）一键切换，内容变化完全确定 |
| 不同前端渲染方式（CSR/SSR/懒加载）采集行为不同 | 一个站点内提供 static / SSR / React / Vue / 动态加载五类页面 |
| 想测失败路径：超时、500、选择器失效、反爬 | 每种失败都是一个显式状态开关 |
| WebMonitor 用 XPath（Selenium），Agent 用 CSS 选择器（HTTP/Playwright） | 每个页面同时标注两套选择器，双端共用同一目标 |

与 WebMonitor-Agent 自带的 `tests/fixtures/site.py`（smoke 专用、最小化）不同，本项目是**独立的、面向日常开发与演示的**目标站：场景更丰富、可直接 docker compose 挂进两个平台的 compose 网络。

## 2. 页面形态（被采集目标）

所有页面共享同一份“商品数据”（见 §3 状态模型），保证同一场景在五种形态下产生**语义相同**的内容变化。

| 路径 | 形态 | 渲染方式 | 考察能力 |
|---|---|---|---|
| `/static/product` | 纯静态 HTML | 服务端直出，无 JS | HTTP 路径基线 |
| `/ssr/product` | 服务端渲染 | 每次请求实时渲染 | SSR 内容、无 JS 依赖 |
| `/react/list` | React 18 SPA (CSR) | UMD React + fetch `/api/data` 渲染 | 等待选择器、JS 渲染后提取 |
| `/vue/list` | Vue 3 SPA (CSR) | UMD Vue + fetch 渲染 | 同上，换框架 |
| `/dynamic/deals` | 动态加载列表 | 懒加载 + “加载更多”按钮分页 | `wait_for_selector` / `click_next` 浏览器步骤、翻页聚合 |
| `/api/data` | JSON 数据源 | — | HTTP 型监控直连数据 |
| `/slow?ms=3000` | 慢响应 | 服务端延迟后返回 | 超时与重试策略 |
| `/flaky` | 抖动端点 | 按 `failure_rate` 随机 500/200 | 瞬时故障→恢复场景 |
| `/redirect-private?target=loopback\|metadata\|ipv6` | 重定向到私网/元数据地址 | 302 | **安全验证**：出口必须拒绝（Agent egress 容器、legacy 白名单） |
| `/private-resource` | 页面内引用私网资源 | `<script src="http://127.0.0.1:9/…">` | 混合内容/私网资源探测 |

前端资产：React/Vue UMD 包 **vendored**（构建时从官方 npm tarball 下载并校验 SHA-512，写死 `assets/vendor/manifest.json`），**运行时不依赖任何 CDN** —— 站点必须能在离线内网完整工作。

每个列表页顶部提供固定结构：

```html
<div id="app" data-framework="react">
  <table id="inventory">
    <tbody>
      <tr class="item" data-id="A"><td class="name">Alpha</td><td class="price">10.00</td></tr>
      ...
    </tbody>
  </table>
  <p id="status" role="status">…</p>
  <button id="load-more">Load more</button>  <!-- 仅 /dynamic/deals -->
</div>
```

**选择器对照（写入每个页面文档的固定注释，供两个平台的监控配置直接复制）：**

| 字段 | CSS（WebMonitor-Agent） | XPath（WebMonitor） |
|---|---|---|
| 商品价格 | `#product #current-price` | `//*[@id="current-price"]` |
| 列表行 | `#inventory tr.item` | `//*[@id="inventory"]/*[@class="item"]` |
| 行内价格 | `tr.item td.price` | 相对 `.//td[@class="price"]` |

## 3. 状态模型（单一事实源）

全部页面读取同一份内存状态。**所有价格一律十进制字符串**（与两个平台的 Decimal 约定一致，禁止 float）：

```jsonc
{
  // 商品数据（五种页面形态共享）
  "current_price": "128.50",       // 十进制字符串
  "original_price": "199.00",
  "currency": "USD",               // 三位大写字母
  "items": [                       // ≤100 行
    {"id": "A", "name": "Alpha", "price": "10.00"}
  ],
  "total_pages": 3,                // /dynamic/deals 分页总数

  // 失败注入
  "http_500": false,               // 全站页面 500
  "empty": false,                  // 数据为空（≠ 缺失：测 “missing ≠ empty”）
  "slow_ms": 0,                    // 人为延迟 0..30000
  "flaky_failure_rate": 0.0,       // /flaky 专用 0.0..1.0

  // 结构变化
  "selector_changed": false,       // 把 id 换成 replacement-current-price（选择器失效）
  "rename_field": false,           // td.price → td.cost（字段级结构漂移）
  "duplicate": false,              // 注入重复行（覆盖校验）

  // 行为
  "private_resource": false        // 页面内引用私网资源
}
```

**不变量**（实现时必须校验）：
- 价格字段：十进制、有限、非负、≤64 字符；
- `items[].id/name`：非空字符串 ≤256 字符；
- 未知键拒绝 PATCH（防拼写错误静默生效）。

## 4. 管理（控制面）API

前缀 `/_admin/`，**必须**由环境变量 `MOCKSITE_TOKEN`（≥32 随机字符）开启 Bearer 认证；未配置 token 时拒绝所有管理请求（宁可拒绝，不可裸奔）。管理端口不发布到宿主（见 §6）。

| 方法 | 路径 | 作用 |
|---|---|---|
| `GET` | `/_admin/state` | 读当前完整状态 |
| `PATCH` | `/_admin/state` | 部分更新（深度合并，逐键校验） |
| `PUT` | `/_admin/state` | 整体替换 |
| `POST` | `/_admin/reset` | 恢复默认状态 |
| `POST` | `/_admin/scenario/{name}` | 一键执行预设场景（§5） |
| `GET` | `/_admin/scenarios` | 列出全部场景及其效果说明 |
| `GET` | `/health` | 无认证健康检查 `{"status":"ok"}` |

安全基线（沿用 fixture 的纪律）：
- 日志**不记录**任何 token、请求路径或 query；
- `PATCH` body ≤ 64KiB、拒绝 `Transfer-Encoding`；
- 管理响应与页面响应都带 `Cache-Control: no-store`。

## 5. 预设场景

每个场景 = 一组受控状态转移，全部**确定性**（除 `/flaky` 显式随机外）：

| 场景名 | 动作 | 验证点（两平台各自应表现） |
|---|---|---|
| `price_change` | `current_price` 128.50 → 96.00 | 变化检测、diff 正确、（配置邮件时）告警 |
| `no_change` | 重置后仅触碰无关字段 | 不产生事件 |
| `gone` | `empty=true` | 缺失处理：Agent “missing ≠ empty”语义；legacy 记录错误 |
| `structure_break` | `selector_changed=true` | Agent 报 `extraction_*` 错误而非静默成功；legacy XPath 落空 |
| `field_rename` | `rename_field=true` | 字段级 diff 识别“列名变了” |
| `duplicate_rows` | `duplicate=true` | 覆盖/去重证明（Agent coverage 语义） |
| `outage` | `http_500=true` → 60s 后自动恢复 | 故障→恢复两种告警、重试只对瞬时错误生效 |
| `slow_site` | `slow_ms=8000` | 超时路径、租约/fencing 下的重试行为 |
| `flaky_50` | `flaky_failure_rate=0.5` | 瞬时失败统计、最终成功 |
| `pagination_grow` | `total_pages` 1→3，每页内容不同 | `click_next` 聚合完整性、翻页后 diff 基线 |
| `ssr_vs_csr_drift` | 仅 `/react/list` 数据变化，`/static/product` 不变 | 单页面定向变化不影响其他监控 |
| `private_egress` | 恢复 + `private_resource=true` | 出口安全：两平台都必须失败/拒绝，不得触达私网 |

实现要求：场景执行是**原子的**（一次锁内完成状态写入），并返回转移前后状态。

## 6. 运行

```sh
# 构建并启动（仅暴露被采集端口，管理端口只在内部网络）
export MOCKSITE_TOKEN="$(openssl rand -hex 32)"
docker compose up --build -d

# 被采集端（宿主可见，供本地前端/HTTP worker 指向）
curl http://localhost:9000/static/product

# 管理（容器网络内，或显式发布的 127.0.0.1:9001）
curl -H "Authorization: Bearer $MOCKSITE_TOKEN" \
     -X POST http://127.0.0.1:9001/_admin/scenario/price_change
```

端口约定：
- **9000** — 被采集页面（可发布宿主或仅在 compose 内网）；
- **9001** — 管理 API（默认只绑 `127.0.0.1`，绝不 `0.0.0.0`）。

单容器、无外部依赖（数据在内存，重启即重置 —— 这是特性：状态可复现）。

### 接入两个平台（compose 片段）

```yaml
# WebMonitor-Agent 的 compose overlay 示例
services:
  mocksite:
    image: ghcr.io/webmonitor/mocksite:latest
    networks: [trusted]          # 只在采集出口网络
  http-worker:
    environment:
      MOCK_TARGET: http://mocksite:9000
```

WebMonitor legacy 同理：监控任务 URL 填 `http://mocksite:9000/...`，XPath 用 §2 对照表。

## 7. 技术选型（建议，非强制）

- **服务端**：Python 3.12 标准库 `http.server`（对齐 fixture 风格）或 FastAPI —— 零/极低依赖优先；
- **前端**：不引入构建链。React/Vue 用 vendored UMD 单文件；页面模板用 Python f-string（同 fixture）；
- **容器**：`python:3.12-slim`，非 root 用户，只读根文件系统兼容。

## 8. 验收清单（实现 PR 必须逐条演示）

- [ ] 五种页面形态 curl 均返回含 §2 固定结构的 HTML；React/Vue 页面离线可用（无外网请求）
- [ ] `PATCH /_admin/state` 非法键/非法十进制 → 400，且状态不变
- [ ] `price_change` 场景后，同一 CSS 与 XPath 选择器在 5 种页面取到一致新价格
- [ ] `structure_break` 后 Agent 端提取报错（不静默成功）
- [ ] `/redirect-private` 与 `/private-resource` 在两平台的采集路径上被拒绝
- [ ] 无 token 时所有 `/_admin/*` → 403；日志无 token/路径
- [ ] `docker compose up` 一次成功；管理端口未发布到 `0.0.0.0`

## 9. License

CC BY-NC 4.0 —— 与 WebMonitor / WebMonitor-Agent 一致（非商业使用）。
