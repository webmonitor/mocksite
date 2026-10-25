# 交付计划

本目录记录实施任务与进度；页面、状态、管理后台及 API 的目标契约以 [项目 README](../README.md) 为准。变更已经发生后记录到 [changelog](../changelog/README.md)，不能把计划写成已交付能力。

当前状态：阶段 0（工具链骨架）、阶段 1（状态内核）与阶段 2（双端口 HTTP）已完成。`pyproject.toml`、`web/package.json` + `pnpm-lock.yaml`、`deploy/dev.Dockerfile`、`compose.yaml` 的 `dev` 服务、`src/mocksite/state/`、`src/mocksite/scenarios/`、`src/mocksite/{config,cli}.py`、`admin/{auth,api}.py`、`site/{render,routes}.py` 已落地，进程可实际启动并响应两个端口；列表页、后台界面、部署镜像与平台联调仍待实现。首轮交付包含 P1–P3，管理后台是必交付内容。

## 实施阶段

按依赖顺序推进。阶段 0–6 是可执行的落地顺序，P1–P4 是验收分组：P1 = 阶段 0–3，P2 = 阶段 4，P3 = 阶段 5，P4 = 阶段 6。

```mermaid
graph LR
  S0[0 工具链骨架] --> S1[1 状态内核 ✅]
  S1 --> S2[2 双端口 HTTP]
  S2 --> S3[3 管理后台 SPA]
  S2 --> S4[4 列表与 CSR]
  S3 --> S5[5 容器与平台联调]
  S4 --> S5
  S5 --> S6[6 P4 扩展]
```

| 阶段 | 产出 | 关键约束 | 完成标准 |
|---|---|---|---|
| 0 工具链骨架 | `pyproject.toml`、`requirements*.txt`、`.gitignore`、`web/package.json` + `pnpm-lock.yaml`、`deploy/dev.Dockerfile`、`compose.yaml`（dev 服务） | Python `>=3.12,<3.13` 装进镜像，不在宿主建 venv；Python 依赖无锁文件，由 `uv pip compile --generate-hashes` 从 `pyproject.toml` 生成；pnpm 版本写入 `packageManager` 并由 pnpm 生成锁文件 | 容器内 `python -c "import mocksite"` 与 `pnpm install --frozen-lockfile` 均成功 |
| 1 状态内核 ✅ | `src/mocksite/state/{models,patch,store,errors}.py`、`scenarios/registry.py` | 纯逻辑无 HTTP；校验、提交、版本递增、静态页重渲在同一次锁内完成 | `tests/unit` 通过；非法输入不改变状态也不推进版本 |
| 2 双端口 HTTP ✅ | `src/mocksite/cli.py`、`config.py`、`admin/{auth,api}.py`、`site/{render,routes}.py`、`site/templates/*` | 单进程、两个监听器共享同一个 `StateStore`，禁止多 worker；9001 不挂站点路由 | 401/415/413/400 与 `no-store`、`X-Mocksite-Revision` 符合 §5.2 |
| 3 管理后台 SPA | `web/admin/src/**`（复用已有 `features/{connection,state,scenarios,targets}` 目录） | token 只存页面内存；同源调用 `/_admin/*`；失败保留表单内容 | 真实浏览器完成“默认价 → 修改 → 恢复”；500 期间仍能恢复 |
| 4 列表与 CSR | `web/targets/{shared,react,vue}`、`site/static/vendor/`、`/dynamic/deals` | 本地 UMD 资产、无 CDN；行必须是 `<table>` 结构以匹配 §3.3 选择器 | 浏览器离线渲染；分页得到完整有序 ID；空列表、加载失败、字段缺失、重复行可区分 |
| 5 容器与平台联调 | `deploy/Dockerfile`、`compose.yaml`、`compose.dev.yaml`、`scripts/control.py`、`integrations/{agent,legacy}` | 非 root、只读根文件系统；基础 Compose 不发布 9001，dev overlay 才映射 `127.0.0.1:9001` | 一条命令启动并访问后台；两个平台分别完成基线、变化、故障、恢复 |
| 6 P4 扩展 | `/flaky`、`/slow`、单页覆盖、安全探针 | 确定性序列与计数，reset 清零；探针只接受固定枚举 | 相同序列产生相同响应；受限地址未被访问（出口或探针计数证据） |

