# 安全政策

## 报告漏洞

请走 GitHub 私有漏洞报告：<https://github.com/Choyeon/team_roll/security/advisories/new>。

不要开公开 issue、不要在 PR 描述里贴漏洞细节或利用代码。维护者通常会在 7 天内回复，公开披露请等补丁发布后再谈。

报告里请尽量给出：复现步骤、影响版本（`git rev-parse --short HEAD`）、触发所需的最小权限（哪个 capability）、以及你判断的危害。

## 这个项目已经把哪些当回事

- 口令用 pbkdf2_sha256 加盐存储，登录失败达 `MAX_FAILED_LOGINS` 后按 `LOCKOUT_MINUTES` 锁定。
- 会话是 HttpOnly Cookie，写操作再要求 `X-CSRF-Token` 头与之双提交一致。
- 按能力授权：`read` / `manage` / `manage_admins` / `dangerous`，后端每个管理路由独立校验，不依赖前端隐藏按钮。
- 每请求下发 CSP：`default-src 'self'`、`script-src 'self' 'unsafe-eval'`（外加 JSON-LD 的 hash）、`style-src 'self'`、`frame-ancestors 'none'`。
- 参与者名字等内容作为文本渲染，不拼接 HTML；`TRUST_PROXY_HEADERS` 明确控制来源 IP 取值，避免误信伪造头。
- 登录、Roll、发号都有限流窗口；WebSocket 每活动连接数有上限。

## 已知边界

- **单 worker 设计**：在线连接表与限流计数器都在进程内存里。多副本部署会削弱限流与在线数，需要前置粘性会话并把状态外置。
- **SQLite**：适合中小并发。要横向扩容请先换数据库，并重新评估发号去重的唯一约束与冲突重试。
- **管理员账号是内部角色**，不是面向公网的注册体系；请把站点放在 HTTPS 之后，`SECRET_KEY` 换成随机值，`BOOTSTRAP_ADMIN_*` 只在首次建号时存在、建完立刻删。
- **审计日志不防篡改**，它记录操作而不保证不可抵赖；有强合规需求请外接日志归档。
- 项目本身不做数据保留策略：历史 Roll 记录与审计会一直留着，删除只能由管理员显式操作。
