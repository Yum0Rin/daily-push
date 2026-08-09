# 当前状态与已知问题

> 更新日期：2026-08-09

## 可用能力 ✅

- 网易云日推（5首）—— 稳定，含 top1 热评；`netease.mode=api`（NeteaseCloudMusicApi + Cookie）
- B站 UP动态 —— 走「关注动态」接口，1 次请求拉最近视频，快且轻
- 公众号推文（标题+链接+作者）—— 稳定，今日可取 ~10 条
- Flask 网页 + 开机自动采集（另有 07:30 兜底定时）
- 失败通知：本地/云端统一发邮件，主题标明环节与来源（不再桌面弹窗）
- 失败重试：采集每 5 分钟、推送每 60 秒，网络恢复后自动补上
- Cookie 自动修复：回复报错邮件贴新 cookie，云端轮询更新 Secrets + 本地自愈写回 config.json
- 存储：按日合并（失败不覆盖当天）；`push_date` 固定北京时间（UTC+8）

## 已知问题 / 限制

| 项 | 状态 | 说明 |
|----|------|------|
| 小红书 | ⛔ 暂停 | 关注流/推荐流接口均被风控 `300011`；签名已摸清但账号被标记；以后再说 |
| 网易云客户端播放 | 故障 | orpheus:// 本机无法唤起，只给官网歌曲页链接 |
| 双端同时触发 cookie-repair | 已知 | 本地与云端若同日同时 cookie 失效，可能双触发轮询（幂等，会重复回结果邮件） |

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

## 待办（用户可选）

- [ ] 小红书：换账号/解除风控后再接（用户表示以后再说）。
