# Team Roll

团队 Roll 点平台：参与者在一个数值区间内领取不重复的随机数，管理员负责活动全生命周期、记录修正与审计。
FastAPI 提供 JSON API 与 WebSocket 实时通道，前端是无需构建步骤的 Vue 3 单页应用。

## 功能

- **Roll 点**：区间内去重发号（并发冲突自动重试）、每人参与上限、限定参与人数（满员后只有已上榜的名字还能继续 Roll，作废某人的全部记录即释放其名额）、作废后号码重新开放、按数值/时间/名字排序的实时排行榜（不限高度，跟随页面滚动）、开奖数字按区间百分位分七档只作配色（档位不向参与者解释，界面上不出现百分位说明）。
- **实时同步**：`/ws/{activity_id}` 推送 `hello`/`roll_result`/`roll_updated`/`roll_deleted`/`activity_*` 帧，附带在线人数。
- **管理后台**：仪表盘（KPI、趋势折线、状态分布、活动 Top、最近记录与审计）、活动创建/编辑（独立表单页 `/admin/activities/new`、`/admin/activities/{id}/edit`）、规则调整/暂停/结束/重开/删除、按记录 ID 作废·恢复·改名·改数值·删除·补录、记录列表附来源（IP + 浏览器标识，只在管理视图与导出中出现，参与者同名时靠它分辨记录来自哪台设备）、多管理员与角色、在线会话强制下线、审计日志、CSV/JSON 导出、系统状态。
- **安全**：pbkdf2_sha256 加盐口令、登录失败锁定、滑动窗口限流、HttpOnly 会话 Cookie + CSRF 双重提交、按能力的 RBAC（`read`/`manage`/`manage_admins`/`dangerous`）、每请求 CSP。
- **SEO/GEO**：按路由注入 title/description/canonical/OG/Twitter 与 JSON-LD，`sitemap.xml`、`robots.txt`，后台与未知路径 `noindex`。

## 快速开始

```bash
python -m venv .venv
.venv/Scripts/activate                     # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # Windows: copy .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8803 --reload
```

打开 <http://127.0.0.1:8803>，管理员入口在 <http://127.0.0.1:8803/login>。
首次启动会自动建表并跑 Alembic 迁移；设置了 `BOOTSTRAP_ADMIN_*` 时创建初始超级管理员，请登录后立即改密并把这两个变量删掉。

开发依赖（测试与 lint）：

```bash
pip install -r requirements-dev.txt
python -m pytest                 # 全部 API 与实时用例
python -m ruff check app tests alembic
```

## 架构

```
app/
  main.py            应用工厂：中间件、异常处理、路由装配、lifespan 迁移
  core/              config(pydantic-settings) / deps(鉴权·RBAC·CSRF) / errors / security / time / ws / logging
  db/                models(SQLAlchemy 2.0) / session(引擎·WAL PRAGMA) / migrate / base
  schemas/           Pydantic v2 出入参与分页
  services/          activity / roll / auth / admins / audit / stats / export（业务规则与不变量）
  api/v1/            HTTP 路由：activities / admin_* / auth / ws
  web/               SPA 外壳渲染（CSP + SEO 元信息）、sitemap、robots
static/
  index.html         唯一 HTML 入口，服务端按路由填充 <!--seo-slot-->
  js/lib/            api / router / store / ws / format / action / vue
  js/views/          public.js（首页·活动·登录） admin_core.js admin_manage.js
  js/components/     ui.js（弹窗·分页·空态） charts.js（手绘 SVG 折线/柱/环）
  vendor/            vue.global.prod.js（本地打包，不走 CDN）
alembic/versions/     0001 基线 → 0005 历史时间戳回拨为 UTC
```

请求链路：路由只做 HTTP 语义，业务规则集中在 `app/services/`，异常统一抛 `AppError` 并由 `app/core/errors.py` 渲染成 `{"error":{"code","message","details"}}`。
前端不引入构建工具：ES Modules + Vue 全局构建，运行时需要 CSP 中的 `'unsafe-eval'`（模板在浏览器内编译）；JSON-LD 用的是精确 SHA-256 哈希，内联脚本仅限这一段。

## 配置

