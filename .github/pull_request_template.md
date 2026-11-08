## 改了什么

一句话说明动机，再列关键点。跨层改动请按 后端 / 前端 / 样式 / 部署 分段。

## 影响面

- [ ] API 路由或 schema
- [ ] WebSocket 帧结构
- [ ] 数据库迁移（`alembic/versions/`）
- [ ] 鉴权、RBAC 或 CSRF
- [ ] 仅前端视图与样式

## 验证

把实际跑过的命令和结果贴在这里。

- [ ] `python -m pytest`
- [ ] `python -m ruff check app tests alembic`
- [ ] 界面改动已在手机上量过横向溢出（`scrollWidth - clientWidth == 0`）
- [ ] 新增/改动的文案与数字格式跟其他页面一致

## 迁移与回滚

涉及数据库时写明 `upgrade` / `downgrade` 怎么跑，以及旧数据是否需要备份。没有则写「无」。

## 安全

不要提交 `.env`、真实 `SECRET_KEY`、口令、会话 Cookie 或数据库文件；日志与截图里的敏感值先抹掉。
