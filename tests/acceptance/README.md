# 验收测试（浏览器）

这里的脚本驱动**真实 Chromium** 访问一个**已启动的站点**，验证采集方实际看到的东西。它们不是 pytest 测试。

## 为什么不放在 pytest 里

它们需要：

1. 一个正在运行的栈（`site` 容器，9000 + 9001 端口）；
2. 真实的管理 token；
3. 真实浏览器（Chromium / Playwright）。

放进 `testpaths` 会让 `pytest -q` 默认失败或跳过，掩盖真实问题。所以它们留在 `tests/acceptance/`，由 `testpaths` 之外显式执行——目录名表明归属，执行方式保持独立。

`tests/unit/` 与 `tests/integration/` 是 pytest 收集的；本目录**不是**。

## 运行

```sh
cd mocksite
cp .env.example .env                                   # 设 MOCKSITE_TOKEN
docker compose -f compose.yaml -f compose.dev.yaml up --build -d --wait

export MOCKSITE_TOKEN=$(grep ^MOCKSITE_TOKEN .env | cut -d= -f2)
conda run -n webmonitor python tests/acceptance/check_admin_ui.py       # 管理后台，38 项
conda run -n webmonitor python tests/acceptance/check_target_pages.py   # 目标页面，47 项
```

两者都接受 `--admin-origin`、`--site-origin`、`--token`，默认 `http://127.0.0.1:9001` 与 `http://127.0.0.1:9000`。Playwright 包来自工作区根目录的 `.github/env/environment.yml`（conda 环境 `webmonitor`）；首次运行前如未安装浏览器，执行 `conda run -n webmonitor python -m playwright install chromium`。

**每次运行都会先 `POST /_admin/reset`**，所以可重复执行，且失败后站点处于已知状态。

退出码：`0` 全部通过，`1` 有失败项。

> 宿主机跑时若设了 `http_proxy`/`all_proxy`，记得加 `env -u no_proxy -u NO_PROXY -u all_proxy -u http_proxy -u https_proxy`。脚本内部已对 loopback 绕过代理，但 `no_proxy` 里的 `[::1]` 会让 httpx 解析失败。

## 文件

| 文件 | 内容 |
|---|---|
| `_harness.py` | 共用基建：`Results`、绕代理的 `admin_request`、`reset_server`、`apply_scenario`、`ConsoleLog`、token 读取、参数解析、退出码。**不含任何业务断言。** |
| `check_admin_ui.py` | 管理后台：错误 token、单页控制台（无向导、无选择器表、无 diff）、内嵌预览跟随、手动编辑与校验失败、恢复、token 不落盘、刷新/退出清除会话 |
| `check_target_pages.py` | 目标页面：通知页诱饵金额与同一发布时刻的多重渲染、脚本异步填充的点击次数、数据场景下结构不变、已删除的列表路由与资产返回 404、无外部请求 |

`check_target_pages.py` 会拦截并中止所有非站点请求，因此“无外部请求”通过也证明页面离线可用。

## 最近一次记录

2026-10-26 的单条通知收敛后实测：`check_admin_ui.py` → 38/38，`check_target_pages.py` → 47/47（见 [changelog](../../changelog/2026-10-26.md)）。2026-10-30 的文档整理没有重新运行这些脚本；数字只代表该历史记录。

## 加新验收套件的约定

1. 断言写在套件里，基建写进 `_harness.py`；
2. 套件导出 `run(args, token) -> Results`，入口写 `run_as_script(run)`；
3. **每条断言必须能被用户观察到**——HTTP 200 不是证据，要断言渲染后的文本或 DOM；
4. 先 reset 再开始，保证可重复；
5. 目标页脚本继续拦截外部请求，离线是契约的一部分。
