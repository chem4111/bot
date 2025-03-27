$ cat bot.py        
import os
import time
import botpy
from botpy import logging
from botpy.ext.cog_yaml import read
from botpy.message import C2CMessage, GroupMessage
import requests
import json
import re

# 读取配置文件
config = read(os.path.join(os.path.dirname(__file__), "config.yaml"))
API_ACCESS_TOKEN = config["coze_api_access_token"]
BOT_ID = config["coze_bot_id"]
API_BASE_URL = "https://api.coze.cn/open_api/v2/chat"

# 全局存储对话状态
conversation_settings = {
    "context_enabled": {},  # 上下文开关状态 {recipient_id: bool}
    "r1_enabled": {}  # 深度思考开关 {recipient_id: bool}
}

_log = logging.get_logger()


async def send_message(message, recipient_id, msg_id, content):
    """
    发送消息给用户，过滤消息中的 URL
    :param message: 消息对象
    :param recipient_id: 接收者 ID
    :param msg_id: 消息 ID
    :param content: 消息内容
    """
    content = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', content)
    send_func = message._api.post_group_message if isinstance(message, GroupMessage) \
        else message._api.post_c2c_message
    params = {
        "msg_type": 0,
        "msg_id": msg_id,
        "content": content
    }
    if isinstance(message, GroupMessage):
        params["group_openid"] = recipient_id
    else:
        params["openid"] = recipient_id
    return await send_func(**params)


class MyClient(botpy.Client):
    async def on_ready(self):
        """
        机器人准备就绪时触发
        """
        _log.info(f"「{self.robot.name}」准备就绪")

    async def on_group_at_message_create(self, message: GroupMessage):
        """
        处理群聊中 @ 机器人的消息
        :param message: 群消息对象
        """
        await self.process_message(message, message.group_openid, message.id)

    async def on_private_message_create(self, message: C2CMessage):
        """
        处理私聊消息
        :param message: 私聊消息对象
        """
        await self.process_message(message, message.author.user_openid, message.id)

    async def process_message(self, message, recipient_id, msg_id):
        """
        处理用户消息，调用 API 并解析响应
        :param message: 消息对象
        :param recipient_id: 接收者 ID
        :param msg_id: 消息 ID
        """
        content = message.content.strip()
        _log.info(f"收到消息: {content}")

        if await self.handle_commands(message, recipient_id, msg_id, content):
            return

        headers = {
            "Authorization": f"Bearer {API_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Host": "api.coze.cn",
            "Connection": "keep-alive"
        }

        payload = {
            "bot_id": BOT_ID,
            "user": recipient_id,
            "query": content,
            "stream": False,  # 非流式响应
            "custom_variables": {}
        }

        try:
            response = requests.post(API_BASE_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            # 打印原始响应数据
           # _log.info(f"原始响应数据: {json.dumps(data, indent=2)}")

            # 解析响应数据
            if "messages" in data:
                for msg in data["messages"]:
                    if msg["type"] == "answer":
                        answer = msg["content"]
                        await send_message(message, recipient_id, msg_id, answer)
                        _log.info(f"发送回复: {answer}")
                        _log.info(f"使用模型: {data.get('model', '未知模型')}")
                        _log.info(f"对话 ID: {data.get('conversation_id', '未提供')}")
                        break  # 只发送第一个 answer 类型消息
                else:
                    raise ValueError("未找到 answer 类型的回复消息")
            else:
                raise ValueError("响应中未包含 messages 字段")

        except Exception as e:
            _log.error(f"请求失败: {str(e)}")
            error_msg = str(e)
            error_msg = re.sub(r'http[s]?://\S+', '', error_msg)
            await send_message(message, recipient_id, msg_id, f"服务暂时不可用: {error_msg}")

    async def handle_commands(self, message, recipient_id, msg_id, content):
        """
        处理特殊命令
        :param message: 消息对象
        :param recipient_id: 接收者 ID
        :param msg_id: 消息 ID
        :param content: 消息内容
        :return: 是否处理了命令
        """
        if content == "我喜欢你":
            await send_message(message, recipient_id, msg_id, "我也喜欢你～")
            return True

        elif content.startswith("/context"):
            new_state = not conversation_settings["context_enabled"].get(recipient_id, False)
            conversation_settings["context_enabled"][recipient_id] = new_state
            status = "启用" if new_state else "关闭"
            await send_message(message, recipient_id, msg_id, f"上下文功能已{status}")
            return True

        elif content.startswith("/r1"):
            new_state = not conversation_settings["r1_enabled"].get(recipient_id, False)
            conversation_settings["r1_enabled"][recipient_id] = new_state
            status = "启用" if new_state else "关闭"
            await send_message(message, recipient_id, msg_id, f"深度思考模式已{status}")
            return True

        return False


if __name__ == "__main__":
    intents = botpy.Intents(public_messages=True, direct_message=True)
    client = MyClient(intents=intents, is_sandbox=True)
    client.run(appid=config["appid"], secret=config["secret"])
