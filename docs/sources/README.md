# 数据源说明

每个采集器输出结构如下，前端据此渲染。任何采集器失败时应返回
`{"error": "..."}` 而不是抛异常，配合 storage 的合并语义。

## 网易云日推 (sources/netease.py) → `netease` 字段

数组，每项：
```json
{
  "name": "歌名", "artists": "歌手", "album": "专辑",
  "id": "歌曲ID", "url": "官网歌曲页链接",
  "pic": "封面图URL", "duration": 217,
  "hot_comment": "最火热评文本（/comment/music，可为空字符串）"
}
```
数据来自 NeteaseCloudMusicApi（:3000，node 进程）。每首歌额外请求一次
`/comment/music` 取 top1 热评，失败则置空，不影响整卡。

## B站关注UP (sources/bilibili.py) → `bilibili` 字段

数组，每项（一条视频）：
```json
{
  "title": "视频标题",
  "url": "https://www.bilibili.com/video/BVxxx",
  "author": "UP名",
  "created": 1754623229
}
```
数据来自「关注动态」接口（`x/polymer/web-dynamic/v1/feed/all?type=video`），
一次请求即可拿到最近投稿的视频（标题/链接/UP名/发布时间 `module_author.pub_ts`），
**不逐个访问 UP 空间**。按发布时间倒序，返回 `recent_days` 内（默认 1 天，含今日）的视频。

筛选与配置：
- `bilibili.exclude`：按 UP 名排除（如「冷水先森无人声助眠」「哔哩哔哩课堂」等）。
- `bilibili.recent_days`：时间窗口天数，默认 1（从昨日 0 点起）。
- `bilibili.max_videos`：最多返回条数，默认 10。
- `bilibili.feed_pages`：动态接口最多翻页数，默认 2。
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
数据来源：微信解密后的 `biz_message_*.db`（公众号库，含今日推文），
提取 appmsg XML 的 `<title>`、`<url>` 与 `<mmreader><category><name>`（公众号名）。
排序：内容推文在前、通知类在后，各自按发布时间倒序，默认取 10 条
（config `wechat.max_articles` / `article_days`）。

过滤与分类（config `wechat.exclude_keywords` / `notify_keywords`，均有默认值）：
- `exclude_keywords`：标题或账号名命中即排除，默认 `演出余票监控 / 省教育厅 / 三福sanfu`。
- `notify_keywords`：标题命中即标记为通知类并排到列表下方，默认覆盖取餐/优惠券/快递等常见服务通知。
仅保存标题+链接+作者，不存正文。

## 小红书 (sources/xiaohongshu.py) → 预留

**当前未接通。** 已摸清签名方案（见 tools/xhs_console.txt），但：

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
