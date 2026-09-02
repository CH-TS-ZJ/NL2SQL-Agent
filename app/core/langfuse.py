"""
Langfuse 观测与评估客户端

集中管理 Langfuse client 的惰性初始化与 LangChain 回调 handler 的创建。
通过配置开关 app_config.langfuse.enabled 控制是否启用，未启用时所有入口
返回 None，保证对既有链路零影响。

Langfuse SDK v4 以 public_key 为键做了底层资源单例（tracer / span exporter /
score 队列共享），因此同一进程内多次 Langfuse(...) 与 CallbackHandler() 都会
复用同一套导出资源，flush() 一次即可把 traces 与 scores 一起落盘。
"""

import threading

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from app.conf.app_config import app_config

# 进程内唯一 client，惰性创建，避免未启用时连初始化都不会触发
_client: Langfuse | None = None
_lock = threading.Lock()


def _enabled() -> bool:
    """是否真正启用 Langfuse：开关打开且公钥/私钥都已配置"""
    cfg = app_config.langfuse
    return bool(cfg.enabled and cfg.public_key and cfg.secret_key)


def get_client() -> Langfuse | None:
    """返回进程内复用的 Langfuse client，未启用时返回 None"""
    global _client
    if not _enabled():
        return None
    if _client is None:
        with _lock:
            if _client is None:
                cfg = app_config.langfuse
                _client = Langfuse(
                    public_key=cfg.public_key,
                    secret_key=cfg.secret_key,
                    host=cfg.host,
                )
    return _client


def build_handler() -> CallbackHandler | None:
    """创建一个 LangChain 回调 handler，未启用时返回 None

    调用方把返回值放进 graph.astream(config={"callbacks": [handler], ...})
    即可让一次图执行产出一条 trace（节点=span、LLM 调用=generation）。
    """
    return CallbackHandler() if get_client() is not None else None


def flush() -> None:
    """把待上传的 traces 与 scores 立即落盘，供短生命周期脚本退出前调用"""
    client = get_client()
    if client is not None:
        client.flush()
