"""FCPXML 工程导出：Timeline → FCPXML 纯文本（最小实现，对齐 src/export/fcpxml.ts 契约）。

首版覆盖视频轨片段（按 startFrame 排序 + gap 填充），转场/音频/多机位完整度延后。
"""
from __future__ import annotations

from xml.sax.saxutils import escape as xml_escape

from ..domain.timeline import Timeline


def _sec(frame: int, fps: int) -> str:
    return f"{frame}/{fps}s"


def _frame_duration(fps: int) -> str:
    return f"100/{fps * 100}s"


def timeline_to_fcpxml(tl: Timeline) -> str:
    fps = tl.fps or 30
    width = tl.width or 1920
    height = tl.height or 1080

    video_items = sorted(
        (i for i in tl.items if i.kind not in ("audio",)),
        key=lambda x: x.startFrame,
    )

    resources: list[str] = [
        f'<format id="r1" name="FFVideoFormat{height}p{fps}" '
        f'frameDuration="{_frame_duration(fps)}" width="{width}" height="{height}" '
        f'colorSpace="1-1-1 (Rec. 709)"/>'
    ]
    spine: list[str] = []
    cursor = 0

    for idx, item in enumerate(video_items, start=1):
        aid = f"a{idx}"
        if cursor < item.startFrame:
            spine.append(f'<gap name="Gap" offset="{_sec(cursor, fps)}" '
                         f'duration="{_sec(item.startFrame - cursor, fps)}" start="3600s"/>')
        if item.src:
            resources.append(
                f'<asset id="{aid}" name="{xml_escape(item.name)}" '
                f'duration="{_sec(item.durationInFrames, fps)}" hasVideo="1" '
                f'format="r1" src="{xml_escape(item.src)}"/>'
            )
        else:
            resources.append(
                f'<asset id="{aid}" name="{xml_escape(item.name)}" '
                f'duration="{_sec(item.durationInFrames, fps)}" hasVideo="1" format="r1"/>'
            )
        spine.append(
            f'<asset-clip ref="{aid}" offset="{_sec(item.startFrame, fps)}" '
            f'duration="{_sec(item.durationInFrames, fps)}" name="{xml_escape(item.name)}" '
            f'start="0s"/>'
        )
        cursor = item.startFrame + item.durationInFrames

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE fcpxml>\n'
        '<fcpxml version="1.9">\n'
        '  <resources>\n'
        + "\n".join(f"    {r}" for r in resources) +
        "\n  </resources>\n"
        '  <library>\n'
        '    <event name="OpenChatCut">\n'
        f'      <project name="{xml_escape(tl.name)}">\n'
        '        <sequence format="r1" duration="' + _sec(cursor, fps) + '" '
        'tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">\n'
        '          <spine>\n'
        + "\n".join(f"            {s}" for s in spine) +
        "\n          </spine>\n"
        "        </sequence>\n"
        "      </project>\n"
        "    </event>\n"
        "  </library>\n"
        "</fcpxml>\n"
    )
