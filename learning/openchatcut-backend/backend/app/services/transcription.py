"""转写 ASR：faster-whisper 本地封装（对齐原版本地 whisper 路径）。

产出词级 TranscriptWord（毫秒时间戳）。faster-whisper 懒加载，未安装时
transcribe_audio 返回 {ok:False, error} 而非 import 崩溃。
"""
from __future__ import annotations

import os

from ..domain.transcript import TranscriptWord

_model = None
_model_name: str | None = None


def _get_model():
    global _model, _model_name
    name = os.environ.get("OPENCHATCUT_WHISPER_MODEL", "base")
    if _model is None or _model_name != name:
        from faster_whisper import WhisperModel
        _model = WhisperModel(name, device="cpu", compute_type="int8")
        _model_name = name
    return _model


def transcribe_audio(path: str) -> dict:
    """转写音频文件，返回词级毫秒 TranscriptWord 列表。

    成功：{"ok": True, "words": tuple[TranscriptWord, ...]}
    失败：{"ok": False, "error": str}（code="no-audio" 表示无音频，调用方应跳过而非报错）
    """
    try:
        model = _get_model()
    except ImportError:
        return {"ok": False, "error": "faster-whisper not installed (pip install faster-whisper)"}
    except Exception as exc:  # 模型文件损坏 / 下载失败等
        return {"ok": False, "error": f"whisper model load failed: {exc}"}

    try:
        segments, _info = model.transcribe(path, word_timestamps=True)
        words = tuple(
            TranscriptWord(
                text=(w.word or "").strip(),
                startMs=int(round(w.start * 1000)),
                endMs=int(round(w.end * 1000)),
            )
            for seg in segments
            for w in (seg.words or [])
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if not words:
        return {"ok": False, "error": "no-audio", "code": "no-audio"}
    return {"ok": True, "words": words}
