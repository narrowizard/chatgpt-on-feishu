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
                    "Authorization": "Bearer " + self.access_token,
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
                    "Authorization": "Bearer " + self.access_token,
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
                logger.debug(f"[FeiShu] parent message: {items}")
                msg_type = first_item.get("msg_type")
                self.parent_msg = {
                    "text": "",
                    "appendix": [],
                }
                if msg_type == "merge_forward":
                    # 合并转发消息, 需要合并所有消息内容
                    logger.debug(f"[FeiShu] merge_forward message: {items}")
                    for item in items[1:]:
                        res = self.resolve_msg(item)
                        self.parent_msg["text"] += res.get("text", "") + "\n"
                        self.parent_msg["appendix"].extend(res.get("appendix", []))
                else:
                    res = self.resolve_msg(first_item)
                    self.parent_msg["text"] = res.get("text")
                    self.parent_msg["appendix"] = res.get("appendix")
                # 下载附件(图片)
                for appendix in self.parent_msg.get("appendix", []):
                    if appendix.get("type") == "image":
                        url = f"https://open.feishu.cn/open-apis/im/v1/messages/{appendix.get('message_id')}/resources/{appendix.get('key')}"
                        headers = {
                            "Authorization": f"Bearer {self.access_token}",
                        }
                        params = {
                            "type": "image"
                        }
                        # https://open.feishu.cn/document/server-docs/im-v1/message/get-2?appId=cli_a5cac8e139f8d00d
                        # 暂不支持获取合并转发消息中的子消息、卡片消息中的资源文件。
                        _download_file_helper(url, headers, params, appendix.get("file_path"))
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
    
    # {'body': {'content': '{"image_key":"img_v3_02ip_beb56cd0-52a8-4d34-9388-6f0026523e6g"}'}, 'chat_id': 'oc_1db2c6250ca2935b9d68ab9261c63b60', 'create_time': '1737524321810', 'deleted': False, 'message_id': 'om_069dadebd6947fcdeb623dfaa0f55567', 'msg_type': 'image', 'sender': {'id': 'ou_d441fdf71e0abffc3936eb420e7b979f', 'id_type': 'open_id', 'sender_type': 'user', 'tenant_key': '2e524b52fecf165f'}, 'update_time': '1737524321810', 'updated': False}
    # returns {'text': '![img_v3_02ip_beb56cd0-52a8-4d34-9388-6f0026523e6g]', 'appendix': [{'type': 'image', 'key': 'img_v3_02ip_beb56cd0-52a8-4d34-9388-6f0026523e6g', 'message_id': 'om_069dadebd6947fcdeb623dfaa0f55567', 'file_path': '/tmp/img_v3_02ip_beb56cd0-52a8-4d34-9388-6f0026523e6g.png'}]}
    def resolve_msg(self, msg_item) -> dict:
        msg_type = msg_item.get("msg_type")
        res = {
            "text": "",
            "appendix": [],
        }
        content_str = msg_item.get("body", {}).get("content", "")
        if msg_type == "text":
            res["text"] = content_str
        elif msg_type == "image":
            content_obj = json.loads(content_str)
            res["text"] = f"![{content_obj.get('image_key')}]"
            res["appendix"].append({
                "type": "image",
                "key": content_obj.get("image_key"),
                "message_id": msg_item.get("message_id"),
                "file_path": TmpDir().path() + content_obj.get("image_key") + ".png",
            })
        elif msg_type == "post":
            content_obj = json.loads(content_str)
            content_list = content_obj.get("content", [])
            text_parts = []
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
                                    res["appendix"].append({
                                        "type": "image",
                                        "key": image_key,
                                        "message_id": msg_item.get("message_id"),
                                        "file_path": TmpDir().path() + image_key + ".png",
                                    })
                                    text_parts.append(f"![{image_key}]")
                elif isinstance(content_item, dict):
                    if content_item.get("tag") == "text":
                        text = content_item.get("text", "")
                        if text:
                            text_parts.append(text)
            res["text"] = " ".join(text_parts).strip()
        return res