### 阶段 0：工具链骨架

- [x] 创建 `pyproject.toml`（hatchling，包 `mocksite`，源码根 `src`）与 `.gitignore`（`__pycache__`、`.venv`、`node_modules`、构建产物、本地 `.env`）。
- [x] 在 `web/package.json` 写入 `packageManager` 固定 pnpm 精确版本，生成并提交 `pnpm-lock.yaml`；管理后台与 React/Vue 目标页共用这一份清单。
- [x] 提供 dev 工具链 Dockerfile（Python 3.12 + Node 22 + pnpm），依赖安装与前端构建都在容器内执行，部署构建使用冻结锁文件。

### 阶段 1：状态内核

- [x] 定义状态模型：业务数据（商品、列表、`page_size`）、互斥呈现枚举、故障项、只读 `revision`。
  `src/mocksite/state/models.py`：`State`/`BusinessData`/`Product`/`Item`/`Presentation`/`Faults`，全部 frozen + `extra="forbid"`；价格用 `Decimal` + 前后置校验（仅接受 `<digits>[.<digits>]` 字符串，拒绝浮点、指数、负号、非有限值、>64 字符），序列化为十进制字符串；`page_count` 派生不存储。
- [x] 实现 `PATCH` 语义：对象递归合并、数组整体替换、`null` 与未知键报错。
  `src/mocksite/state/patch.py`：`null`、任意深度的 `revision`、未知 section/key 全部拒绝并给出 `loc`；一次返回全部错误。
- [x] 实现锁内的“校验 → 静态页渲染 → 提交 → 版本递增”，保证不存在状态已更新而静态页仍旧的窗口。
  `src/mocksite/state/store.py`：`_commit_locked` 在同一把锁内完成“递增 revision → 渲染 → 同时替换 state 与 static_html”；渲染抛错时状态与页面都不前进（`test_renderer_failure_does_not_advance_state_or_page`、`test_failed_render_keeps_previous_page_content`）。
- [x] 实现场景注册表：每个场景从默认状态构造完整目标状态后一次性提交，场景之间不叠加。
  `src/mocksite/scenarios/registry.py`：13 个预设（`baseline`…`slow_site`），`PresetScenario.build()` 返回完整 `State`；`test_scenarios_do_not_stack` 覆盖 `outage → price_change` 清除故障。
- [x] 单元测试覆盖价格校验（`Decimal`、非负、有限、≤64 字符）、列表边界（0–100 行、页大小 1–100）、非法请求不推进版本。
  `tests/unit/test_state_models.py`、`test_state_patch.py`、`test_state_store.py`、`test_scenarios.py`；容器内 `pytest -q` → `171 passed`。

**遗留到阶段 2**：静态页渲染器目前是注入的 `Renderer`（默认返回空串），真实 Jinja2 模板在实现 `/static/product` 时提供；故障注入的消费方（站点路由）也属于阶段 2。

### 阶段 2：双端口 HTTP

- [x] `cli.py` 内并发运行两个 `uvicorn.Server`，共享同一 `StateStore`；不启用多进程。
  `src/mocksite/cli.py`：`asyncio.wait(FIRST_COMPLETED)` 同时托管两个 server，任一退出即取消另一个；只有站点 server 安装信号处理器，`SIGTERM` 实测退出码 0 且两个监听器都打印 `Shutting down`。`mocksite --check` 仅校验配置不绑定端口。`pyproject.toml` 增加 `mocksite` console script。
