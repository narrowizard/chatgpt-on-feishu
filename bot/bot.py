"""
Auto-replay chat robot abstract class
"""

from abc import ABC, abstractmethod
from typing import Optional
from bridge.context import Context
from bridge.reply import Reply


class IReply(ABC):
    """Bot回复能力接口"""
    @abstractmethod
    def reply(self, query: str, context: Optional[Context] = None) -> Reply:
        """
        bot auto-reply content
        :param query: 用户输入内容
        :param context: 上下文信息
        :return: 回复内容
        """
        pass


class IImageCreate(ABC):
    """Bot图片生成能力接口"""
    @abstractmethod
    def create_img(self, prompt: str, context: Optional[Context] = None) -> str:
        """
        根据文本生成图片
        :param prompt: 图片描述
        :param context: 上下文信息
        :return: 图片URL或文件路径
        """
        pass


class IImage2Text(ABC):
    """Bot图片转文字能力接口"""
    @abstractmethod
    def image2text(self, image_url: str, context: Optional[Context] = None) -> str:
        """
        将图片转换为文字描述
        :param image_url: 图片URL或文件路径
        :param context: 上下文信息
        :return: 图片内容描述
        """
        pass


class Bot(IReply, IImageCreate, IImage2Text):
    def reply(self, query: str, context: Optional[Context] = None) -> Reply:
        """
        bot auto-reply content
        :param query: 用户输入内容
        :param context: 上下文信息
        :return: 回复内容
        """
        raise NotImplementedError

    def create_img(self, prompt: str, context: Optional[Context] = None) -> str:
        """
        根据文本生成图片
        :param prompt: 图片描述
        :param context: 上下文信息
        :return: 图片URL或文件路径
        """
        raise NotImplementedError
    
    def reply_image(self, query: str, context: Optional[Context] = None) -> Reply:
        """
        bot auto-reply content
        :param query: 用户输入内容 
        :param context: 上下文信息
        :return: 回复内容
        """
        raise NotImplementedError

    def image2text(self, image_url: str, context: Optional[Context] = None) -> str:
        """
        将图片转换为文字描述
        :param image_url: 图片URL或文件路径
        :param context: 上下文信息
        :return: 图片内容描述
        """
        raise NotImplementedError

    def has_image_create(self) -> bool:
        """
        判断bot是否实现了图片生成能力
        :return: 如果实现了IImageCreate接口返回True，否则返回False
        """
        return not getattr(self.create_img, "__isabstractmethod__", False)
