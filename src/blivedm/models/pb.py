# -*- coding: utf-8 -*-
import dataclasses
import enum
from typing import *

import pure_protobuf.annotations as pb_anno
import pure_protobuf.message as pb_msg

try:
    Annotated
except NameError:
    from typing_extensions import Annotated  # Python < 3.9


class InteractWordV2MsgType(enum.IntEnum):
    Unknown = 0
    EnterRoom = 1
    Follow = 2
    ShareRoom = 3


@dataclasses.dataclass
class InteractWordV2UserBaseInfo(pb_msg.BaseMessage):
    face: Annotated[str, pb_anno.Field(2)] = ''


@dataclasses.dataclass
class InteractWordV2UserInfo(pb_msg.BaseMessage):
    base: Annotated[InteractWordV2UserBaseInfo, pb_anno.Field(2)] = dataclasses.field(default_factory=InteractWordV2UserBaseInfo)


@dataclasses.dataclass
class InteractWordV2(pb_msg.BaseMessage):
    uid: Annotated[int, pb_anno.Field(1)] = 0
    uname: Annotated[str, pb_anno.Field(2)] = ''
    # 为了防止加新枚举后不兼容，还是用int了
    # msg_type: Annotated[InteractWordV2MsgType, pb_anno.Field(5)] = InteractWordV2MsgType.Unknown
    msg_type: Annotated[int, pb_anno.Field(5)] = 0
    timestamp: Annotated[int, pb_anno.Field(7)] = 0
    uinfo: Annotated[InteractWordV2UserInfo, pb_anno.Field(22)] = dataclasses.field(default_factory=InteractWordV2UserInfo)


@dataclasses.dataclass
class SendGiftV2Gift(pb_msg.BaseMessage):
    """SEND_GIFT_V2 的 data.pb 中 gift 字段（字段号来自逆向结构）。"""

    gift_id: Annotated[int, pb_anno.Field(1)] = 0
    gift_name: Annotated[str, pb_anno.Field(2)] = ''
    num: Annotated[int, pb_anno.Field(3)] = 0
    gift_type: Annotated[int, pb_anno.Field(4)] = 0
    price: Annotated[int, pb_anno.Field(5)] = 0
    total_coin: Annotated[int, pb_anno.Field(6)] = 0
    coin_type: Annotated[str, pb_anno.Field(8)] = ''
    timestamp: Annotated[int, pb_anno.Field(10)] = 0
    action: Annotated[str, pb_anno.Field(18)] = ''


@dataclasses.dataclass
class SendGiftV2(pb_msg.BaseMessage):
    gift: Annotated[SendGiftV2Gift, pb_anno.Field(10)] = dataclasses.field(
        default_factory=SendGiftV2Gift
    )
