from bridge.context import ContextType
from channel.chat_message import ChatMessage
import json
import requests
from common.log import logger
from common.tmp_dir import TmpDir
from common import utils

def _download_file_helper(url, headers, params, file_path):
    response = requests.get(url=url, headers=headers, params=params)
    if response.status_code == 200:
        with open(file_path, "wb") as f:
            f.write(response.content)
    else:
        logger.info(f"[FeiShu] Failed to download file, url={url}, res={response.text}")


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
            self.ctype = ContextType.RICH_TEXT
            try:
                content = json.loads(msg.get('content'))
                logger.debug(f"[FeiShu] post message content: {content}")

                # 提取post消息中的文本内容和图片附件
                text_parts = []
                self.appendix = {}
                content_list = content.get("content", [])
                if isinstance(content_list, list):
                    for content_item in content_list:
                        if isinstance(content_item, list):
                            for item in content_item:
                                if isinstance(item, dict):
                                    if item.get("tag") == "text":
                                        text = item.get("text", "")
                                        if text:
                                            text_parts.append(text)
                                    elif item.get("tag") == "img":
                                        image_key = item.get("image_key")
                                        if image_key:
                                            self.appendix[image_key] = {
                                                "type": "image",
                                                "key": image_key,
                                                "file_path": TmpDir().path() + image_key + ".png"
                                            }
                                            text_parts.append(f"![{image_key}]")
                                            # 记录图片信息
                                            self._image_keys = list(self.appendix.keys())
                                            
                                            # 设置图片下载函数
                                            def _download_image():
                                                for image_key in self._image_keys:
                                                    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{self.msg_id}/resources/{image_key}"
                                                    headers = {
                                                        "Authorization": "Bearer " + self.access_token,
                                                    }
                                                    params = {
                                                        "type": "image"
                                                    }
                                                    _download_file_helper(url, headers, params, self.appendix[image_key]["file_path"])
                                            self._prepare_fn = _download_image
                        elif isinstance(content_item, dict):
                            if content_item.get("tag") == "text":
                                text = content_item.get("text", "")
                                if text:
                                    text_parts.append(text)
                self.content = " ".join(text_parts).strip()
                logger.debug(f"[FeiShu] extracted post text: {self.content}")
                logger.debug(f"[FeiShu] post message appendix: {self.appendix}")
            except Exception as e:
                logger.error(f"[FeiShu] parse post message error: {str(e)}")
                self.content = ""
                self.appendix = []
        elif msg_type == "file":
            self.ctype = ContextType.FILE
            content = json.loads(msg.get("content"))
            file_key = content.get("file_key")
            file_name = content.get("file_name")

            self.content = TmpDir().path() + file_key + "." + utils.get_path_suffix(file_name)

            def _download_file():
                url = f"https://open.feishu.cn/open-apis/im/v1/messages/{self.msg_id}/resources/{file_key}"
                headers = {
                    "Authorization": "Bearer " + access_token,
                }
                params = {
                    "type": "file"
                }
                _download_file_helper(url, headers, params, self.content)
            self._prepare_fn = _download_file
        elif msg_type == "image":
            self.ctype = ContextType.IMAGE
            content = json.loads(msg.get("content"))
            image_key = content.get("image_key")
            self.content = TmpDir().path() + image_key + ".png"
            logger.debug(f"[FeiShu] image_url: {self.content}")
            # 如果消息只有一张图, 则解释图片
            def _download_image():
                url = f"https://open.feishu.cn/open-apis/im/v1/messages/{self.msg_id}/resources/{image_key}"
                headers = {
                    "Authorization": "Bearer " + access_token,
                }
                params = {
                    "type": "image"
                }
                _download_file_helper(url, headers, params, self.content)
            self._prepare_fn = _download_image
        else:
            # Unsupported message type: Type:merge_forward
            raise NotImplementedError("Unsupported message type: Type:{} ".format(msg_type))

        self.parent_id = msg.get("parent_id")
        self.from_user_id = sender.get("sender_id").get("open_id")
        self.to_user_id = event.get("app_id")
        
        # 获取父消息
        self.parent_msg = None
        if self.parent_id and self.access_token:
            url = f"https://open.feishu.cn/open-apis/im/v1/messages/{self.parent_id}"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                items = response.json().get("data", {}).get("items", [])
                first_item = items[0]
                msg_type = first_item.get("msg_type")
                self.parent_msg = {
                    "text": "",
                    "appendix": [],
                }
                if msg_type == "merge_forward":
                    # 合并转发消息
                    for item in items[1:]:
                        item_type = item.get("msg_type")
                        if item_type == "image":
                            content_obj = json.loads(item.get("body", {}).get("content", "{}"))
                            image_key = content_obj.get("image_key")
                            self.parent_msg["text"] += f"\n![{image_key}]"
                            self.parent_msg["appendix"].append({
                                "type": "image",
                                "key": image_key,
                                "file_path": "TODO: download image",
                            })
                        else:
                            self.parent_msg["text"] += item.get("body", {}).get("content", "")
                else:
                    self.parent_msg["text"] = first_item.get("body", {}).get("content", "")
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
