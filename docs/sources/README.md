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

## B站首页推荐 (sources/bilibili.py 的 `BiliRecommendCollector`) → `bili_rec` 字段

数组，每项（一条视频）：
```json
{
  "title": "视频标题",
  "url": "https://www.bilibili.com/video/BVxxx",
  "author": "UP名",
  "bvid": "BVxxx",
  "created": 1793084368,
  "duration": 2682,
  "views": 361374,          // stat.view
  "likes": 92871,           // stat.like
  "ratio": 0.2571,          // likes / views
  "pic": "封面 URL（统一 https）"
}
```

接口 `GET x/web-interface/index/top/feed/rcmd`（`fresh_type=4&ps=20&fresh_idx=N`），
个性化首页推荐流，20 条/页，`fresh_idx` 递增翻页。**不需要 WBI 签名**，但需要 SESSDATA。
接口自带 `is_followed` 和 `stat.view/like`，所以「未关注」和「点赞率」都是本地算，不用额外请求。

筛选（策略存 `settings.json` 的 `bilibili.recommend`）：
- `min_views`（默认 50000）：播放量下限，`>` 比较。
- `min_like_ratio`（默认 0.07）：点赞率下限（`likes/views`），`>` 比较。
- `limit`（默认 6）：返回条数。
- `max_pages`（默认 8）：最多翻几页；凑不够就返回实际条数（每页间隔 1.2s）。
- `time_budget`（默认 20）：**单模块时间预算**，超时即停（已取到的照常返回）。
- 额外过滤：`goto != "av"`（直播/番剧）、`rcmd_reason.content` 含「广告/赞助」、
  作者命中 `bilibili.exclude`（与关注动态共用同一份屏蔽名单）。

**不按时间过滤**：推荐流会推老视频，跨天去重按 bvid（URL 固定）。
与「关注 UP 动态」是两个独立模块（`bilibili` / `bili_rec`），互不影响。

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

**封面回填 / 失效清理**：`python -m daily_push.cover_backfill [days] [interval]` 为历史补封面
（网易云 `http→https`；B站逐条查 `x/web-interface/view`；公众号读本地微信库），
并把返回 620xx / -404 / -403 的**失效 / 私密视频删除**；
同时把历史公众号**补到 `wechat.max_articles`（现 12/天）**；默认最近 7 天，`0`=全部，逐条 sleep 控频。
非正式推文（无封面）**保留**，前端显示占位封面。

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
  "pic": "封面图URL（appmsg thumburl/cover_16_9，统一 https）",
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
保证当天更晚的新文章也会被采到；重复推送由 collector 的**跨天去重**兜底：
采集时按历史已推 URL（`storage.pushed_urls`）过滤，一条只推一次（cutoffs.json 仅作时间兜底）。

过滤与分类（策略存于跟踪文件 `settings.json`，键 `wechat.exclude_keywords` / `notify_keywords`，均有默认值）：
- `exclude_keywords`：**仅按 `author`（公众号名）子串匹配**排除，**不匹配标题**（避免误伤正常推文）。
- `notify_keywords`：标题命中即标记为通知类并排到列表下方，默认覆盖取餐/优惠券/快递等常见服务通知。
仅保存标题+链接+作者，不存正文。

## 小红书推荐流 (sources/xiaohongshu.py) → `xhs` 字段

数组，每项：
```json
{
  "id": "6adcbeb40000000033013bff",
  "title": "……降这么多那别人之前的努力算什么",
  "url": "https://www.xiaohongshu.com/explore/<id>?xsec_token=<token>&xsec_source=pc_feed",
  "author": "辰羽",
  "likes": 31000,               // 由 "3.1万" 换算出的整数
  "likes_text": "3.1万",        // 原始文案，前端直接显示
  "collects": 1846,             // 收藏数（来自笔记详情；未开启藏赞比过滤时为 0）
  "collect_ratio": 0.0595,      // 收藏 / 点赞；详情请求失败时为 null
  "kind": "normal",             // normal=图文 / video=视频
  "pic": "封面 URL（取 cover.info_list 的 FD_PRV_WEBP）",
  "created": 1792659920         // 笔记 ID 前 8 位十六进制 = 发布时间戳
}
```

