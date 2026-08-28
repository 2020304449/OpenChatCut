"""C+D 服务层测试。"""
import builtins

from app.domain.captions import CaptionCue, CaptionsData
from app.domain.timeline import Timeline, default_project
from app.services.export import render_timeline
from app.services.fcpxml import timeline_to_fcpxml
from app.services.probe import probe_media
from app.services.subtitles import captions_to_srt


def test_captions_to_srt():
    c = CaptionsData(items=(CaptionCue(0, 60, "你好"), CaptionCue(60, 150, "世界")))
    srt = captions_to_srt(c, 30)
    assert "00:00:00,000 --> 00:00:02,000" in srt
    assert "你好" in srt
    assert "00:00:02,000 --> 00:00:05,000" in srt
    assert "世界" in srt


def test_timeline_to_fcpxml_structure():
    tl = Timeline(id="tl1", name="测试", fps=30, width=1920, height=1080)
    xml = timeline_to_fcpxml(tl)
    assert xml.startswith('<?xml version="1.0"')
    assert '<fcpxml version="1.9">' in xml
    assert '<format id="r1"' in xml
    assert '<project name="测试">' in xml


def test_probe_missing_file_graceful():
    r = probe_media("/nonexistent/path.mp4")
    assert r["ok"] is False


def test_export_empty_timeline_graceful():
    tl = default_project().timelines[0]
    r = render_timeline(tl, "out.mp4")
    assert r["ok"] is False


def test_transcribe_missing_dep_graceful(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("no faster-whisper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    from app.services.transcription import transcribe_audio

    r = transcribe_audio("/nonexistent.mp3")
    assert r["ok"] is False
    assert "not installed" in r["error"]


def test_fcpxml_escapes_xml_special_chars():
    from app.domain.item import TimelineItem
    tl = Timeline(
        id="tl1", name="a<b>&c", fps=30, width=1920, height=1080,
        items=(TimelineItem(id="i1", track="V1", startFrame=0, durationInFrames=30,
                            name="x<y>&z", kind="video"),),
    )
    xml = timeline_to_fcpxml(tl)
    assert 'name="a&lt;b&gt;&amp;c"' in xml
    assert 'name="x&lt;y&gt;&amp;z"' in xml


def test_export_run_error_path(monkeypatch):
    import subprocess
    from app.services import export as exp

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, "", "some ffmpeg error")

    monkeypatch.setattr(exp.subprocess, "run", fake_run)
    r = exp._run(["ffmpeg", "-y"], "/tmp/out.mp4")
    assert r["ok"] is False
    assert "error" in r


def test_render_video_builds_filter_graph(monkeypatch, tmp_path):
    """导出 filter 图应含：归一化 + xfade + overlay + 字幕 + amix。"""
    import subprocess
    from app.domain.item import TimelineItem
    from app.domain.transition import TransitionItem
    from app.services import export as exp

    tl = Timeline(
        id="tl1", name="t", fps=30, width=1920, height=1080,
        items=(
            TimelineItem(id="i1", track="V1", startFrame=0, durationInFrames=150, name="a", kind="video", src="a.mp4"),
            TimelineItem(id="i2", track="V1", startFrame=150, durationInFrames=210, name="b", kind="video", src="b.mp4"),
            TimelineItem(id="i4", track="V2", startFrame=60, durationInFrames=90, name="logo", kind="image", src="logo.png"),
            TimelineItem(id="i5", track="A1", startFrame=0, durationInFrames=540, name="bgm", kind="audio", src="bgm.mp3"),
        ),
        transitions=(TransitionItem(id="tr1", incomingItemId="i2", transType="crossfade", durationInFrames=15),),
        captions=CaptionsData(items=(CaptionCue(0, 90, "你好"),)),
    )

    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        (tmp_path / "out.mp4").write_text("")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(exp.shutil, "which", lambda _b: "/usr/bin/ffmpeg")
    monkeypatch.setattr(exp.subprocess, "run", fake_run)

    r = exp.render_timeline(tl, str(tmp_path / "out.mp4"))
    assert r["ok"] is True

    fc = " ".join(captured["cmd"])
    assert "scale=" in fc and "pad=" in fc   # 分辨率归一化
    assert "xfade" in fc                       # 转场 crossfade
    assert "overlay" in fc                     # 叠层
    assert "subtitles" in fc                   # 字幕烧录
    assert "amix" in fc                        # 音频混流


def test_render_video_no_main_v1_graceful(monkeypatch):
    """只有叠层/音频、没有 V1 视频时优雅失败。"""
    from app.domain.item import TimelineItem
    from app.services import export as exp

    monkeypatch.setattr(exp.shutil, "which", lambda _b: "/usr/bin/ffmpeg")

    tl = Timeline(
        id="tl1", name="t", fps=30, width=1920, height=1080,
        items=(TimelineItem(id="i4", track="V2", startFrame=0, durationInFrames=90,
                            name="logo", kind="image", src="logo.png"),),
    )
    r = exp.render_timeline(tl, "out.mp4")
    assert r["ok"] is False
    assert "V1" in r["error"]
