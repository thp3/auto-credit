"""FFmpeg execution, cancellation, metadata normalization and atomic exports."""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from threading import Event
from typing import Callable
from fractions import Fraction

from PySide6.QtGui import QImage

from .artwork import end_card, overlay
from .models import Credit, VideoInfo


class Cancelled(Exception):
    pass


def executable(name: str) -> str:
    env = os.environ.get(f"AUTO_CREDIT_{name.upper()}")
    if env:
        path = Path(env)
        if not path.is_file():
            raise ValueError(f"找不到指定的 {name}：{path}")
        return str(path.resolve())
    suffix = ".exe" if os.name == "nt" else ""
    # PyInstaller onedir stores collected binaries under _MEIPASS.
    roots = [Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)),
             Path(sys.executable).parent]
    for root in roots:
        candidate = root / "bin" / f"{name}{suffix}"
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if not found:
        raise ValueError(f"找不到 {name}。請依 README 安裝 FFmpeg，或設定 AUTO_CREDIT_{name.upper()}。")
    return found


def process_options() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def run_process(args: list[str], cancel: Event, *, duration: float = 0,
                progress: Callable[[float], None] | None = None,
                cwd: Path | None = None) -> str:
    if cancel.is_set():
        raise Cancelled()
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=output,
                                stderr=errors, cwd=cwd, **process_options())
        try:
            while proc.poll() is None:
                if cancel.wait(.15):
                    raise Cancelled()
                if progress and cwd and duration:
                    progress_path = cwd / "progress.txt"
                    if progress_path.exists():
                        lines = progress_path.read_text(encoding="utf-8", errors="replace").splitlines()
                        values = [line.split("=", 1)[1] for line in lines if line.startswith("out_time_us=")]
                        if values and values[-1].lstrip("-").isdigit():
                            progress(min(.99, max(0, int(values[-1]) / 1_000_000 / duration)))
            if cancel.is_set():
                raise Cancelled()
            errors.seek(0)
            error_text = errors.read().decode("utf-8", errors="replace")
            if proc.returncode:
                raise ValueError(f"影片處理失敗：\n{error_text[-5000:]}")
            output.seek(0)
            return output.read().decode("utf-8", errors="replace")
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def probe(path: Path, cancel: Event | None = None) -> VideoInfo:
    if not path.is_file():
        raise ValueError("找不到原始影片，請重新選擇檔案。")
    data = json.loads(run_process([
        executable("ffprobe"), "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(path.resolve()),
    ], cancel if cancel is not None else Event()))
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
    if not video:
        raise ValueError("檔案沒有可用的影片軌道。")
    if video.get("color_transfer") in ("smpte2084", "arib-std-b67"):
        raise ValueError("第一版支援 SDR 影片；請先把 HDR 影片轉成 SDR 再匯入。")
    try:
        duration = float(video.get("duration") or data["format"]["duration"])
        rate = float(Fraction(video.get("avg_frame_rate", "0/1")))
    except (KeyError, ValueError, ZeroDivisionError):
        raise ValueError("無法讀取影片長度或幀率。") from None
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(rate) or rate <= 0:
        raise ValueError("影片長度或幀率無效。")
    width, height = int(video["width"]), int(video["height"])
    sar = video.get("sample_aspect_ratio", "1:1")
    try:
        width = round(width * float(Fraction(sar.replace(":", "/"))))
    except (ValueError, ZeroDivisionError):
        pass
    rotation = float(video.get("tags", {}).get("rotate", 0))
    for side in video.get("side_data_list", []):
        if "rotation" in side:
            rotation = float(side["rotation"])
    if round(rotation) % 180 != 0:
        width, height = height, width
    width, height = width + width % 2, height + height % 2
    if min(width, height) < 240 or max(width, height) > 4096:
        raise ValueError("第一版支援短邊至少 240、長邊最多 4096 像素的影片。")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    offset = (float(audio.get("start_time", 0)) - float(video.get("start_time", 0))) if audio else 0
    return VideoInfo(width, height, duration, min(rate, 60), audio is not None, offset)


