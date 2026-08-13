"""在线源片源下载器。

在线源给的是片源直链（mp4/mkv/m3u8），qBittorrent 无法处理，因此使用
**独立的** aria2 RPC（``settings.online_source`` 配置段，与主下载器解耦）：
- mp4/mkv 直链 → aria2 ``addUri``；
- m3u8（HLS）→ ffmpeg 下载并封装为 mp4。

文件直接落到媒体库目录（``gen_save_path``，按标题/季命名），因为在线源
已知精确的标题/季/集，无需再经 Renamer 二次解析。
"""

import asyncio
import hashlib
import logging
import os
from urllib.parse import urlparse

from module.conf import settings
from module.database import Database
from module.downloader import AddResult
from module.downloader.client.aria2_downloader import Aria2Downloader
from module.downloader.path import gen_save_path, sanitize_path_fragment
from module.models import Bangumi

from .models import ResolvedVideo

logger = logging.getLogger(__name__)


def _is_hls(url: str) -> bool:
    return ".m3u8" in urlparse(url).path.lower()


def _ext_for(url: str) -> str:
    """根据直链推断目标文件扩展名；m3u8 由 ffmpeg 封装为 mp4。"""
    if _is_hls(url):
        return ".mp4"
    suffix = os.path.splitext(urlparse(url).path)[1].lower()
    return suffix if suffix in (".mp4", ".mkv") else ".mp4"


class OnlineSourceDownloader:
    """独立 aria2 下载后端（带客户端缓存，配置变更时重建）。"""

    def __init__(self):
        self._client: Aria2Downloader | None = None
        self._key: tuple[str, str] | None = None

    async def _get_client(self) -> Aria2Downloader:
        cfg = settings.online_source
        key = (cfg.aria2_rpc_url, cfg.aria2_secret)
        if self._client is None or self._key != key:
            if self._client is not None:
                await self._client.logout()
            self._client = Aria2Downloader(
                host=cfg.aria2_rpc_url, username="", password=cfg.aria2_secret
            )
            self._key = key
        return self._client

    @staticmethod
    def _split_headers(video: ResolvedVideo) -> tuple[str, str]:
        """返回 (referer, user_agent)，键名大小写不敏感。"""
        lower = {k.lower(): v for k, v in video.headers.items()}
        return lower.get("referer", ""), lower.get("user-agent", "")

    @staticmethod
    def _build_filename(
        bangumi: Bangumi, season: int, episode: int | float, media_type: str, url: str
    ) -> str:
        title = sanitize_path_fragment(bangumi.official_title or "Unknown") or "Unknown"
        ext = _ext_for(url)
        if media_type == "movie":
            return f"{title}{ext}"
        if isinstance(episode, float) and episode.is_integer():
            episode = int(episode)
        ep = f"0{episode}" if episode < 10 else str(episode)
        return f"{title} S{season:02d}E{ep}{ext}"

    async def _download_direct(
        self,
        client: Aria2Downloader,
        video: ResolvedVideo,
        save_path: str,
        filename: str,
    ) -> tuple[AddResult, str | None]:
        referer, ua = self._split_headers(video)
        options: dict = {"dir": save_path, "out": filename}
        header = []
        if referer:
            header.append(f"Referer: {referer}")
        if ua:
            header.append(f"User-Agent: {ua}")
        if header:
            options["header"] = header
        result, gid = await client.add_uri(video.url, options)
        if result is AddResult.DUPLICATE:
            gid = f"aria2:{hashlib.sha1(video.url.encode()).hexdigest()[:16]}"
        return result, gid

    async def _download_hls(
        self, video: ResolvedVideo, save_path: str, filename: str
    ) -> str | None:
        ffmpeg = settings.online_source.ffmpeg_path or "ffmpeg"
        target = os.path.join(save_path, filename)
        os.makedirs(save_path, exist_ok=True)
        referer, ua = self._split_headers(video)
        cmd = [ffmpeg, "-y", "-loglevel", "error"]
        if ua:
            cmd += ["-user_agent", ua]
        if referer:
            cmd += ["-headers", f"Referer: {referer}\r\n"]
        if video.cookies:
            cmd += ["-cookies", video.cookies]
        cmd += ["-i", video.url, "-c", "copy", target]
        logger.debug("Running ffmpeg: %s", " ".join(cmd))
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.error(
                "ffmpeg not found at %r; install ffmpeg or set ffmpeg_path", ffmpeg
            )
            return None
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = (stderr or b"").decode(errors="replace")[-400:]
            logger.error("ffmpeg failed (%s): %s", proc.returncode, err)
            return None
        if not os.path.exists(target):
            return None
        return f"ffmpeg:{hashlib.sha1(video.url.encode()).hexdigest()[:16]}"

    async def download(
        self,
        video: ResolvedVideo,
        bangumi: Bangumi,
        season: int,
        episode: int | float,
        media_type: str = "episode",
    ) -> AddResult:
        """把片源直链下载到该番剧的媒体库目录，返回新增/重复/失败。"""
        cfg = settings.online_source
        if not cfg.enable:
            logger.warning("Online-source download is disabled")
            return AddResult.FAILED
        if not cfg.aria2_rpc_url:
            logger.error("Online-source aria2 RPC URL is not configured")
            return AddResult.FAILED

        dedup_key = f"online:{bangumi.id}:{season}:{episode}"
        async with Database() as db:
            if await db.aria2.find_by_dedup_key(dedup_key):
                logger.debug("Online episode already downloaded: %s", dedup_key)
                return AddResult.DUPLICATE

        save_path = bangumi.save_path or gen_save_path(bangumi, root=cfg.save_path)
        filename = self._build_filename(bangumi, season, episode, media_type, video.url)
        target = os.path.join(save_path, filename)
        if os.path.exists(target):
            # 文件已就位但无去重记录（例如 ffmpeg 落盘后进程中断）：补记一条
            async with Database() as db:
                await db.aria2.upsert(
                    f"file:{hashlib.sha1(target.encode()).hexdigest()[:16]}",
                    bangumi_id=bangumi.id,
                    category="Bangumi",
                    dedup_key=dedup_key,
                )
            return AddResult.DUPLICATE

        client = await self._get_client()
        if not await client.auth():
            return AddResult.FAILED

        if _is_hls(video.url):
            gid = await self._download_hls(video, save_path, filename)
            result = AddResult.ADDED if gid else AddResult.FAILED
        else:
            result, gid = await self._download_direct(client, video, save_path, filename)

        if gid:
            async with Database() as db:
                await db.aria2.upsert(
                    gid,
                    bangumi_id=bangumi.id,
                    category="Bangumi",
                    dedup_key=dedup_key,
                )
            logger.info("Downloaded online episode: %s -> %s", filename, save_path)
        return result
