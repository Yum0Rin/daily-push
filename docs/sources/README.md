# 数据源说明

每个采集器输出结构如下，前端据此渲染。任何采集器失败时应返回
`{"error": "..."}` 而不是抛异常，配合 storage 的合并语义。

## 网易云日推 (sources/netease.py) → `netease` 字段

数组，每项：
```json
{
  "id": 123456, "name": "歌名", "artists": "歌手1 / 歌手2", "album": "专辑",
  "duration_ms": 217000, "pic": "封面图URL", "url": "官网歌曲页链接",
  "hot_comment": "最火热评文本（/comment/music，可为空字符串）",
  "comment_count": 4839,        // 评论总数（/comment/music 的 total）
  "favorite_count": 244451      // 收藏/红心数（/song/red/count 的 data.count）
}
```
数据来源可通过 config `netease.mode` 切换：
- `api`（本地现用，默认）：走 NeteaseCloudMusicApi（:3000 node 进程）+ Cookie，通过 `/recommend/songs` 和 `/comment/music`。
- `ncm-cli`（备用）：走官方开放平台接口，通过本机已登录的 `ncm-cli` 命令行获取每日推荐（`recommend daily`）与热评（`comment list-hot`），不需 Cookie，不需 node 代理。需先 `ncm-cli login` 登录一次。
  **断网规则**：ncm-cli 远端同步失败时会「使用本地缓存」返回过期数据，采集器检测到缓存回退即当作硬错误、拒绝使用，绝不拿昨天的推荐冒充当天。

> **2026-08-10 起本地已切回 `api` 模式**：`ncm-cli` 官方 CLI 目前（v0.1.6）
> 的命令树里**没有 `recommend` 子命令**（只有 play/search/playlist/queue 等），
> 代码调用 `ncm-cli recommend daily` 会报 `unknown command 'recommend'`，导致网易云采集
> 持续失败、页面只剩 B站/公众号。故本地回退到验证过的 `api`（Cookie + :3000 Node 代理）方案；
> 若未来 ncm-cli 支持日推命令可再切回。

Cookie 失效时（`api` 模式）：报错邮件主题会带 `ref=日期-来源`，直接**回复该邮件**、正文第一行贴新 Cookie
即可自动更新（云端更新 Secrets + 本地写回 config.json），详见 architecture.md「失败通知与 Cookie 自动修复」。
`ncm-cli` 登录失效只能手动 `ncm-cli login`，不会触发邮件自动修复。

每首歌额外请求一次热评，失败则置空，不影响整卡。

**评论数 / 收藏数**：`/comment/music` 同一次请求返回 `total`（评论总数）与 `hotComments`（热评）；
收藏数走 `/song/red/count`（`data.count`）。两者都写入结果（`comment_count` / `favorite_count`）。
为防风控，请求之间默认 sleep `netease.request_interval`（默认 0.3s）。

**评论数 / 收藏数过滤**（`netease.max_comments` 默认 10000，`netease.max_favorites` 默认 0=不限）：
任一项 **大于** 对应阈值即 **跳过并顺延下一首**，直到推满 `max_songs` 首（日推列表取尽仍不足则返回已有的几首）。

**封面 / 隐藏缓冲**：`pic` 统一规范成 `https://`（否则 https 页面或 CSP 会拦截 http 图）；
额外多取 `netease.reserve`（默认 3）条并标 `"hidden": true` 作**隐藏缓冲**，被忽略/过滤后可回填，前端不显示。

## B站关注UP (sources/bilibili.py) → `bilibili` 字段

数组，每项（一条视频）：
```json
{
  "title": "视频标题",
  "url": "https://www.bilibili.com/video/BVxxx",
  "author": "UP名",
  "created": 1754623229,
  "pic": "视频封面URL（动态 archive.cover，统一 https）"
}
```
数据来自「关注动态」接口（`x/polymer/web-dynamic/v1/feed/all?type=video`），
一次请求即可拿到最近投稿的视频（标题/链接/UP名/发布时间 `module_author.pub_ts`），
**不逐个访问 UP 空间**。按发布时间倒序，返回 `recent_days` 内（默认 1 天，含今日）的视频。

