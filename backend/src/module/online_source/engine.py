"""在线源高层语义 API。

上层（API 路由 / 半自动追番循环）不关心 web-selector 细节，只调用
``search`` / ``get_channels`` / ``resolve`` 三个语义化方法。
"""

import logging

from .models import MediaSource, OnlineChannel, OnlineSubject, ResolvedVideo
from .subscription import load_sources, sources_by_name
from .web_selector import WebSelectorEngine

logger = logging.getLogger(__name__)


class OnlineSourceEngine:
    def __init__(self, sources: list[MediaSource] | None = None):
        self._sources = sources if sources is not None else load_sources()
        self._by_name = sources_by_name(self._sources)

    def list_sources(self) -> list[MediaSource]:
        return self._sources

    def get_source(self, name: str) -> MediaSource | None:
        return self._by_name.get(name)

    def _engine_for(self, source_name: str) -> WebSelectorEngine:
        source = self.get_source(source_name)
        if source is None:
            raise ValueError(f"Unknown online source: {source_name}")
        return WebSelectorEngine(source)

    async def search(self, source_name: str, keyword: str) -> list[OnlineSubject]:
        """在指定源搜索关键词，返回番剧条目列表。"""
        return await self._engine_for(source_name).search(keyword)

    async def get_channels(self, source_name: str, subject_url: str) -> list[OnlineChannel]:
        """解析番剧详情页，返回播放路线与集数列表。"""
        return await self._engine_for(source_name).get_channels(subject_url)

    async def resolve(self, source_name: str, episode_url: str) -> ResolvedVideo | None:
        """解析某一集的播放页，返回真实片源直链与防盗链头。"""
        return await self._engine_for(source_name).resolve(episode_url)
