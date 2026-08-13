"""在线源子系统纯函数/模型单元测试（不依赖外部网络）。"""

import pytest

from module.database.migrations import MIGRATIONS
from module.online_source.models import (
    MediaSource,
    OnlineSubject,
    Subscription,
)
from module.online_source.subscription import parse_subscription
from module.online_source.web_selector import (
    _json_path_select,
    _parse_episode_sort,
    to_python_regex,
)


def test_to_python_regex_named_group():
    assert to_python_regex(r"第\s*(?<ep>.+)\s*[话集]") == r"第\s*(?P<ep>.+)\s*[话集]"


def test_to_python_regex_keeps_lookbehind():
    # lookbehind 的 (?<=...)/(?<!...) 不能被误转
    assert to_python_regex(r"(?<=foo)bar(?<!baz)") == r"(?<=foo)bar(?<!baz)"


def test_parse_episode_sort():
    assert _parse_episode_sort("第01话", r"第\s*(?<ep>.+)\s*[话集]") == 1
    assert _parse_episode_sort("第 12 集", r"第\s*(?<ep>.+)\s*[话集]") == 12
    assert _parse_episode_sort("无集号", r"第\s*(?<ep>.+)\s*[话集]") is None


def test_json_path_select():
    data = [
        {"url": "https://a/1", "title": "甲"},
        {"link": "https://a/2", "name": "乙"},
    ]
    links = _json_path_select(data, "$[*]['url', 'link']")
    names = _json_path_select(data, "$[*]['title','name']")
    assert links == ["https://a/1", "https://a/2"]
    assert names == ["甲", "乙"]


def test_parse_subscription_minimal():
    raw = """
    {
      "exportedMediaSourceDataList": {
        "mediaSources": [
          {
            "factoryId": "web-selector",
            "version": 2,
            "arguments": {
              "name": "测试源",
              "searchConfig": {
                "searchUrl": "https://x.test/search?wd={keyword}",
                "subjectFormatId": "a",
                "selectorSubjectFormatA": {"selectLists": "div.list > a"},
                "channelFormatId": "no-channel",
                "selectorChannelFormatNoChannel": {"selectEpisodes": "#glist a"},
                "matchVideo": {"matchVideoUrl": "(https?://.+(m3u8|mp4))"}
              }
            },
            "unknownFutureField": {"ignored": true}
          }
        ]
      }
    }
    """
    sub = parse_subscription(raw)
    sources = sub.exportedMediaSourceDataList.mediaSources
    assert len(sources) == 1
    assert sources[0].arguments.name == "测试源"
    assert sources[0].arguments.searchConfig.searchUrl == "https://x.test/search?wd={keyword}"


def test_media_source_ignores_unknown_fields():
    src = MediaSource.model_validate(
        {"factoryId": "web-selector", "arguments": {"name": "x"}, "extra": 1}
    )
    assert src.arguments.name == "x"


def test_online_subject_model():
    subject = OnlineSubject(name="标题", url="https://x.test/detail/1")
    assert subject.model_dump() == {"name": "标题", "url": "https://x.test/detail/1"}


def test_migration_online_source_columns():
    """迁移 v25 为 bangumi 增加在线源绑定列。"""
    migration = next(m for m in MIGRATIONS if m.version == 25)
    joined = " ".join(migration.statements)
    for column in (
        "online_source",
        "online_subject_id",
        "online_channel",
        "online_update_time",
        "online_update_weekday",
    ):
        assert column in joined