- [x] 管理端口实现 Bearer 认证（`MOCKSITE_TOKEN` 未配置或不足 32 个非空白字符时拒绝启动）、`GET/PATCH /_admin/state`、`POST /_admin/reset`、`GET /_admin/scenarios`、`POST /_admin/scenario/{name}`。
  `src/mocksite/admin/auth.py` 用 `secrets.compare_digest` 常量时间比较，401 不返回状态内容；`src/mocksite/admin/api.py` 实现五个路由，`reset` 与场景应用返回 `before`/`after`；`src/mocksite/config.py` 在启动时拒绝弱 token（`Settings.token` 设 `repr=False`，避免泄漏到日志与 traceback）。
- [x] 站点端口实现 `/static/product`（预渲染）、`/ssr/product`、`/api/data`、`/health`，全部带 `X-Mocksite-Revision` 与 `no-store`。
  `src/mocksite/site/routes.py` + `site/render.py` + `site/templates/product.html`：`/static/product` 直接返回提交时预渲染的 HTML，`/ssr/product` 每次按快照渲染；`/api/data` 附带 `revision` 与派生的 `page_count`；`/health` 返回 `{"status":"ok"}`。
- [x] 故障注入只作用于站点业务路由，不影响管理服务、`/health` 与本地资产。
  `_faults` 中间件放行 `/health`；`outage` 优先于 `delay_ms`（`test_outage_takes_precedence_over_delay`）；`test_admin_survives_site_outage`、`test_recovery_after_outage_restores_pages` 覆盖恢复路径。
- [x] 请求体上限 64 KiB、只接受 `application/json`、日志不输出 Authorization 与请求体。
  流式读取时累计字节数并在超限时返回 413（不信任 `Content-Length`），非 `application/json` 返回 415，空体与坏 JSON 返回 400；日志只记方法、路由模板、状态码与 revision（`test_admin_logs_never_contain_token_or_body`）。

**尚未覆盖**：列表页与 CSR 目标页属阶段 4；后台界面属阶段 3；`tests/browser/` 为空。

### 阶段 3：管理后台 SPA

- [ ] 连接与认证：token 输入、连接状态、退出；刷新即清除，不写 localStorage/URL。
- [ ] 状态总览与手动刷新；商品字段表单；列表行增删改与页大小编辑；呈现控制项。
- [ ] 场景列表（含影响范围）、应用预设、恢复默认；应用前提示覆盖当前状态，成功后展示前后版本。
- [ ] 目标页面入口：区分宿主预览地址与平台采集地址，提供 CSS/XPath 复制。
- [ ] 操作反馈：提交中禁用、字段错误、401 失效、网络失败；失败不伪报成功。
### 阶段 4：列表与 CSR

- [ ] 落地本地 React/Vue UMD 资产与许可证/完整性清单（可复用 Agent `tests/fixtures/static/vendor/` 的版本与校验值，资产随站点分发）。
- [ ] React/Vue 列表页：加载成功后才设 `data-ready="true"` 并写入 `data-revision`，失败显示错误且不设就绪标记。
  `site/static/assets/{list,react-list,vue-list}.js` + `site/templates/list.html`：`#app` 由服务端渲染为空壳（不含任何行），页面脚本 fetch `/api/data` 后才挂载；React 在 `createRoot().render()` 后、Vue 在 `nextTick` 后调用 `markReady()`。失败时写入 `#status[data-state=error]` 且不设 `data-ready`。
- [ ] `/dynamic/deals`：首屏一页、点击追加、加载中禁用、末页隐藏按钮；空列表也进入就绪状态。
- [ ] 列表相关场景：`item_price_change`、`empty_list`、`field_rename`、`duplicate_rows`、`pagination_grow`。
### 阶段 5：容器与平台联调

