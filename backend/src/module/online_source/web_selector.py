"""web-selector 在线源爬取引擎。

css1.json 的每个源都是「网页选择器配方」：给定关键词去抓搜索结果页，用 CSS
选择器取标题与详情页链接，再抓详情页取「路线 + 集数列表」，最后从播放页用
正则提取真实片源（mp4/mkv/m3u8）。

与 RSS 不同，这里的「下载单元」是片源直链，因此本引擎只负责爬取与解析，
下载交由 :mod:`module.online_source.downloader`。
"""

import asyncio
import json
import logging
import re
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from module.conf import settings
from module.network.request_url import get_shared_client

from .models import (
    MediaSource,
    OnlineChannel,
    OnlineEpisode,
    OnlineSubject,
    ResolvedVideo,
)

logger = logging.getLogger(__name__)

# 同主机连续请求的节流（与 rss/engine.py 的 RSS_PER_HOST_DELAY 同思路，
# 避免抓取循环触发站点 429）。
_host_lock = asyncio.Lock()
_host_last: dict[str, float] = {}

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def to_python_regex(pattern: str) -> str:
    """把订阅里 .NET/Oniguruma 风格的 ``(?<name>...)`` 命名组转成 Python 的
    ``(?P<name>...)``，其余原样保留。

    只替换 ``(?<`` 后紧跟单词字符的命名组，避免误伤 ``(?<=...)``/``(?<!...)``
    这类 lookbehind。
    """
    return re.sub(r"\(\?<(\w)", r"(?P<\1", pattern)


def _compile(pattern: str) -> re.Pattern | None:
    if not pattern:
        return None
    try:
        return re.compile(to_python_regex(pattern))
    except re.error as e:
        logger.warning("Invalid regex in source definition: %r (%s)", pattern, e)
        return None


async def _rate_limit(host: str, delay: float) -> None:
    if delay <= 0:
        return
    async with _host_lock:
        now = time.monotonic()
        last = _host_last.get(host, 0.0)
        wait = delay - (now - last)
        _host_last[host] = now + max(wait, 0.0)
        if wait > 0:
            await asyncio.sleep(wait)


