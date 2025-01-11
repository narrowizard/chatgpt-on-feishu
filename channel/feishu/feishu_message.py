from bridge.context import ContextType
from channel.chat_message import ChatMessage
import json
import requests
from common.log import logger
from common.tmp_dir import TmpDir
from common import utils


class FeishuMessage(ChatMessage):
    def __init__(self, event: dict, is_group=False, access_token=None):
        super().__init__(event)
        msg = event.get("message")
        sender = event.get("sender")
        self.access_token = access_token
        self.msg_id = msg.get("message_id")
        self.create_time = msg.get("create_time")
        self.is_group = is_group
        msg_type = msg.get("message_type")

        if msg_type == "text":
            self.ctype = ContextType.TEXT
            content = json.loads(msg.get('content'))
            self.content = content.get("text").strip()
        elif msg_type == "post":
            self.ctype = ContextType.TEXT
            try:
                content = json.loads(msg.get('content'))
                logger.debug(f"[FeiShu] post message content: {content}")
                
                # 提取post消息中的文本内容
                text_parts = []
                content_list = content.get("content", [])
                if isinstance(content_list, list):
                    for content_item in content_list:
                        if isinstance(content_item, list):
                            for item in content_item:
                                if isinstance(item, dict) and item.get("tag") == "text":
                                    text = item.get("text", "")
                                    if text:
                                        text_parts.append(text)
                        elif isinstance(content_item, dict):
                            if content_item.get("tag") == "text":
                                text = content_item.get("text", "")
                                if text:
                                    text_parts.append(text)
                self.content = " ".join(text_parts).strip()
                logger.debug(f"[FeiShu] extracted post text: {self.content}")
            except Exception as e:
                logger.error(f"[FeiShu] parse post message error: {str(e)}")
                self.content = ""
        elif msg_type == "file":
            self.ctype = ContextType.FILE
            content = json.loads(msg.get("content"))
            file_key = content.get("file_key")
            file_name = content.get("file_name")

            self.content = TmpDir().path() + file_key + "." + utils.get_path_suffix(file_name)

            def _download_file():
                # 如果响应状态码是200，则将响应内容写入本地文件
                url = f"https://open.feishu.cn/open-apis/im/v1/messages/{self.msg_id}/resources/{file_key}"
                headers = {
                    "Authorization": "Bearer " + access_token,
                }
                params = {
                    "type": "file"
                }
                response = requests.get(url=url, headers=headers, params=params)
                if response.status_code == 200:
                    with open(self.content, "wb") as f:
                        f.write(response.content)
                else:
                    logger.info(f"[FeiShu] Failed to download file, key={file_key}, res={response.text}")
            self._prepare_fn = _download_file
        else:
            # Unsupported message type: Type:merge_forward
            raise NotImplementedError("Unsupported message type: Type:{} ".format(msg_type))

        self.parent_id = msg.get("parent_id")
        self.from_user_id = sender.get("sender_id").get("open_id")
        self.to_user_id = event.get("app_id")
        if is_group:
            # 群聊
            self.other_user_id = msg.get("chat_id")
            self.actual_user_id = self.from_user_id
            self.content = self.content.replace("@_user_1", "").strip()
            self.actual_user_nickname = ""
        else:
            # 私聊
            self.other_user_id = self.from_user_id
            self.actual_user_id = self.from_user_id
