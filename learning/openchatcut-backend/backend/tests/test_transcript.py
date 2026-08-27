"""文本稿词级编辑命令测试（12 种 + ms_to_frame）。"""
import pytest

from app.commands.actions import AddItem
from app.commands.base import Executor
from app.commands.transcript_actions import (
    CleanScript, ClearEdits, DeleteWords, FixTranscriptWord, PoolSetTranscription,
    RenameSpeaker, ReorderTrackItems, SetGapCap, SetItemTranscript,
    SetItemVariants, SetTranscriptPlayOrder, ToggleWord,
)
from app.domain.item import TimelineItem
from app.domain.media import MediaAsset
from app.domain.timeline import active_timeline, default_project
from app.domain.transcript import (
    TranscriptVariant, TranscriptVariantWord, TranscriptWord, ms_to_frame,
)


def make_item():
    words = (
        TranscriptWord(text="呃", startMs=0, endMs=200),
        TranscriptWord(text="大家好", startMs=200, endMs=800),
        TranscriptWord(text="那个", startMs=800, endMs=1000),
        TranscriptWord(text="欢迎", startMs=1000, endMs=1500),
    )
    return TimelineItem(id="i1", track="V1", startFrame=0, durationInFrames=90,
                        name="A", kind="video", transcript=words)


@pytest.fixture
def ex():
    e = Executor(default_project())
    e.execute(AddItem(make_item()))
    return e


def _find(ex, item_id="i1"):
    return next(i for i in active_timeline(ex.state).items if i.id == item_id)


def test_ms_to_frame():
    assert ms_to_frame(1000, 30) == 30
    assert ms_to_frame(0, 30) == 0
    assert ms_to_frame(500, 25) == 13


def test_set_item_transcript(ex):
    words = (TranscriptWord(text="新", startMs=0, endMs=100),)
    ex.execute(SetItemTranscript("i1", words, generation_id="g2"))
    it = _find(ex)
    assert it.transcript[0].text == "新"
    assert it.transcriptGenerationId == "g2"
    assert it.transcriptStale is False


def test_toggle_and_delete_words(ex):
    ex.execute(ToggleWord("i1", 0))
    assert _find(ex).deletedWordIdx == (0,)
    ex.execute(ToggleWord("i1", 0))   # 再切换回来
    assert _find(ex).deletedWordIdx == ()
    ex.execute(DeleteWords("i1", (0, 2)))
    assert _find(ex).deletedWordIdx == (0, 2)


def test_clean_script_removes_fillers(ex):
    ex.execute(CleanScript("i1", remove_fillers=True, silence_frames=10, cut_pad_frames=5))
    it = _find(ex)
    assert it.deletedWordIdx == (0, 2)   # "呃" 和 "那个"
    assert it.silenceFrames == 10
    assert it.cutPadFrames == 5


def test_fix_transcript_word(ex):
    ex.execute(FixTranscriptWord("i1", 1, "大家好呀"))
    assert _find(ex).transcript[1].text == "大家好呀"


def test_rename_speaker(ex):
    words = (TranscriptWord(text="a", startMs=0, endMs=100, speaker="A"),
             TranscriptWord(text="b", startMs=100, endMs=200, speaker="A"))
    e = Executor(default_project())
    e.execute(AddItem(TimelineItem(id="i1", track="V1", startFrame=0,
                                   durationInFrames=90, name="A", kind="video", transcript=words)))
    e.execute(RenameSpeaker("i1", "A", "B"))
    assert all(w.speaker == "B" for w in _find(e).transcript)


def test_set_variants_and_gap_cap_and_play_order(ex):
    v = TranscriptVariant(id="v1", lang="English", kind="translation", label="EN",
                          words=(TranscriptVariantWord(i=1, text="Hello everyone"),))
    ex.execute(SetItemVariants("i1", (v,)))
    assert _find(ex).variants[0].lang == "English"

    ex.execute(SetGapCap("i1", after_word_idx=1, max_ms=50))
    assert _find(ex).gapCapsMs == {"1": 50}

    ex.execute(SetTranscriptPlayOrder("i1", (1, 3, 0, 2)))
    assert _find(ex).transcriptPlayOrder == (1, 3, 0, 2)


def test_clear_edits(ex):
    ex.execute(DeleteWords("i1", (0, 2)))
    ex.execute(SetGapCap("i1", 1, 50))
    ex.execute(ClearEdits("i1"))
    it = _find(ex)
    assert it.deletedWordIdx == ()
    assert it.gapCapsMs is None
    assert it.transcriptPlayOrder is None


def test_reorder_track_items(ex):
    e = Executor(default_project())
    e.execute(AddItem(TimelineItem(id="i1", track="V1", startFrame=0, durationInFrames=90, name="A", kind="video")))
    e.execute(AddItem(TimelineItem(id="i2", track="V1", startFrame=90, durationInFrames=90, name="B", kind="video")))
    e.execute(ReorderTrackItems("V1", ("i2", "i1")))
    track_ids = [i.id for i in active_timeline(e.state).items if i.track == "V1"]
    assert track_ids == ["i2", "i1"]


def test_pool_set_transcription(ex):
    e = Executor(default_project())
    from app.commands.actions import AddAsset
    e.execute(AddAsset(MediaAsset(id="a1", name="clip.mp4", kind="video")))
    words = (TranscriptWord(text="hi", startMs=0, endMs=100),)
    e.execute(PoolSetTranscription("a1", words, source_revision="r1"))
    assert e.state.assets[0].transcript[0].text == "hi"
    assert e.state.assets[0].transcriptSourceRevision == "r1"