- [ ] 生产镜像（非 root、只读根文件系统、无数据库与外部存储）与基础 `compose.yaml`；仅发布 9000，9001 走控制网络。
- [ ] `compose.dev.yaml` 映射 `127.0.0.1:9001:9001` 供浏览器打开后台；控制脚本封装 `/_admin/*` 调用。
- [ ] 为 Agent 增加精确 origin 例外（见下文阻塞 1），保持管理端口对采集出口不可达；legacy 单独确认网络与安全限制。
- [ ] 运行文档：构建、启动、后台访问与认证、管理请求、关闭，并验证宿主与容器内两条访问路径。
- [ ] 完成 README §5.1 全部后台功能的浏览器验收并保留证据。

### 阶段 6：P4 扩展

- [ ] `/flaky` 固定序列与按端点计数，reset 清零。
- [ ] `/slow?ms=` 仅影响当前请求，边界 0–30000，非法输入 400。
- [ ] 单页数据覆盖，显式出现在状态中，reset 清除。
- [ ] `/redirect-private?target=` 与 `/private-resource`，只接受固定枚举。

## P1：管理后台与商品页面

- [x] 在 Docker 开发环境中初始化 `web/package.json`，固定 pnpm 版本并生成 `pnpm-lock.yaml`；提供后台构建入口，部署构建采用冻结锁文件安装。
- [x] 实现单进程状态管理、输入校验、原子提交、版本递增与 reset。见阶段 1。
- [x] 实现独立管理端口、Bearer 认证和管理 API。见阶段 2。
- [x] 实现 static/SSR 商品页、稳定选择器与响应版本标记。见阶段 2。
- [x] 实现商品价格变化、空文本、节点缺失、结构破坏、500 与延迟场景。见阶段 2。
- [ ] 实现后台认证、状态总览、商品编辑、场景控制及操作反馈。
- [ ] 用真实浏览器完成“默认价格 → 修改 → 恢复”，验证非法写入不改变状态，目标站 500 时仍能通过后台恢复。

## P2：浏览器与列表

依赖 P1 的状态与管理 API。

- [ ] 实现 React/Vue 列表、本地前端资产、就绪标记及数据版本展示。
- [ ] 实现动态分页、稳定行 ID、加载期间禁用与末页结束行为。
- [ ] 实现列表价格变化、空列表、字段改名、重复行及分页增长场景。
- [ ] 完成后台列表增删改、页大小编辑、呈现控制及目标页面入口。
- [ ] 提供 CSS/XPath 复制，区分宿主预览地址与平台采集地址。
- [ ] 验证离线渲染、完整有序分页及后台修改后的实际页面内容。

## P3：容器与平台联调

依赖 P1、P2；本阶段通过后才算首轮交付完成。

- [ ] 提供 Dockerfile、基础 Compose、本地开发 overlay 与控制脚本。
- [ ] 提供可执行的启动、后台认证、管理请求和关闭文档。
- [ ] 为 Agent 配置精确 origin、DNS 和出口例外，保持管理端口不可被采集出口访问。
- [ ] 分别验证 Agent 与 legacy 的基线、变化、故障和恢复行为。
- [ ] 完成 README §5.1 全部后台功能的浏览器验收，包括错误凭据、非法输入、请求失败和重置。
- [ ] 记录执行环境、操作步骤、预期结果及实际证据；邮件验证仅在显式启用时执行。

## P4：后续扩展

不阻塞首轮交付。

- [ ] 实现确定性失败序列与计数器重置。
- [ ] 实现单请求延迟及参数边界校验。
- [ ] 实现单页面数据覆盖与 reset 清除。
- [ ] 实现固定私网重定向和子资源探针，以出口记录或探针计数证明受限地址未被访问。

## 维护方式

仅在实现及对应验收均完成后勾选任务，并附证据位置。较大的独立任务可新增 `YYYY-MM-DD-topic.md`，在本文件对应阶段链接；内容包含目标、范围、依赖、实施步骤和验收结果。需求变化同时更新 README 契约、相关计划和变更记录，避免三处描述冲突。