所有配置来自环境变量或 `.env`，完整清单见 [.env.example](.env.example)。常改的几项：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./team_roll.db` | 只使用同步驱动，`+aiosqlite` 会被自动降级 |
| `ENVIRONMENT` | `dev` | `prod` 关闭 `/docs`、启用 HSTS 与 Secure Cookie |
| `SECRET_KEY` | 开发占位值 | 生产必须替换为随机值 |
| `SESSION_TTL_MINUTES` | `120` | 会话滑动有效期 |
| `LOGIN_RATE_LIMIT` / `ROLL_RATE_LIMIT` | `10/60s`、`12/60s` | 滑动窗口限流 |
| `TRUST_PROXY_HEADERS` | `false` | Nginx 等反代之后设为 `true` |
| `PUBLIC_BASE_URL` | 空 | canonical 与 sitemap 使用的对外地址 |
| `DATABASE_AUTO_MIGRATE` | `true` | 启动时自动 `alembic upgrade head` |

## 数据库与迁移

SQLite（WAL、外键开启、`busy_timeout=5000`），文件即数据，备份 = 复制 `team_roll.db`。

- 全新库：启动时依次执行 `0001`→`0005` 建出所有表并写入 `alembic_version`。
- 从 1.x 升级：检测到旧表但没有 `alembic_version` 时先 `stamp 0001` 再升级到 head，活动与 Roll 历史原样保留。
- 1.x 用本机时钟写的是裸时间，`0005` 按 `LEGACY_LOCAL_OFFSET_MINUTES`（默认 480）回拨成真实 UTC；如果原服务器时区不同，改这个值再迁移。
- 生产建议 `DATABASE_AUTO_MIGRATE=false`：此时版本落后或缺表会拒绝启动，需要先备份再手动 `python -m alembic upgrade head`。

## 部署

```bash
docker compose up -d --build      # 数据落在 team-roll-data 卷
```

镜像固定 **单 worker**：在线连接表和限流计数器都在进程内存里。需要多副本时前置粘性会话并改造共享状态。
Nginx 需要转发 WebSocket：

```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:8803;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_read_timeout 3600s;
}
```

健康检查：`GET /healthz`（数据库不可用时返回 503）。

### choyeon 服务器（choyeon-panel 纳管）

站点 <https://roll.choyeon.cc>，面板应用 `team-roll`（id 47，端口 8803）：

```bash
choyeonctl app deploy --id 47     # 拉 main 并重装依赖，随后重启 panel-team-roll.service
systemctl restart panel-team-roll
choyeonctl app logs --id 47
```

- 代码在 `/root/www/team_roll`，数据库在 `/var/lib/team_roll/team_roll.db`（刻意放在代码目录外，`git reset --hard` 碰不到）。
- 生产参数写在 `/root/www/team_roll/.panel.env`（0600，unit 以 `EnvironmentFile` 读取），首启建管理员用的 `BOOTSTRAP_ADMIN_*` 已在建号后删除。
- nginx 配置由面板生成在 `/etc/nginx/conf.d/panel-team-roll.conf`（已含 `Upgrade`/`Connection` 转发），证书由 certbot 装在同一文件；若重新 `choyeonctl app create` 会覆盖该文件，需要重跑 `certbot --nginx -d roll.choyeon.cc`。
- 面板的备份任务目前只覆盖 rosetta 的 PG，`/var/lib/team_roll` 还没进自动备份，需要另建 SQLite 备份任务。

## API 摘要

公开：`GET /api/v1/activities`（分页·搜索·状态）、`GET /api/v1/activities/{id}`、`GET /api/v1/activities/{id}/rolls`、`GET /api/v1/activities/{id}/stats`、`POST /api/v1/activities/{id}/rolls`（参与 Roll 点）。
鉴权：`POST /api/v1/auth/login|logout|password`、`GET /api/v1/auth/me`。
管理：`/api/v1/admin/dashboard`、`/admin/system`、`/admin/activities*`、`/admin/activities/{id}/rolls*`、`/admin/rolls/{id}*`、`/admin/admins*`、`/admin/sessions*`、`/admin/audit-logs`、`/admin/export/*`、`/admin/maintenance/*`。
实时：`GET /ws/{activity_id}`。
交互式文档（非生产环境）：<http://127.0.0.1:8803/docs>。

写操作要求 `X-CSRF-Token` 头，值与 `csrf_token` Cookie 双提交一致；会话 Cookie 为 HttpOnly。

## 从 1.x 迁移注意

- 旧的 `main.py`/`database.py`/`templates/` 已归档到 `legacy/`，不再被引用，可随时删除。
- 前端不再读取 `window` 上的一次性变量，Roll 记录一律经 JSON API 获取并作为文本渲染。
- 端口保持 `8803`，与原部署一致。