数据来自 PC 网页推荐流 `POST /api/sns/web/v1/homefeed`（`category=homefeed_recommend`），
20 条/页，`cursor_score` 翻页。请求需三个签名头 `x-s / x-t / x-s-common`，
由纯 Python 的 [`xhshow`](https://pypi.org/project/xhshow/) 生成（**不再依赖浏览器执行 JS**）。

登录态来源（按顺序）：
1. `config.json` 的 `xiaohongshu.cookie`（**整段 Cookie**，必须同时含 `a1=` 与 `web_session=`；
   只有 `web_session` 生成不了签名）——云端就用这条，值来自 GitHub Secret `XHS_COOKIE`；
2. 本机 **Firefox** 配置目录里已登录的小红书 Cookie —— 只读打开 `cookies.sqlite`
   （`mode=ro&immutable=1`），不复制文件、不外传。

> 本地：`config.json` 没配 Cookie 时自动回落到 Firefox。
> 云端（GitHub Actions）：没有浏览器，**必须**配 `XHS_COOKIE`，否则报「登录态缺失」并触发 cookie-repair 邮件流程。
> 只支持 Firefox 自动读取：Chrome 127+ 的 Cookie 是 App-Bound 加密，进程外无法解密。

筛选与配置：
- `xiaohongshu.min_likes`（策略，默认 5000）：点赞数下限。
- `xiaohongshu.min_collect_ratio`（策略，默认 0.1）：**藏/赞比**下限，`0` = 关闭。
- `xiaohongshu.limit`（config，默认 6）：返回条数上限（凑不满就返回实际条数）。
- `xiaohongshu.max_pages`（策略，默认 4）：最多翻几页（凑不够就返回实际条数）。
- `xiaohongshu.time_budget`（策略，默认 30）：**单模块时间预算**，超时即停，已取到的照常返回。
- `xiaohongshu.ad_keywords`（策略，默认见模块内 `DEFAULT_AD_KEYWORDS`）：命中标题或作者即丢弃。
- `xiaohongshu.exclude_keywords`（策略）：额外屏蔽词，命中标题或作者即丢弃。
- 每次翻页间隔 `request_interval`（默认 2 秒），失败重试 1 次；详情请求间隔 `detail_interval`（默认 1.5 秒）。

**没有浏览量，用「藏/赞比」代替**：小红书推荐流与笔记详情接口**都不返回浏览/播放数**
（`note_card` 里只有点赞、收藏、评论、分享；浏览量只有作者在创作中心能看到），
所以做不了 B站 那种「点赞/播放」。替代做法是只对**已过点赞阈值**的候选调一次
`POST /api/sns/web/v1/feed`（签名同推荐流）取 `collected_count`，按 `收藏/点赞` 过滤：
收藏相对点赞越高 = 越偏干货/可留存，纯情绪娱乐内容这个比值很低。
实测 18 条 5k+ 候选的分布：p25 = 0.040、中位 = 0.077、p75 = 0.129、最大 0.455；
阈值 0.1 约通过 1/3（尖子段），凑 6 条一般翻 3~4 页。

**30 秒预算怎么分配**：单次请求实测只要 0.1~0.3s，时间全在间隔上。小红书
翻页间隔 2.0s、详情间隔 1.5s（**不为了省时间把间隔调小，防账号被标记异常**），
所以 30 秒大约能覆盖 4 页 + 14~16 次详情，对应 4~6 条成品。
`time_budget` 是硬闸：快到点时不再等满间隔，到点立刻收尾，不会把整条流水线拖长。

> 代价：每条候选多 1 次详情请求，单次采集由约 12 秒增至约 60~70 秒（30~35 次请求）。
> 详情请求失败时按「比例未知」**放行**，不会因为一次失败把内容丢掉。
> 阈值设 `0` 可完全关闭该过滤，此时一次详情请求都不会发。
> 前端**只显示点赞数**：收藏数仅用于后台筛选藏/赞比，不展示；也不显示比值。

**广告判定是启发式**：推荐流返回的 `note_card` 只有 `cover / type / display_title / user /
interact_info`，**没有任何广告/赞助标记**（网页上的「赞助」角标不在此接口里），
所以只能靠标题+作者关键词过滤，会有漏判和误杀。要精确判定需逐条调笔记详情接口，
请求量 ×20，风控风险不值得。

**不按时间过滤**：推荐流会推几天前的老笔记，因此不套 `created` 时间窗口，
跨天去重靠「已推过的 note id」（从历史 URL 里提取）。

### 历史：8 月风控暂停 → 10 月恢复

2026-08 曾接通关注流/推荐流但账号被风控（`code 300011 当前账号存在异常`），
`sources/xiaohongshu.py` 被删除、只留 `tools/xhs_console.txt` 调研备忘。
2026-10-27 重新验证：`xhshow` 签名 + 本机登录态均可用，推荐流 `code 0` 正常返回，
账号风控已解除，故恢复接入。若再次遇到 300011，**停几天、别连续重试**。