筛选与配置（策略存于跟踪文件 `settings.json`）：
- `bilibili.exclude`：按 UP 名**子串**排除（如「冷水先森无人声助眠」「哔哩哔哩课堂」等）。
- `bilibili.recent_days`：时间窗口天数，默认 1（从昨日 0 点起）。
- `bilibili.max_videos`：最多返回条数，默认 10。
- `bilibili.feed_pages`：动态接口最多翻页数，默认 2。
- `bilibili.reserve`：隐藏缓冲条数，默认 3（多取几条标 `hidden` 供回填，前端不显示）。
- `bilibili.sessdata`：登录 Cookie（动态接口需 WBI 签名 + 登录态）。

## ~~QQ群消息~~ / ~~微信群消息~~（已移除）

2026-08-07 起已删除 `sources/qq.py`、`sources/wechat.py`，collector 不再采集，
config 中的 `qq` 段与 wechat 群消息相关键已移除。历史数据仍在库中但不展示。

## 公众号推文 (sources/wechat_article.py) → `mp` 字段

数组，每项：
```json
{
  "title": "推文标题",
  "url": "http://mp.weixin.qq.com/s?...",   // 外链，点击跳转
  "author": "公众号账号名",
  "notify": false,                          // true=服务通知（取餐/优惠券/快递等）
  "time": "08-07 15:20",
  "timestamp": 1754623229
}
```
数据来源：微信解密后的 `biz_message_*.db`（公众号库，动态发现全部库，含今日推文），
提取 appmsg XML 的 `<title>`、`<url>` 与 `<mmreader><category><name>`（公众号名）。
排序：内容推文在前、通知类在后，各自按发布时间倒序，默认取 10 条
（`wechat.max_articles`）；额外多取 `wechat.reserve`（默认 3）条标 `"hidden": true`
作隐藏缓冲，被忽略后可回填，前端不显示。

**时间窗口**（config `wechat.mp_cutoff_hour`，默认 18）：窗口 = 最近一次「当天 18:00」之后 ~ 当前时刻。
即起始边界为 18:00（晚上采 → 前一天 18:00 起；早上采 → 前天 18:00 起），结束为当前时刻，
保证当天更晚的新文章也会被采到；重复推送由 collector 的跨天去重（cutoffs.json）兜底。

过滤与分类（策略存于跟踪文件 `settings.json`，键 `wechat.exclude_keywords` / `notify_keywords`，均有默认值）：
- `exclude_keywords`：**仅按 `author`（公众号名）子串匹配**排除，**不匹配标题**（避免误伤正常推文）。
- `notify_keywords`：标题命中即标记为通知类并排到列表下方，默认覆盖取餐/优惠券/快递等常见服务通知。
仅保存标题+链接+作者，不存正文。

## 小红书 → 已暂停（仅存档调研备忘）

`sources/xiaohongshu.py` 已删除，无采集模块。仅 `tools/xhs_console.txt` / `xhs_capture.txt`
保留当时的签名调研备忘，若日后重试可参考。**当前未接通。** 已摸清签名方案，但：

- 关注流 `homefeed_follow` 与推荐流 `homefeed_recommend` 均返回
  `code 300011「当前账号存在异常，请切换账号后重试」` —— 账号被风控。
- 用户决定**暂停**。若日后重试，先用 `tools/xhs_console.txt` 在浏览器验证，
  注意控制频率避免封号。

### 小红书签名备忘（后续可用）

- 需三个头：`x-s` / `x-t` / `x-s-common`，均由页面 `window._webmsxyw(path, params)`
  与 localStorage `b1`、cookie `a1` 组合生成。
- 纯 Python 的 pip `xhs` 库内建签名算法**已过时**（signType x2 / svn 56 是新版），
  直接调不通；必须以浏览器页面签名或本地执行新版 JS 为准。
- 方案：浏览器 Console 里 `window._webmsxyw` 签名 + fetch 请求（见
  `tools/xhs_console.txt`），或之后引入 `GenXsAndCommon_56.js` 类脚本在本地跑。
