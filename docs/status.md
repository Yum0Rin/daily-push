# 当前状态与已知问题

> 更新日期：2026-09-12

## 可用能力 ✅

- 网易云日推（5首）—— 稳定，含 top1 热评；本地 `netease.mode=api`（Cookie+:3000 Node 代理），云端同用 `api`；`ncm-cli` 因无 `recommend` 命令已降为备用
- B站 UP动态 —— 走「关注动态」接口，1 次请求拉最近视频，快且轻
- 公众号推文（标题+链接+作者）—— 稳定，今日可取 ~10 条
- Flask 网页 + 开机自动采集（另有 07:30 兜底定时）
- 失败通知：本地/云端统一发邮件，主题标明环节与来源（不再桌面弹窗）
- 失败重试：采集每 5 分钟、推送每 60 秒，网络恢复后自动补上
- Cookie 自动修复：回复报错邮件贴新 cookie，云端轮询更新 Secrets + 本地自愈写回 config.json
- 存储：按日合并（失败不覆盖当天）；`push_date` 固定北京时间（UTC+8）
- 本地设置页 `/settings`：可视化编辑屏蔽名单 / 平台登录态（Cookie 更新 + 验证）/ 采集参数；
  仅本机、Host/Origin/CSRF 鉴权、密钥打码
- 配置分层：`settings.json`（非密钥策略，跟踪入库）与 `config.json`（密钥，gitignore），本地/云端同源
- 屏蔽词全量生效：保存后清理历史/今天 → 重发 Pages → 推送 `settings.json` 到 `code`（云端次日同源过滤）
- 单元测试 23 项（标准库 `unittest`，零新依赖）

## 已知问题 / 限制

| 项 | 状态 | 说明 |
|----|------|------|
| 小红书 | ⛔ 暂停 | 关注流/推荐流接口均被风控 `300011`；签名已摸清但账号被标记；以后再说 |
| 网易云客户端播放 | 故障 | orpheus:// 本机无法唤起，只给官网歌曲页链接 |
| 双端同时触发 cookie-repair | 已知 | 本地与云端若同日同时 cookie 失效，可能双触发轮询（幂等，会重复回结果邮件） |
| 云端同源 | 前提 | 要让 `settings.json` 在云端生效，`code` 分支必须是**含配置分层的新代码** |
| 设置页 | 仅本机 | PC 关机时无法访问；`push_time` / `port` 等改完需重启进程才生效 |
| 云端 Cookie | 可选同步 | 设置页勾「同步云端」→ `gh secret set`（需本机 `gh` 已登录）；否则走「回复邮件」或手动改 Secrets |

> QQ 群消息与微信群消息采集已移除（2026-08-07，用户不再需要）。

## 变更记录（较近）

1. 收集改为异步（POST /api/collect + 轮询 /api/collect/status，threaded=True）。
2. storage 合并语义：None/error 保留当天旧值。
3. 前端移除日期标签、QQ 卡片；新增公众号卡片；修复主题切换+持久化。
4. 新增 `wechat_article.py`（公众号）并接入 collector/storage(mp 列)/前端。
5. 小红书调研：签名方案已摸清（tools/xhs_console.txt），因风控暂停。
6. 公众号增强：提取作者（公众号名）、逐条展示；排除「演出余票监控/省教育厅/三福sanfu/高等教育出版社」；
   通知类（取餐/优惠券/快递等）置底弱化展示（config `exclude_keywords`/`notify_keywords`）。
7. B站逻辑改造：改走「关注动态」接口（`feed/all?type=video`），一次拉取最近视频的
   标题/链接/UP名/时间（`module_author.pub_ts`），不再逐个访问 UP 空间；按 UP 名排除
   （config `bilibili.exclude`），窗口 `recent_days`，上限 `max_videos`。
8. 前端：移除「立即采集」按钮与采集状态（每日开机自动采集，无需手动）；
   B站卡片改为与公众号一致的排版（标题链接 + 作者下一行 + 时间），去掉「最新：」前缀；
   summary 按钮顺序「推荐歌曲 | up动态 | 公众号推文」，点击滚动使卡片标题完整露出；
   标题改为「每日推送」，回到顶部按钮 emoji「🔝」。
9. 网易云：每首歌取 top1 热评（`/comment/music`），前端在歌手下一行用引号展示。
10. 运维：采集出错时在桌面生成 `collect_error.txt` 并自动弹出（每天最多一次），
    成功则清理；服务启动后自动打开浏览器；开机自启（Startup\DailyPush.vbs，隐藏窗口）。
