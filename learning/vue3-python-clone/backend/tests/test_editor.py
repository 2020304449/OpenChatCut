"""编辑核心单测：add / remove / set_duration / undo / redo。"""
from app.editor.commands import AddClip, RemoveClip, SetClipDuration
from app.editor.store import ProjectStore


def _n_clips(store: ProjectStore) -> int:
    return sum(len(t.clips) for t in store.state.tracks)


def test_default_timeline_has_two_empty_tracks():
    s = ProjectStore()
    assert [t.id for t in s.state.tracks] == ["v1", "c1"]
    assert _n_clips(s) == 0


def test_add_clip_to_video_track():
    s = ProjectStore()
    s.apply(AddClip(clip_id="c1x", label="A", kind="video", track_id="v1", start=0.0, duration=3.0))
    track = next(t for t in s.state.tracks if t.id == "v1")
    assert len(track.clips) == 1
    assert track.clips[0].label == "A"
    assert track.clips[0].duration == 3.0


def test_remove_clip():
    s = ProjectStore()
    s.apply(AddClip(clip_id="c1x", label="A", kind="video", track_id="v1", start=0.0, duration=3.0))
    s.apply(RemoveClip(clip_id="c1x"))
    assert _n_clips(s) == 0


def test_set_clip_duration():
    s = ProjectStore()
    s.apply(AddClip(clip_id="c1x", label="A", kind="video", track_id="v1", start=0.0, duration=3.0))
    s.apply(SetClipDuration(clip_id="c1x", duration=5.5))
    track = next(t for t in s.state.tracks if t.id == "v1")
    assert track.clips[0].duration == 5.5


def test_undo_redo():
    s = ProjectStore()
    s.apply(AddClip(clip_id="c1x", label="A", kind="video", track_id="v1", start=0.0, duration=3.0))
    s.apply(AddClip(clip_id="c2x", label="B", kind="video", track_id="v1", start=3.0, duration=3.0))
    assert _n_clips(s) == 2

    s.undo()
    assert _n_clips(s) == 1

    s.undo()
    assert _n_clips(s) == 0

    s.redo()
    assert _n_clips(s) == 1


def test_undo_on_empty_history_is_safe_noop():
    s = ProjectStore()
    assert s.undo() is None
    assert _n_clips(s) == 0
