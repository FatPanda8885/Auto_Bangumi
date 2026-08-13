"""在线源（在线播放站）搜索与下载子系统。

在线源给的是片源直链（mp4/mkv/m3u8）而非种子，qBittorrent 无法处理，
因此使用独立的 aria2 RPC 下载，m3u8 由 ffmpeg 封装。本包只负责订阅解析、
网页爬取与播放地址提取；下载见 :mod:`module.online_source.downloader`。
"""

from .engine import OnlineSourceEngine
from .models import (
    MediaSource,
    OnlineChannel,
    OnlineEpisode,
    OnlineSubject,
    ResolvedVideo,
)
from .subscription import (
    fetch_subscription,
    import_subscription,
    load_sources,
    save_sources,
    sources_by_name,
)

__all__ = [
    "OnlineSourceEngine",
    "MediaSource",
    "OnlineChannel",
    "OnlineEpisode",
    "OnlineSubject",
    "ResolvedVideo",
    "fetch_subscription",
    "import_subscription",
    "load_sources",
    "save_sources",
    "sources_by_name",
]
