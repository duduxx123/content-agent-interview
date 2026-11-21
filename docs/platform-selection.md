# 平台接入选择（2026-11-19）

## 项目实际采用的接入方式：网页端客户端

`D:\blivedm` 基于 `xfgryujk/blivedm`，同时实现了网页端 `BLiveClient` 和官方开放平台 `OpenLiveClient` 两种模式。本项目复制了 `blivedm` 源码，并选择网页端 `BLiveClient`：它接收房间号和 aiohttp session，session 可携带用户 Cookie，不需要开放平台 access_key。

这里的“无需开放平台权限”特指使用该库的网页端弹幕连接方式；这与官方 OpenLive 接口是不同路径。客户端依赖 B 站网页端接口和 WebSocket 协议，项目代码只通过环境变量读取 Cookie，不保存凭据文件。

## 为什么代码仍保留独立适配层

`BilibiliLiveProvider` 将第三方库的消息对象转换为项目自己的 `LiveEvent`，Agent 模块不直接依赖 B 站字段。当前映射包括弹幕、礼物、上舰、醒目留言和进房互动，并附带发送者昵称（仅用于页面展示，不进入模型）。

新版房间使用 `SEND_GIFT_V2`，礼物数据是 base64 + protobuf 编码，项目已同时兼容 `SEND_GIFT` 和 `SEND_GIFT_V2`。`SEND_GIFT_V2` 只包含礼物名称、数量、价格等信息，不包含发送者昵称；因此这类礼物的页面会显示礼物内容，但不显示送礼人。消息事件不包含后台购物车点击率或成交转化率；在线人数可从房间信息接口获取，其他指标需要独立业务数据源。

## 来源与许可

复制来源：[xfgryujk/blivedm](https://github.com/xfgryujk/blivedm)。项目附带其 MIT License 文本，见 `THIRD_PARTY_LICENSES/blivedm-LICENSE.txt`。

## 其他平台对比

本次查询抖音官方公开资料未找到面向普通开发者、可直接订阅任意直播间弹幕的通用 API；公开直播 SDK 属于合作接入路径。对当前原型而言，复用本地 `blivedm` 网页端客户端是最短的实现路线。
