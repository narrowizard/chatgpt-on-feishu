"""
GitLab 通道接入

@author Roo code & deepseek & narro
@Date 2025/1/26
"""

# -*- coding=utf-8 -*-
import json
import web
from channel.channel import Channel
from channel.gitlab.gitlab_message import GitlabMessage
from bridge.context import Context
from bridge.reply import Reply, ReplyType
from common.log import logger
from common.singleton import singleton
from config import conf
from common.expired_dict import ExpiredDict
from bridge.context import ContextType
from channel.chat_channel import ChatChannel, check_prefix


@singleton
class GitlabChannel(ChatChannel):
    def __init__(self):
        super().__init__()
        # 历史消息id暂存，用于幂等控制
        self.receivedMsgs = ExpiredDict(60 * 60 * 7.1)
        logger.info("[Gitlab] channel initialized")

    def handle_request(self, req):
        try:
            request = req.get_json()
            logger.debug(f"[Gitlab] receive request: {request}")
            
            # 1. 处理 GitLab Webhook 事件
            event_type = request.get("object_kind")
            if not event_type:
                return '{"success": false}'

            # 2. 消息接收处理
            # 幂等判断
            if self.receivedMsgs.get(request.get("object_attributes", {}).get("id")):
                logger.warning(f"[Gitlab] repeat msg filtered, event_id={request.get('object_attributes', {}).get('id')}")
                return '{"success": true}'
            self.receivedMsgs[request.get("object_attributes", {}).get("id")] = True

            # 构造 GitLab 消息对象
            gitlab_msg = GitlabMessage(request)
            if not gitlab_msg:
                return '{"success": true}'

            context = self._compose_context_from_controller(
                gitlab_msg.ctype,
                gitlab_msg.content,
                msg=gitlab_msg
            )
            if context:
                self.produce(context)
            logger.info(f"[Gitlab] query={gitlab_msg.content}, type={gitlab_msg.ctype}")
            return '{"success": true}'

        except Exception as e:
            logger.error(e)
            return '{"success": false}'

    def _compose_context_from_controller(self, ctype: ContextType, content, **kwargs):
        context = Context(ctype, content)
        context.kwargs = kwargs
        if "origin_ctype" not in context:
            context["origin_ctype"] = ctype

        cmsg: GitlabMessage = context["msg"]
        context["session_id"] = cmsg.from_user_id

        if ctype == ContextType.TEXT:
            context.type = ContextType.TEXT
            context.content = content.strip()

        return context

    def send(self, reply: Reply, context: Context):
        # GitLab Webhook 不需要主动发送消息
        pass


class GitlabController:
    # 类常量
    SUCCESS_MSG = '{"success": true}'
    FAILED_MSG = '{"success": false}'

    def GET(self):
        return "Gitlab service start success!"

    def POST(self):
        try:
            channel = GitlabChannel()

            request = json.loads(web.data().decode("utf-8"))
            logger.debug(f"[Gitlab] receive request: {request}")

            # 处理 GitLab Webhook 事件
            event_type = request.get("object_kind")
            if not event_type:
                return self.FAILED_MSG

            # 构造 GitLab 消息对象
            gitlab_msg = GitlabMessage(request)
            if not gitlab_msg:
                return self.SUCCESS_MSG

            context = self._compose_context(
                gitlab_msg.ctype,
                gitlab_msg.content,
                msg=gitlab_msg
            )
            if context:
                channel.produce(context)
            logger.info(f"[Gitlab] query={gitlab_msg.content}, type={gitlab_msg.ctype}")
            return self.SUCCESS_MSG

        except Exception as e:
            logger.error(e)
            return self.FAILED_MSG

    def _compose_context(self, ctype: ContextType, content, **kwargs):
        context = Context(ctype, content)
        context.kwargs = kwargs
        if "origin_ctype" not in context:
            context["origin_ctype"] = ctype

        cmsg: GitlabMessage = context["msg"]
        context["session_id"] = cmsg.from_user_id
        context["receiver"] = cmsg.other_user_id

        if ctype == ContextType.TEXT:
            context.type = ContextType.TEXT
            context.content = content.strip()

        return context