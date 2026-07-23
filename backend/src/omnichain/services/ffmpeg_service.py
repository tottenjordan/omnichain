"""FFmpeg assembly: concatenate approved clips and mux a master audio track.

Omni Flash clips carry native synced audio, but a user's own master track
cannot be fed to the model (audio-reference upload is unsupported). So the
master is overlaid here at assembly time. Two mux modes:

* **duck** (default) — the clips' native music bed is attenuated and mixed
  *under* the master track, so dialogue/SFX from the clips stay audible while
  the master dominates.
* **replace** — the native audio is dropped entirely in favour of the master.

If no master track is supplied, :meth:`FfmpegService.assemble` simply concats
the clips and leaves their native audio untouched.

FFmpeg runs via :mod:`subprocess`; the command builders are pure so they can be
asserted without a real ffmpeg binary (which is not present in dev/test).
"""

from __future__ import annotations

import functools
import logging
import subprocess
from typing import TYPE_CHECKING

from omnichain.errors import AssemblyError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

logger = logging.getLogger("omnichain.ffmpeg")

# Attenuation applied to the clips' native music bed when ducking under the
# master track. 0.25 ≈ -12 dB: audible but clearly subordinate.
_DUCK_VOLUME = 0.25


def _default_runner(cmd: list[str]) -> None:
    """Run an ffmpeg command, surfacing any failure as :class:`AssemblyError`."""
    logger.info("ffmpeg_exec", extra={"cmd": cmd})
    try:
        subprocess.run(cmd, check=True, capture_output=True)  # noqa: S603 - argv built internally
    except FileNotFoundError as exc:
        msg = "ffmpeg binary not found on PATH"
        raise AssemblyError(msg, detail=str(exc)) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace") if exc.stderr else None
        msg = "ffmpeg exited with a non-zero status"
        raise AssemblyError(msg, detail=stderr) from exc


class FfmpegService:
    """Builds and runs ffmpeg concat/mux commands."""

    def __init__(
        self,
        runner: Callable[[list[str]], None] | None = None,
        ffmpeg_bin: str = "ffmpeg",
    ) -> None:
        self._run = runner or _default_runner
        self._bin = ffmpeg_bin

    # --- command builders (pure) -------------------------------------------

    def build_concat_command(self, inputs: Sequence[str], output: str) -> list[str]:
        """Concatenate clips via the ``concat`` filter (re-encodes for safety).

        The filter graph is used instead of the concat *demuxer* so clips with
        slightly different encodes/timestamps join cleanly into one v+a pair.
        """
        cmd = [self._bin, "-y"]
        for src in inputs:
            cmd += ["-i", src]
        n = len(inputs)
        streams = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
        filtergraph = f"{streams}concat=n={n}:v=1:a=1[outv][outa]"
        cmd += ["-filter_complex", filtergraph, "-map", "[outv]", "-map", "[outa]", output]
        return cmd

    def build_mux_command(
        self,
        video: str,
        audio: str,
        output: str,
        *,
        duck: bool = True,
    ) -> list[str]:
        """Overlay ``audio`` (master track) onto ``video``.

        With ``duck`` the native bed is attenuated and mixed under the master;
        otherwise the master replaces the native audio outright.
        """
        cmd = [self._bin, "-y", "-i", video, "-i", audio]
        if duck:
            filtergraph = (
                f"[0:a]volume={_DUCK_VOLUME}[bed];"
                "[bed][1:a]amix=inputs=2:duration=longest:dropout_transition=0[aout]"
            )
            cmd += ["-filter_complex", filtergraph, "-map", "0:v", "-map", "[aout]"]
        else:
            cmd += ["-map", "0:v", "-map", "1:a"]
        cmd += ["-c:v", "copy", "-shortest", output]
        return cmd

    # --- execution ----------------------------------------------------------

    def concat(self, inputs: Sequence[str], output: str) -> str:
        """Concatenate ``inputs`` into ``output`` and return the output path."""
        if not inputs:
            msg = "cannot assemble: no clips to concatenate"
            raise AssemblyError(msg)
        self._run(self.build_concat_command(inputs, output))
        return output

    def mux_master_audio(
        self,
        video: str,
        audio: str,
        output: str,
        *,
        duck: bool = True,
    ) -> str:
        """Mux ``audio`` over ``video`` into ``output`` and return the path."""
        self._run(self.build_mux_command(video, audio, output, duck=duck))
        return output

    def assemble(
        self,
        clip_paths: Sequence[str],
        output: str,
        *,
        master_audio: str | None = None,
        duck: bool = True,
    ) -> str:
        """Concatenate ``clip_paths`` and, if given, overlay ``master_audio``.

        Without a master track the concatenated clips keep their native audio.
        """
        if master_audio is None:
            return self.concat(clip_paths, output)
        intermediate = f"{output}.concat.mp4"
        self.concat(clip_paths, intermediate)
        return self.mux_master_audio(intermediate, master_audio, output, duck=duck)


@functools.lru_cache(maxsize=1)
def get_ffmpeg_service() -> FfmpegService:
    """FastAPI dependency: a shared :class:`FfmpegService` instance."""
    return FfmpegService()