11. 移除 QQ 与微信群采集：删除 `sources/qq.py`、`sources/wechat.py`，collector 只采
    netease/bilibili/mp；config 去掉 qq 段与 wechat 群消息相关键。
12. 2026-08-09：网易云切回 `api` 模式（NeteaseCloudMusicApi+Cookie，ncm-cli 留作备用）。
13. 2026-08-09：修复云端时区 bug（`push_date` 固定 UTC+8，解决 08-09 永不发布）。
14. 2026-08-09：失败通知统一改邮件（本地·采集/推送 + 云端），去掉桌面弹窗；
    采集/推送失败自动耐心重试（5 分钟 / 60 秒），网络恢复后自动补上（含 mp）。
15. 2026-08-09：新增「回复邮件自动更新 Cookie」：`cookie-repair.yml` 云端每 10 分钟
    轮询（最多 6h）→ 验证 → `gh secret set` 更新 Secrets；本地重试时读回复写回 config.json；
    报错邮件主题带 `ref=日期-来源` 标记。
16. 2026-08-09：网易云本地切回 `ncm-cli`（官方接口）并修复断网规则——ncm-cli 远端同步失败
    时的「本地缓存回退」现在被当作硬错误，不再用过期数据冒充当天；ncm-cli 登录失效提示手动
    `ncm-cli login`，邮件自动修 Cookie 仅对 `api` 模式生效。
17. 2026-08-09：公众号采集修复——①时间窗口改为「最近一次 18:00 之后 ~ 当前时刻」
    （`wechat.mp_cutoff_hour`，不再用固定 7 天），当天更晚的新文章也能采到；
    ②动态发现全部 `biz_message_*.db`，避免新库漏采；
    ③前端：云端静态站 mp 为空时显示权限说明卡片，不再整个消失。
18. 2026-08-10：本地网易云从 `ncm-cli` 切回 `api`——ncm-cli v0.1.6 命令树无
    `recommend` 子命令，`recommend daily` 报 `unknown command 'recommend'`，采集持续失败；
    `api` 模式（Cookie + :3000）验证可用。
19. 2026-09-12：配置分层——新增跟踪文件 `settings.json`（非密钥策略）与 `settings_store.py`
    （`默认 < settings.json < config.json`、schema 校验、原子写、`.bak` 备份、密钥打码）；
    `config.json` 只留密钥/机器相关；`.gitignore` 增加 `config.json.*`。
20. 2026-09-12：新增本地设置页 `/settings` 与 `/api/settings*`（登录状态检测/更新 Cookie、
    屏蔽名单、采集参数）；Host/Origin/CSRF token 鉴权、密钥只回打码值、设置页不参与静态站导出
    （`export_site.py` 剥离 `#settingsLink`，并有导出隔离测试）。
21. 2026-09-12：屏蔽名单全量生效——公众号改为**仅按作者（公众号名）子串**匹配、不匹配标题；
    设置页保存后异步执行 `purge_and_publish()`（清理历史/今天 → 重发 Pages）+
    `git_publish.commit_and_push_settings()`（只提交 `settings.json` 推到 `code`）；
    `make_cloud_config.py` 改从 `settings.json` 读策略、删硬编码名单；`_heavy_lock` 串行化采集与发布；
    修复仪表盘日期选择器 `«`/`»` 跨年 bug；新增 23 项单元测试。
22. 2026-09-12：本地 → 云端 Cookie 同步——新增 `daily_push/cloud_secrets.py`，设置页登录卡加「同步云端」
    勾选，保存 Cookie 时经本机 `gh secret set` 写入云端 Secrets（值走 stdin）；
    新增 `/api/settings/cloud-status`、`/api/settings/sync-cloud`；邮件 `cookie-repair` 流程**保留兜底**；
    `config.json` 可选 `github.token`（无 gh 登录时用）；「B站翻页数」标签改为「B站动态翻页数（每页上限约20条）」；
    测试增至 31 项。
23. 2026-09-12：仓库整理——`AGENTS.md` 加入 `.gitignore` 并从索引移除（仅本机、不再公开）；
    「忽略某博主/公众号」流程移入 [settings.md](settings.md)（含手动 CLI 步骤）；
    `AGENTS.md` 顶部增补「常驻约定（务必遵守）」与「命令由 AI 后台静默执行」说明；
    新增 gitignored 个人笔记 `AGENTS.local.md`。

## 待办（用户可选）

- [ ] 小红书：换账号/解除风控后再接（用户表示以后再说）。
