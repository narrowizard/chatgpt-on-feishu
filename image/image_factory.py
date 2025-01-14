"""
image factory
"""


from bot.zhipuai.zhipuai_bot import ZHIPUAIBot


def create_image(image_type):
    """
    create an image instance
    :param image_type: image type code
    :return: image instance
    """
    if image_type == "zhipuai":
        return ZHIPUAIBot()
    
    raise RuntimeError("Unsupported image type: {}".format(image_type))