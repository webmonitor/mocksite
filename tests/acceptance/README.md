# 验收测试（浏览器）

这里的脚本驱动**真实 Chromium** 访问一个**已启动的站点**，验证采集方实际看到的东西。

## 为什么不放在 pytest 里

它们需要：

1. 一个正在运行的栈（`site` 容器，9000 + 9001 端口）；
2. 真实的管理 token；
3. 真实浏览器（Chromium）。

放进 `testpaths` 会让 `pytest -q` 默认失败或跳过，掩盖真实问题。所以它们留在 `tests/acceptance/`，由 `testpaths` 之外显式执行——目录名表明归属，执行方式保持独立。

`tests/unit/` 与 `tests/integration/` 是 pytest 收集的；本目录**不是**。

## 运行

```sh
cd mocksite
cp .env.example .env                                   # 设 MOCKSITE_TOKEN
docker compose -f compose.yaml -f compose.dev.yaml up --build -d --wait

export MOCKSITE_TOKEN=$(grep ^MOCKSITE_TOKEN .env | cut -d= -f2)
python tests/acceptance/check_admin_ui.py              # 管理后台
python tests/acceptance/check_target_pages.py          # 目标页面
```

两者都接受 `--admin-origin`、`--site-origin`、`--token`，默认 `http://127.0.0.1:9001` 与 `http://127.0.0.1:9000`。

**每次运行都会先 `POST /_admin/reset`**，所以可重复执行，且失败后站点处于已知状态。

退出码：`0` 全部通过，`1` 有失败项。

> 宿主机跑时若设了 `http_proxy`/`all_proxy`，记得加 `env -u no_proxy -u NO_PROXY -u all_proxy -u http_proxy -u https_proxy`。脚本内部已对 loopback 绕过代理，但 `no_proxy` 里的 `[::1]` 会让 httpx 解析失败。

## 文件

| 文件 | 内容 |
|---|---|
| `_harness.py` | 共用基建：`Results`、绕代理的 `admin_request`、`reset_server`、`apply_scenario`、`ConsoleLog`、参数解析、退出码。**不含任何业务断言。** |
| `check_admin_ui.py` | 管理后台：错误 token、单页控制台（无向导、无选择器表、无 diff）、内嵌预览跟随、手动编辑与校验失败、恢复、token 不落盘 |
| `check_target_pages.py` | 目标页面：通知页诱饵金额与三种日期渲染、脚本异步填充的点击次数、数据场景下结构不变、已删除的列表路由与资产返回 404 |

## 加新验收套件的约定

1. 断言写在套件里，基建写进 `_harness.py`；
2. 套件导出 `run(args, token) -> Results`，入口写 `run_as_script(run)`；
3. **每条断言必须能被用户观察到**——HTTP 200 不是证据，要断言渲染后的文本或 DOM；
4. 先 reset 再开始，保证可重复。