def _parse_cookies(cookie_str: str) -> dict[str, str]:
    """把 ``"a=1; b=2"`` 解析为 dict。"""
    cookies: dict[str, str] = {}
    for part in (cookie_str or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            if k:
                cookies[k] = v.strip()
    return cookies


async def _get_html(
    url: str, referer: str | None = None, cookies: dict[str, str] | None = None
) -> str | None:
    """抓取页面 HTML（复用共享 httpx 客户端，代理/超时配置随之生效）。"""
    client = await get_shared_client()
    headers = dict(_DEFAULT_HEADERS)
    if referer:
        headers["Referer"] = referer
    try:
        resp = await client.get(
            url, headers=headers, cookies=cookies, follow_redirects=True
        )
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning("Failed to fetch online-source page %s: %s", url, e)
        return None


def _json_path_select(data, path: str) -> list[str]:
    """极简 JSONPath，仅支持订阅里出现的 ``$[*]['k1','k2']`` 形态。

    对数组逐项取第一个存在的键；返回字符串列表。
    """
    match = re.fullmatch(r"\$\[\*\]\s*\[(.*)\]", (path or "").strip())
    if not match:
        return []
    keys = re.findall(r"['\"]([^'\"]+)['\"]", match.group(1))
    if not isinstance(data, list):
        return []
    result: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        for key in keys:
            if key in item and item[key] is not None:
                result.append(str(item[key]))
                break
    return result


def _parse_episode_sort(name: str, pattern: str) -> int | None:
    """从集名里按 ``matchEpisodeSortFromName`` 提取集号（阿拉伯数字）。"""
    compiled = _compile(pattern)
    if compiled is None:
        return None
    match = compiled.search(name or "")
    if not match:
        return None
    raw = match.groupdict().get("ep") or match.groupdict().get("sort")
    if raw is None:
        return None
    # 兼容「第01话」「第 1 集」：先整串取数字
    numbers = re.findall(r"\d+", str(raw))
    if not numbers:
        return None
    try:
        return int(numbers[0])
    except ValueError:
        return None


class WebSelectorEngine:
    """针对单个源定义的爬取引擎。"""

    def __init__(self, source: MediaSource):
        self.source = source
        self.config = source.arguments.searchConfig

    @property
    def delay(self) -> float:
        return getattr(settings.online_source, "request_delay", 2.0)

    def _prepare_keyword(self, keyword: str) -> str:
        kw = keyword.strip()
        if self.config.searchUseOnlyFirstWord:
            kw = kw.split()[0] if kw.split() else kw
        if self.config.searchRemoveSpecial:
            kw = re.sub(r"[\W_]+", "", kw)
        return kw

    # -- 搜索 -----------------------------------------------------------------

    async def search(self, keyword: str) -> list[OnlineSubject]:
        kw = self._prepare_keyword(keyword)
        if not kw or not self.config.searchUrl:
            return []
        url = self.config.searchUrl.replace("{keyword}", kw)
        await _rate_limit(urlparse(url).netloc, self.delay)
        html = await _get_html(url)
        if html is None:
            return []
        soup = BeautifulSoup(html, "html.parser")
        items = self._extract_subjects(soup, url)
        return [
            OnlineSubject(name=name, url=urljoin(url, href))
            for name, href in items
            if name and href
        ]

    def _extract_subjects(self, soup: BeautifulSoup, base_url: str) -> list[tuple[str, str]]:
        fmt = self.config.subjectFormatId.lower()
        if fmt == "a":
            sel = self.config.selectorSubjectFormatA
            anchors = soup.select(sel.selectLists) if sel.selectLists else []
            return [(a.get_text(strip=True), a.get("href", "")) for a in anchors]
        if fmt == "indexed":
            sel = self.config.selectorSubjectFormatIndexed
            names = [
                n.get_text(strip=True)
                for n in (soup.select(sel.selectNames) if sel.selectNames else [])
            ]
            links = [
                a.get("href", "")
                for a in (soup.select(sel.selectLinks) if sel.selectLinks else [])
            ]
            return list(zip(names, links))
        if fmt == "json-path-indexed":
            sel = self.config.selectorSubjectFormatJsonPathIndexed
            try:
                data = json.loads(soup.get_text() or "{}")
            except json.JSONDecodeError:
                return []
            links = _json_path_select(data, sel.selectLinks)
            names = _json_path_select(data, sel.selectNames)
            return list(zip(names, links))
        logger.warning("Unsupported subjectFormatId: %s", self.config.subjectFormatId)
        return []

    # -- 集数 / 路线 -----------------------------------------------------------

    async def get_channels(self, subject_url: str) -> list[OnlineChannel]:
        await _rate_limit(urlparse(subject_url).netloc, self.delay)
        html = await _get_html(subject_url)
        if html is None:
            return []
        soup = BeautifulSoup(html, "html.parser")
        if self.config.channelFormatId == "index-grouped":
            return self._channels_grouped(soup, subject_url)
        return self._channels_no_channel(soup, subject_url)

    def _channels_grouped(self, soup: BeautifulSoup, base_url: str) -> list[OnlineChannel]:
        sel = self.config.selectorChannelFormatFlattened
        channel_names = [
            self._match_channel_name(c.get_text(strip=True))
            for c in (soup.select(sel.selectChannelNames) if sel.selectChannelNames else [])
        ]
        episode_lists = soup.select(sel.selectEpisodeLists) if sel.selectEpisodeLists else []
        channels: list[OnlineChannel] = []
        for i, ch_name in enumerate(channel_names):
            episodes: list[OnlineEpisode] = []
            if i < len(episode_lists):
                box = episode_lists[i]
                anchors = box.select(sel.selectEpisodesFromList) if sel.selectEpisodesFromList else box.find_all("a")
                for a in anchors:
                    name = a.get_text(strip=True)
                    href = a.get("href", "")
                    episodes.append(
                        OnlineEpisode(
                            sort=_parse_episode_sort(name, sel.matchEpisodeSortFromName),
                            name=name,
                            url=urljoin(base_url, href),
                        )
                    )
            channels.append(OnlineChannel(name=ch_name, episodes=episodes))
        return channels

    def _channels_no_channel(self, soup: BeautifulSoup, base_url: str) -> list[OnlineChannel]:
        sel = self.config.selectorChannelFormatNoChannel
        episodes: list[OnlineEpisode] = []
        for a in (soup.select(sel.selectEpisodes) if sel.selectEpisodes else []):
            name = a.get_text(strip=True)
            href = a.get("href", "")
            episodes.append(
                OnlineEpisode(
                    sort=_parse_episode_sort(name, sel.matchEpisodeSortFromName),
                    name=name,
                    url=urljoin(base_url, href),
                )
            )
        return [OnlineChannel(name="默认", episodes=episodes)]

    def _match_channel_name(self, name: str) -> str:
        compiled = _compile(self.config.selectorChannelFormatFlattened.matchChannelName)
        if compiled is None:
            return name
        match = compiled.search(name)
        if match and match.groupdict().get("ch"):
            return match.groupdict()["ch"]
        return name

    # -- 播放地址 -------------------------------------------------------------

    async def resolve(self, episode_url: str) -> ResolvedVideo | None:
        mv = self.config.matchVideo
        await _rate_limit(urlparse(episode_url).netloc, self.delay)
        html = await _get_html(episode_url)
        if html is None:
            return None
        # 部分站点的播放页要先跳一层嵌套 URL 才到真正的播放页
        if mv.enableNestedUrl:
            nested = _compile(mv.matchNestedUrl)
            if nested is not None:
                match = nested.search(html)
                if match:
                    nested_url = match.group(0)
                    nested_html = await _get_html(
                        urljoin(episode_url, nested_url), referer=episode_url
                    )
                    if nested_html:
                        html = nested_html
        video_pattern = _compile(mv.matchVideoUrl)
        if video_pattern is None:
            return None
        match = video_pattern.search(html)
        if not match:
            return None
        video_url = urljoin(episode_url, match.group(0))
        headers = dict(mv.addHeadersToVideo)
        # 默认给一个浏览器 UA，源未显式指定时兜底
        headers.setdefault("User-Agent", _DEFAULT_HEADERS["User-Agent"])
        return ResolvedVideo(url=video_url, headers=headers, cookies=mv.cookies)
