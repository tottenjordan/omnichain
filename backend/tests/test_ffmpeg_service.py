"""Tests for the FFmpeg assembly service (concat + master-audio mux/duck).

FFmpeg is not installed on the dev machine, so every test injects a fake
runner that captures the built argv without executing anything.
"""

import subprocess

import pytest

from omnichain.errors import AssemblyError
from omnichain.services.ffmpeg_service import FfmpegService


class _Recorder:
    """Fake runner: records each argv it is handed, runs nothing."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> None:
        self.commands.append(cmd)


def test_build_concat_command_has_filter_and_maps():
    svc = FfmpegService(runner=_Recorder())
    cmd = svc.build_concat_command(["a.mp4", "b.mp4", "c.mp4"], "out.mp4")

    assert cmd[0] == "ffmpeg"
    # every input passed with -i
    assert cmd.count("-i") == 3
    # filter graph concatenates 3 v+a pairs into one stream pair
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "concat=n=3:v=1:a=1[outv][outa]" in fc
    assert "[0:v:0][0:a:0]" in fc
    assert "[2:v:0][2:a:0]" in fc
    # explicit output stream mapping
    assert cmd[cmd.index("-map") + 1] == "[outv]"
    assert "[outa]" in cmd
    assert cmd[-1] == "out.mp4"


def test_concat_runs_command_and_returns_output():
    rec = _Recorder()
    svc = FfmpegService(runner=rec)
    result = svc.concat(["a.mp4", "b.mp4"], "final.mp4")

    assert result == "final.mp4"
    assert len(rec.commands) == 1
    assert rec.commands[0][-1] == "final.mp4"


def test_concat_empty_raises_assembly_error():
    svc = FfmpegService(runner=_Recorder())
    with pytest.raises(AssemblyError):
        svc.concat([], "out.mp4")


def test_build_mux_command_ducks_native_bed():
    svc = FfmpegService(runner=_Recorder())
    cmd = svc.build_mux_command("video.mp4", "master.mp3", "out.mp4", duck=True)

    fc = cmd[cmd.index("-filter_complex") + 1]
    # native bed is attenuated then mixed with the master track
    assert "volume=" in fc
    assert "amix=inputs=2" in fc
    # final audio is the mixed stream, video is copied through
    assert cmd[cmd.index("-map") + 1] == "0:v"
    assert "[aout]" in cmd


def test_build_mux_command_replace_uses_master_only():
    svc = FfmpegService(runner=_Recorder())
    cmd = svc.build_mux_command("video.mp4", "master.mp3", "out.mp4", duck=False)

    # no filter graph: master audio replaces native audio outright
    assert "-filter_complex" not in cmd
    assert cmd[cmd.index("-map") + 1] == "0:v"
    # second map selects the master input's audio
    maps = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "-map"]
    assert "1:a" in maps


def test_assemble_without_master_leaves_native_audio_intact():
    rec = _Recorder()
    svc = FfmpegService(runner=rec)
    result = svc.assemble(["a.mp4", "b.mp4"], "final.mp4", master_audio=None)

    assert result == "final.mp4"
    # only the concat runs; nothing touches or ducks the native audio
    assert len(rec.commands) == 1
    assert all("amix" not in " ".join(cmd) for cmd in rec.commands)


def test_assemble_with_master_concats_then_ducks():
    rec = _Recorder()
    svc = FfmpegService(runner=rec)
    result = svc.assemble(["a.mp4", "b.mp4"], "final.mp4", master_audio="master.mp3")

    assert result == "final.mp4"
    assert len(rec.commands) == 2
    # first concats, second muxes the master track with ducking
    assert "concat=n=2" in " ".join(rec.commands[0])
    assert "amix=inputs=2" in " ".join(rec.commands[1])


def test_default_runner_wraps_subprocess_failure(monkeypatch):
    def _boom(*_a, **_k):
        raise subprocess.CalledProcessError(1, "ffmpeg", stderr=b"broken pipe")

    monkeypatch.setattr(subprocess, "run", _boom)
    svc = FfmpegService()  # default runner shells out to ffmpeg
    with pytest.raises(AssemblyError):
        svc.concat(["a.mp4", "b.mp4"], "out.mp4")