def frame(path: Path, info: VideoInfo, seconds: float, cancel: Event) -> QImage:
    with tempfile.TemporaryDirectory(prefix="auto-credit-preview-") as folder:
        target = Path(folder) / "frame.png"
        seek = min(max(0, seconds), max(0, info.duration - 1 / info.fps))
        run_process([executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin",
                     "-ss", str(seek), "-i", str(path.resolve()), "-map", "0:V:0",
                     "-frames:v", "1", "-vf", f"scale={info.width}:{info.height},setsar=1",
                     "-update", "1", "-y", str(target)], cancel)
        image = QImage(str(target))
        if image.isNull():
            raise ValueError("無法擷取預覽畫面。")
        return image


def export_video(source: Path, target: Path, credit: Credit, cancel: Event,
                 progress: Callable[[float], None] | None = None) -> VideoInfo:
    credit.validate()
    source, target = source.resolve(), target.resolve()
    if source == target:
        raise ValueError("輸出位置不能與原始影片相同。")
    if target.suffix.lower() != ".mp4":
        raise ValueError("輸出檔案必須使用 .mp4 副檔名。")
    if target.exists():
        raise ValueError("輸出檔案已存在，請選擇另一個檔名。")
    if not target.parent.is_dir():
        raise ValueError("輸出資料夾不存在。")
    info = probe(source, cancel)
    # Same-volume temporary output + exclusive publication protects existing files.
    with tempfile.TemporaryDirectory(prefix=".auto-credit-", dir=target.parent) as folder:
        temp = Path(folder)
        if not overlay(credit, info.width, info.height).save(str(temp / "overlay.png")):
            raise ValueError("無法儲存標註圖層。")
        if not end_card(credit, info.width, info.height).save(str(temp / "end.png")):
            raise ValueError("無法儲存結尾卡。")
        rate = f"{info.fps:.8f}"
        body = f"{info.duration:.8f}"
        ending = f"{credit.outro_seconds:.8f}"
        audio = (f"[0:a:0]asetpts=PTS-STARTPTS+({info.audio_offset:.8f})/TB,"
                 "aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                 f"apad,atrim=duration={body}[a0];") if info.has_audio else (
                     f"[3:a]asplit=2[s0][s1];[s0]atrim=duration={body},asetpts=PTS-STARTPTS[a0];")
        silent = "3:a" if info.has_audio else "s1"
        filters = (
            f"[0:V:0]scale={info.width}:{info.height},setsar=1,fps={rate},"
            f"setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={body},"
            f"trim=duration={body}[base];"
            f"[base][1:v]overlay=0:0:shortest=1,format=yuv420p,setpts=PTS-STARTPTS[v0];"
            f"[2:v]setsar=1,format=yuv420p,trim=duration={ending},setpts=PTS-STARTPTS[v1];"
            + audio + f"[{silent}]atrim=duration={ending},asetpts=PTS-STARTPTS[a1];"
            "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
        )
        args = [executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-i", str(source), "-loop", "1", "-framerate", rate, "-i", "overlay.png",
                "-loop", "1", "-framerate", rate, "-i", "end.png",
                "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                "-filter_complex", filters, "-map", "[v]", "-map", "[a]",
                "-map_metadata", "-1", "-map_chapters", "-1", "-metadata:s:v:0", "rotate=0",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                "-t", str(info.duration + credit.outro_seconds),
                "-progress", "progress.txt", "result.mp4"]
        run_process(args, cancel, duration=info.duration + credit.outro_seconds,
                    progress=progress, cwd=temp)
        result = probe(temp / "result.mp4", cancel)
        if (result.width, result.height) != (info.width, info.height) or abs(
                result.duration - info.duration - credit.outro_seconds) > max(.2, 2 / info.fps):
            raise ValueError("輸出驗證失敗：影片尺寸或長度不符。")
        if cancel.is_set():
            raise Cancelled()
        # Windows rename is atomic and refuses an existing destination. On POSIX,
        # use an exclusive hard link because rename would overwrite silently.
        if os.name == "nt":
            os.rename(temp / "result.mp4", target)
        else:
            os.link(temp / "result.mp4", target)
        if progress:
            progress(1)
        return result
