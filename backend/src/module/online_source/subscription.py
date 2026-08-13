"""在线源订阅的拉取、解析与持久化。

订阅列表（css1.json）本质是配置而非业务数据，因此与 ``search_provider.json``
一样以 JSON 文件落盘（``config/online_sources.json``），不进 SQLite。
"""

import logging
from pathlib import Path

from module.network.request_url import get_shared_client
from module.utils import json_config

from .models import MediaSource, Subscription, SubscriptionData

logger = logging.getLogger(__name__)

ONLINE_SOURCES_PATH = Path("config/online_sources.json")


def parse_subscription(text: str) -> Subscription:
    """把订阅 JSON 文本解析为 :class:`Subscription`。"""
    return Subscription.model_validate_json(text)


def load_sources() -> list[MediaSource]:
    """读取本地已导入的源列表。"""
    if not ONLINE_SOURCES_PATH.exists():
        return []
    try:
        raw = json_config.load(ONLINE_SOURCES_PATH)
        sub = Subscription.model_validate(raw)
    except Exception as e:  # 解析失败不阻断启动，仅告警
        logger.warning("Failed to load online sources: %s", e)
        return []
    return sub.exportedMediaSourceDataList.mediaSources


def save_sources(sources: list[MediaSource]) -> None:
    """把源列表写入本地文件。"""
    sub = Subscription(
        exportedMediaSourceDataList=SubscriptionData(mediaSources=sources)
    )
    ONLINE_SOURCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    json_config.save(ONLINE_SOURCES_PATH, sub.model_dump(mode="json"))


def sources_by_name(sources: list[MediaSource]) -> dict[str, MediaSource]:
    """按源名建立索引；重名时后者覆盖前者。"""
    return {s.arguments.name: s for s in sources if s.arguments.name}


async def fetch_subscription(url: str) -> Subscription:
    """拉取远端订阅 JSON。"""
    client = await get_shared_client()
    resp = await client.get(url, follow_redirects=True)
    resp.raise_for_status()
    return parse_subscription(resp.text)


async def import_subscription(url: str) -> int:
    """拉取并覆盖导入订阅列表，返回导入的源数量。

    覆盖式导入（与订阅列表语义一致）：用户的自定义源会被远端列表替换；
    如需保留自定义源请手动追加。
    """
    sub = await fetch_subscription(url)
    sources = sub.exportedMediaSourceDataList.mediaSources
    save_sources(sources)
    logger.info("Imported %s online sources from %s", len(sources), url)
    return len(sources)
