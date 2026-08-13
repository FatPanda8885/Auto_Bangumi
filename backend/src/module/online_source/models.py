"""在线源（CSS / Yamby 订阅格式）数据模型。

``css1.json`` 是「网页选择器配方」：每个源描述如何从某在线播放站搜索番剧、
列出集数与播放路线、并提取真实播放地址（mp4/mkv/m3u8）。本模块把该 JSON
结构解析为 Pydantic 模型，供 :mod:`module.online_source.web_selector` 消费。

所有模型 ``extra="ignore"``：订阅列表未来新增字段时不会导致解析失败。
"""

from pydantic import BaseModel, ConfigDict, Field

_IGNORE = ConfigDict(extra="ignore")


class SubjectSelectors(BaseModel):
    """搜索结果页的选择器（``subjectFormatId`` 三种变体之一）。

    - ``a``              → ``selectLists``：整块 ``<a>`` 列表，文本即标题。
    - ``indexed``        → ``selectNames`` + ``selectLinks``：标题与链接分离。
    - ``json-path-indexed`` → ``selectNames``/``selectLinks`` 为 JSONPath。
    """

    model_config = _IGNORE

    selectLists: str = ""
    selectNames: str = ""
    selectLinks: str = ""
    preferShorterName: bool = False


class ChannelSelectors(BaseModel):
    """剧集列表页的选择器（``channelFormatId`` 变体之一）。

    ``index-grouped`` 走带路线名的字段（``selectChannelNames`` +
    ``selectEpisodeLists``）；``no-channel`` 走扁平字段（``selectEpisodes``）。
    """

    model_config = _IGNORE

    selectChannelNames: str = ""
    matchChannelName: str = ""
    selectEpisodeLists: str = ""
    selectEpisodesFromList: str = ""
    selectEpisodeLinksFromList: str = ""
    selectEpisodes: str = ""
    selectEpisodeLinks: str = ""
    matchEpisodeSortFromName: str = ""


class MatchVideo(BaseModel):
    """从播放页提取真实视频地址的规则。"""

    model_config = _IGNORE

    enableNestedUrl: bool = False
    matchNestedUrl: str = ""
    matchVideoUrl: str = ""
    cookies: str = ""
    addHeadersToVideo: dict[str, str] = Field(default_factory=dict)


class SearchConfig(BaseModel):
    model_config = _IGNORE

    searchUrl: str = ""
    searchUseOnlyFirstWord: bool = False
    searchRemoveSpecial: bool = False
    searchUseSubjectNamesCount: int = 1
    subjectFormatId: str = "a"
    selectorSubjectFormatA: SubjectSelectors = Field(default_factory=SubjectSelectors)
    selectorSubjectFormatIndexed: SubjectSelectors = Field(
        default_factory=SubjectSelectors
    )
    selectorSubjectFormatJsonPathIndexed: SubjectSelectors = Field(
        default_factory=SubjectSelectors
    )
    channelFormatId: str = "no-channel"
    selectorChannelFormatFlattened: ChannelSelectors = Field(
        default_factory=ChannelSelectors
    )
    selectorChannelFormatNoChannel: ChannelSelectors = Field(
        default_factory=ChannelSelectors
    )
    filterByEpisodeSort: bool = True
    filterBySubjectName: bool = True
    matchVideo: MatchVideo = Field(default_factory=MatchVideo)
    defaultResolution: str = "1080P"


class SourceArguments(BaseModel):
    model_config = _IGNORE

    name: str = ""
    description: str = ""
    iconUrl: str = ""
    searchConfig: SearchConfig = Field(default_factory=SearchConfig)
    channelTiers: dict[str, int] = Field(default_factory=dict)
    tier: int = 0


class MediaSource(BaseModel):
    """单个在线源。``factoryId`` 目前只有 ``web-selector``。"""

    model_config = _IGNORE

    factoryId: str = ""
    version: int = 2
    arguments: SourceArguments = Field(default_factory=SourceArguments)


class SubscriptionData(BaseModel):
    model_config = _IGNORE

    mediaSources: list[MediaSource] = Field(default_factory=list)


class Subscription(BaseModel):
    """css1.json 的顶层结构。"""

    model_config = _IGNORE

    exportedMediaSourceDataList: SubscriptionData = Field(
        default_factory=SubscriptionData
    )


# ---------------------------------------------------------------------------
# 运行时结果类型（非订阅格式），供 engine 对外返回
# ---------------------------------------------------------------------------


class OnlineSubject(BaseModel):
    """搜索结果：一个番剧条目。"""

    name: str
    url: str


class OnlineEpisode(BaseModel):
    """单集：解析出的集号 + 集名 + 播放页链接。"""

    sort: int | None = None
    name: str = ""
    url: str = ""


class OnlineChannel(BaseModel):
    """一条播放路线：路线名 + 集数列表。"""

    name: str
    episodes: list[OnlineEpisode] = Field(default_factory=list)


class ResolvedVideo(BaseModel):
    """解析出的真实片源：直链 + 下载所需的防盗链头与 Cookie。"""

    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    cookies: str = ""
