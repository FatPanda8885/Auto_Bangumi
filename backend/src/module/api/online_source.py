"""在线源搜索 / 集数 / 下载的 REST 端点。

在线源配置（aria2 RPC/secret/ffmpeg 等）随主配置段 ``online_source`` 走
``/config`` 现有端点（敏感字段掩码自动生效），这里只暴露源列表/导入、
SSE 搜索、集数与下载。
"""

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from module.database import Database, get_db
from module.downloader import AddResult
from module.online_source import OnlineSourceEngine, import_subscription, load_sources
from module.online_source.downloader import OnlineSourceDownloader
from module.security.api import get_current_user

router = APIRouter(prefix="/online_source", tags=["online_source"])


class OnlineImportRequest(BaseModel):
    url: str


class OnlineDownloadRequest(BaseModel):
    source: str
    episode_url: str
    bangumi_id: int
    season: int = 1
    episode: int | float
    media_type: str = "episode"  # "episode" | "movie" | "special"


@router.get("/sources", dependencies=[Depends(get_current_user)])
async def list_sources():
    """返回已导入的在线源摘要（不含选择器细节）。"""
    return [
        {
            "name": s.arguments.name,
            "icon": s.arguments.iconUrl,
            "description": s.arguments.description,
            "tier": s.arguments.tier,
        }
        for s in load_sources()
    ]


@router.post("/import", dependencies=[Depends(get_current_user)])
async def import_sources(body: OnlineImportRequest):
    """拉取并覆盖导入 css1.json 订阅列表。"""
    try:
        count = await import_subscription(body.url)
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"msg_zh": f"导入失败：{e}", "msg_en": f"Import failed: {e}"},
        )
    return {"imported": count}


@router.get("/search", dependencies=[Depends(get_current_user)])
async def search_online(source: str, keyword: str = Query(None)):
    """SSE 流式返回搜索结果（番剧条目）。"""
    if not keyword:
        return []
    engine = OnlineSourceEngine()

    async def event_generator():
        try:
            subjects = await engine.search(source, keyword)
        except ValueError as e:
            yield json.dumps({"error": str(e)}, separators=(",", ":"))
            return
        for subject in subjects:
            yield json.dumps(subject.model_dump(), separators=(",", ":"))

    return EventSourceResponse(content=event_generator())


@router.get("/episodes", dependencies=[Depends(get_current_user)])
async def get_episodes(source: str, subject: str):
    """返回某番剧详情页的播放路线与集数列表。"""
    engine = OnlineSourceEngine()
    try:
        channels = await engine.get_channels(source, subject)
    except ValueError as e:
        return JSONResponse(status_code=404, content={"msg_zh": str(e), "msg_en": str(e)})
    return [c.model_dump() for c in channels]


@router.post("/download", dependencies=[Depends(get_current_user)])
async def download_online(body: OnlineDownloadRequest, db: Database = Depends(get_db)):
    """解析片源直链并下载到指定番剧的媒体库目录。"""
    bangumi = await db.bangumi.search_id(body.bangumi_id)
    if bangumi is None:
        return JSONResponse(
            status_code=404,
            content={"msg_zh": "番剧不存在", "msg_en": "Bangumi not found"},
        )
    engine = OnlineSourceEngine()
    try:
        video = await engine.resolve(body.source, body.episode_url)
    except ValueError as e:
        return JSONResponse(status_code=404, content={"msg_zh": str(e), "msg_en": str(e)})
    if video is None:
        return JSONResponse(
            status_code=502,
            content={"msg_zh": "无法解析片源地址", "msg_en": "Failed to resolve video URL"},
        )
    result = await OnlineSourceDownloader().download(
        video, bangumi, body.season, body.episode, body.media_type
    )
    if result is AddResult.ADDED:
        return {"status": "added"}
    if result is AddResult.DUPLICATE:
        return {"status": "duplicate"}
    return JSONResponse(
        status_code=502,
        content={"msg_zh": "下载失败", "msg_en": "Download failed"},
    )
