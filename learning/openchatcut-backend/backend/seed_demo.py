"""生成演示数据：多素材 / 多轨 / 字幕 / 转场 / 标记，写入默认 data/project-store.sqlite3。

用法（在 backend/ 目录下运行）：
    python seed_demo.py

随后启动后端（uvicorn app.main:app），前端即可看到完整的时间线可视化效果。
"""
from __future__ import annotations

from app.domain.captions import CaptionCue, CaptionsData
from app.domain.item import TimelineItem
from app.domain.marker import Marker
from app.domain.media import MediaAsset, MediaFolder
from app.domain.timeline import ProjectDoc, Timeline
from app.domain.transition import TransitionItem
from app.persist import save_project


def build() -> ProjectDoc:
    assets = (
        MediaAsset(id="a1", name="开场片头", kind="video", durationInFrames=90,
                   width=1920, height=1080, favorite=True),
        MediaAsset(id="a2", name="背景音乐", kind="audio", durationInFrames=270),
        MediaAsset(id="a3", name="Logo.png", kind="image", width=512, height=512, folderId="f1"),
    )
    folders = (MediaFolder(id="f1", name="品牌素材"),)

    items = (
        TimelineItem(id="i1", track="V1", startFrame=0, durationInFrames=90,
                     name="开场", kind="video", sourceAssetId="a1"),
        TimelineItem(id="i2", track="V1", startFrame=90, durationInFrames=90,
                     name="正片", kind="video"),
        TimelineItem(id="i3", track="V2", startFrame=30, durationInFrames=60,
                     name="Logo叠层", kind="image", sourceAssetId="a3"),
        TimelineItem(id="i4", track="A1", startFrame=0, durationInFrames=270,
                     name="BGM", kind="audio", sourceAssetId="a2", volume=0.5),
    )
    transitions = (TransitionItem(id="tr1", incomingItemId="i2", transType="crossfade",
                                  durationInFrames=15),)
    captions = CaptionsData(enabled=True, items=(
        CaptionCue(startFrame=0, endFrame=60, text="大家好"),
        CaptionCue(startFrame=60, endFrame=150, text="欢迎来到"),
    ))
    markers = (
        Marker(id="m1", name="高潮点", frame=120, color="#f59e0b"),
        Marker(id="m2", name="重点段落", startFrame=30, endFrame=150, color="#3b82f6"),
    )

    tl = Timeline(id="tl1", name="宣传片", fps=30, width=1920, height=1080,
                  items=items, transitions=transitions, captions=captions, markers=markers,
                  trackOrder=("V2", "V1", "A1", "A2"))
    return ProjectDoc(version=1, assets=assets, mediaFolders=folders,
                      timelines=(tl,), activeTimelineId="tl1")


if __name__ == "__main__":
    save_project(build())
    print("已写入 data/project-store.sqlite3")
