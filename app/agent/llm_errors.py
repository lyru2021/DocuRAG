"""定义模型输出不完整、拒绝和协议异常。"""


class LLMProtocolError(RuntimeError):
    """Provider 返回了无法安全解释的响应。"""


class LLMIncompleteError(LLMProtocolError):
    """模型响应未完成。"""


class LLMRefusalError(LLMProtocolError):
    """模型拒绝执行当前请求。"""