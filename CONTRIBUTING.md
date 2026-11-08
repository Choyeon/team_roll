# 贡献指南

先说清楚预期，再动手，能省掉一轮无谓的 review。

## 环境

```bash
python -m venv .venv
.venv/Scripts/activate                     # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                       # Windows: copy .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8803 --reload
```

Python 版本下限是 3.11，镜像跑 3.12，CI 矩阵覆盖 3.12 与 3.13。依赖全部精确锁版本，改依赖请连 `requirements*.txt` 一起改。

## 门禁

提 PR 前这两条必须全绿：

```bash
python -m pytest
python -m ruff check app tests alembic
```

Ruff 配置在 `pyproject.toml`：`line-length = 120`，启用了 `E F W I UP B SIM ARG C4 RET`。

## 代码约定

- **后端**：路由只做参数校验与装配，业务放 `app/services/`；ORM 不越过 service 直接进模板或前端。
- **鉴权**：按能力（capability）判定，不要新增 `if role == ...` 的分支。能力有 `read` / `manage` / `manage_admins` / `dangerous` 四档。
- **前端**：Vue 3 全局构建 + 运行时模板字符串，**没有构建步骤**。不要引入需要打包的写法（SFC、TS、JSX、import 外部 npm 包）；新库请作为 `static/vendor/` 下的单文件放入并注明来源与许可证。
- **样式**：四层结构——`tokens.css` 是唯一允许出现原始颜色的地方，`base.css` 是元素默认，`components.css` 放原语，`views.css` 放具体页面。断点只用 `rem`（30 / 48 / 62 / 78），配合 `@media (pointer: coarse)`；不要写死像素断点。
- **文案与数字**：中文提示统一语气；数字一律过 `static/js/lib/format.js` 的 `number()` / `percent()` / `dateTime()`，不要在模板里手拼。
- **错误提示**：加载失败用 `ListCard` 的 `:error` + `@retry`（配 `tryLoad`），不要用过场 toast 盖住空白页。

## CSP 约束

响应头是 `default-src 'self'`、`script-src 'self' 'unsafe-eval'`、`style-src 'self'`、`frame-ancestors 'none'`。所以：

- 不要往 HTML 里塞内联 `<style>`，也不要用 `blob:` / `srcdoc` 加载脚本——线上会被拦。
- 内联事件属性（`onclick="..."`）不在白名单里，请一律用 `@click`。

## 界面验收

本项目主战场是手机竖屏。改完界面请至少在 375 / 820 / 1440 三档宽度确认无横向溢出：

```js
document.documentElement.scrollWidth - document.documentElement.clientWidth  // 应为 0
```

## 提 PR

- 一个 PR 只做一件事；重构与行为变更分开提交。
- 描述里写清怎么验证的，贴实际输出。
- 涉及数据库必须给 `downgrade`，并说明旧数据怎么备份。
- 不要提交 `.env`、数据库文件、口令或真实服务器信息。本地验证管理后台请用一份临时库副本：

```bash
DATABASE_URL=sqlite:///./_verify.db python -m uvicorn app.main:app --port 8899
```
