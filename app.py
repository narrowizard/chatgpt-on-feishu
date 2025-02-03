# encoding:utf-8

import os
import signal
import sys
from flask import Flask, request

from channel import channel_factory
from common import const
from config import load_config
from plugins import *
import threading

app = Flask(__name__)
channels = {}


def sigterm_handler_wrap(_signo):
    old_handler = signal.getsignal(_signo)

    def func(_signo, _stack_frame):
        logger.info("signal {} received, exiting...".format(_signo))
        conf().save_user_datas()
        if callable(old_handler):  #  check old_handler
            return old_handler(_signo, _stack_frame)
        sys.exit(0)

    signal.signal(_signo, func)


def register_channel(channel_name: str):
    channel = channel_factory.create_channel(channel_name)
    if channel_name in ["wx", "wxy", "terminal", "wechatmp","web", "wechatmp_service", "wechatcom_app", "wework",
                        const.FEISHU, const.DINGTALK]:
        PluginManager().load_plugins()

    if conf().get("use_linkai"):
        try:
            from common import linkai_client
            threading.Thread(target=linkai_client.start, args=(channel,)).start()
        except Exception as e:
            pass
    
    # Register endpoint for this channel
    endpoint = f"/{channel_name.lower()}"
    app.add_url_rule(endpoint, endpoint, lambda: channel.handle_request(request), methods=["POST"])
    channels[channel_name] = channel


def run():
    try:
        # load config
        load_config()
        # ctrl + c
        sigterm_handler_wrap(signal.SIGINT)
        # kill signal
        sigterm_handler_wrap(signal.SIGTERM)

        # create channels
        channel_names = conf().get("channel_types", ["wx"])
        if isinstance(channel_names, str):
            channel_names = [channel_names]

        if "--cmd" in sys.argv:
            channel_names = ["terminal"]

        for channel_name in channel_names:
            if channel_name == "wxy":
                os.environ["WECHATY_LOG"] = "warn"
            register_channel(channel_name)

        # Start web server
        port = conf().get("port", 8080)
        app.run(host="0.0.0.0", port=port)
    except Exception as e:
        logger.error("App startup failed!")
        logger.exception(e)


if __name__ == "__main__":
    run()
