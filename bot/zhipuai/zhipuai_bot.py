# encoding:utf-8

import base64
import time
from typing import Optional

import openai
from bot.bot import Bot, IImageCreate
from bot.zhipuai.zhipu_ai_session import ZhipuAISession
from bot.session_manager import SessionManager
from bridge.context import Context, ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from config import conf, load_config
from zhipuai import ZhipuAI


# ZhipuAI对话模型API
class ZHIPUAIBot(Bot, IImageCreate):
    def __init__(self):
        super().__init__()
        self.sessions = SessionManager(ZhipuAISession, model=conf().get("model") or "ZHIPU_AI")
        self.args = {
            "model": conf().get("zhipu_ai_model") or "glm-4",  # 对话模型的名称
            "temperature": conf().get("temperature", 0.9),  # 值在(0,1)之间(智谱AI 的温度不能取 0 或者 1)
            "top_p": conf().get("top_p", 0.7),  # 值在(0,1)之间(智谱AI 的 top_p 不能取 0 或者 1)
        }
        self.client = ZhipuAI(api_key=conf().get("zhipu_ai_api_key"))

    def reply(self, query, context=None):
        # acquire reply content
        if context.type == ContextType.TEXT:
            logger.info("[ZHIPU_AI] query={}".format(query))

            session_id = context["session_id"]
            reply = None
            clear_memory_commands = conf().get("clear_memory_commands", ["#清除记忆"])
            if query in clear_memory_commands:
                self.sessions.clear_session(session_id)
                reply = Reply(ReplyType.INFO, "记忆已清除")
            elif query == "#清除所有":
                self.sessions.clear_all_session()
                reply = Reply(ReplyType.INFO, "所有人记忆已清除")
            elif query == "#更新配置":
                load_config()
                reply = Reply(ReplyType.INFO, "配置已更新")
            if reply:
                return reply
            session = self.sessions.session_query(query, session_id)
            logger.debug("[ZHIPU_AI] session query={}".format(session.messages))

            api_key = context.get("openai_api_key") or openai.api_key
            model = context.get("gpt_model")
            new_args = None
            if model:
                new_args = self.args.copy()
                new_args["model"] = model
            # if context.get('stream'):
            #     # reply in stream
            #     return self.reply_text_stream(query, new_query, session_id)

            reply_content = self.reply_text(session, api_key, args=new_args)
            logger.debug(
                "[ZHIPU_AI] new_query={}, session_id={}, reply_cont={}, completion_tokens={}".format(
                    session.messages,
                    session_id,
                    reply_content["content"],
                    reply_content["completion_tokens"],
                )
            )
            if reply_content["completion_tokens"] == 0 and len(reply_content["content"]) > 0:
                reply = Reply(ReplyType.ERROR, reply_content["content"])
            elif reply_content["completion_tokens"] > 0:
                self.sessions.session_reply(reply_content["content"], session_id, reply_content["total_tokens"])
                reply = Reply(ReplyType.TEXT, reply_content["content"])
            else:
                reply = Reply(ReplyType.ERROR, reply_content["content"])
                logger.debug("[ZHIPU_AI] reply {} used 0 tokens.".format(reply_content))
            return reply
        elif context.type == ContextType.IMAGE_CREATE:
            ok, retstring = self.create_img(query, 0)
            reply = None
            if ok:
                reply = Reply(ReplyType.IMAGE_URL, retstring)
            else:
                reply = Reply(ReplyType.ERROR, retstring)
            return reply

        else:
            reply = Reply(ReplyType.ERROR, "Bot不支持处理{}类型的消息".format(context.type))
            return reply

    def reply_text(self, session: ZhipuAISession, api_key=None, args=None, retry_count=0) -> dict:
        """
        call openai's ChatCompletion to get the answer
        :param session: a conversation session
        :param session_id: session id
        :param retry_count: retry count
        :return: {}
        """
        try:
            # if conf().get("rate_limit_chatgpt") and not self.tb4chatgpt.get_token():
            #     raise openai.error.RateLimitError("RateLimitError: rate limit exceeded")
            # if api_key == None, the default openai.api_key will be used
            if args is None:
                args = self.args
            # response = openai.ChatCompletion.create(api_key=api_key, messages=session.messages, **args)
            response = self.client.chat.completions.create(messages=session.messages, **args)
            # logger.debug("[ZHIPU_AI] response={}".format(response))
            # logger.info("[ZHIPU_AI] reply={}, total_tokens={}".format(response.choices[0]['message']['content'], response["usage"]["total_tokens"]))

            return {
                "total_tokens": response.usage.total_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "content": response.choices[0].message.content,
            }
        except Exception as e:
            need_retry = retry_count < 2
            result = {"completion_tokens": 0, "content": "我现在有点累了，等会再来吧"}
            if isinstance(e, openai.error.RateLimitError):
                logger.warn("[ZHIPU_AI] RateLimitError: {}".format(e))
                result["content"] = "提问太快啦，请休息一下再问我吧"
                if need_retry:
                    time.sleep(20)
            elif isinstance(e, openai.error.Timeout):
                logger.warn("[ZHIPU_AI] Timeout: {}".format(e))
                result["content"] = "我没有收到你的消息"
                if need_retry:
                    time.sleep(5)
            elif isinstance(e, openai.error.APIError):
                logger.warn("[ZHIPU_AI] Bad Gateway: {}".format(e))
                result["content"] = "请再问我一次"
                if need_retry:
                    time.sleep(10)
            elif isinstance(e, openai.error.APIConnectionError):
                logger.warn("[ZHIPU_AI] APIConnectionError: {}".format(e))
                result["content"] = "我连接不到你的网络"
                if need_retry:
                    time.sleep(5)
            else:
                logger.exception("[ZHIPU_AI] Exception: {}".format(e), e)
                need_retry = False
                self.sessions.clear_session(session.session_id)

            if need_retry:
                logger.warn("[ZHIPU_AI] 第{}次重试".format(retry_count + 1))
                return self.reply_text(session, api_key, args, retry_count + 1)
            else:
                return result

    def create_img(self, query, retry_count=0, api_key=None, api_base=None):
        try:
            if conf().get("rate_limit_dalle"):
                return False, "请求太快了，请休息一下再问我吧"
            logger.info("[ZHIPU_AI] image_query={}".format(query))
            response = self.client.images.generations(
                prompt=query,
                n=1,  # 每次生成图片的数量
                model=conf().get("zhipu_ai_text_to_image_model") or "cogview-3",
                size=conf().get("image_create_size", "1024x1024"),  # 图片大小,可选有 256x256, 512x512, 1024x1024
                quality="standard",
            )
            image_url = response.data[0].url
            logger.info("[ZHIPU_AI] image_url={}".format(image_url))
            return True, image_url
        except Exception as e:
            logger.exception(e)
            return False, "画图出现问题，请休息一下再问我吧"

    def reply_image(self, query: str, context: Optional[Context] = None) -> Reply:
        success, retstring = self.create_img(query, 0)
        if success:
            return Reply(ReplyType.IMAGE_URL, retstring)
        else:
            return Reply(ReplyType.ERROR, retstring)
        
    def explain_img(self, images, text=None):
        """
        描述图片内容，支持多张图片和文本
        :param images: 图片文件路径列表
        :param text: 用户提供的文本描述或问题
        :return: (是否成功, 描述结果)
        """
        model = conf().get("zhipu_ai_image_to_text_model")
        try:
            # 处理多张图片
            image_contents = []
            for imageFile in images:
                with open(imageFile, 'rb') as img_file:
                    img_base = base64.b64encode(img_file.read()).decode('utf-8')
                    image_contents.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_base}"
                        }
                    })

            # 构建消息内容
            messages = [{
                "role": "user",
                "content": image_contents
            }]

            # 添加用户文本描述或问题
            if text:
                messages[0]["content"].append({
                    "type": "text",
                    "text": text
                })
            else:
                messages[0]["content"].append({
                    "type": "text",
                    "text": "请描述这些图片"
                })

            response = self.client.chat.completions.create(
                model=model,
                messages=messages
            )
            return True, response.choices[0].message.content
        except Exception as e:
            logger.exception(f"[ZHIPU_AI] explain_img error: {e}")
            return False, "图片描述失败，请稍后再试"

    def imageToText(self, imageFiles, text=None) -> Reply:
        """
        图片转文字，支持多张图片和文本
        :param imageFiles: 图片文件路径列表
        :param text: 用户提供的文本描述或问题
        :return: Reply对象
        """
        if isinstance(imageFiles, str):
            imageFiles = [imageFiles]
        succ, retstring = self.explain_img(imageFiles, text)
        if succ:
            return Reply(ReplyType.TEXT, retstring)
        else:
            return Reply(ReplyType.ERROR, retstring)