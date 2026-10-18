import shutil
import subprocess
import array
import math
from threading import Event

import pytest

from auto_credit.engine import Cancelled, executable, export_video, frame, probe
from auto_credit.models import Credit

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                                reason="FFmpeg and FFprobe are required for integration tests")


def ffmpeg(*args):
    subprocess.run([executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", *map(str, args)],
                   check=True, capture_output=True)


def make_video(path, size="640x360", audio=True, duration="1.3"):
    args = ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate=24:duration={duration}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}"]
    ffmpeg(*args, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
           "-c:a", "aac", path)


@pytest.mark.parametrize("size,audio", [("640x360", True), ("360x640", False)])
def test_real_export_and_end_card(tmp_path, size, audio):
    source = tmp_path / "作者's [原片] 01.mp4"
    target = tmp_path / "輸出影片.mp4"
    make_video(source, size, audio)
    credit = Credit("測試平台", "@原作者:%'[]", "https://example.com/watch?v=1&tag=中文", 1)
    before = source.read_bytes()
    progress = []
    result = export_video(source, target, credit, Event(), progress.append)
    assert source.read_bytes() == before
    assert abs(result.duration - (probe(source).duration + 1)) < .15
    assert result.has_audio
    assert (result.width, result.height) == tuple(map(int, size.split("x")))
    assert progress[-1] == 1
    # Compare original and encoded frame: the upper-right watermark changes pixels.
    original = frame(source, probe(source), .5, Event())
    encoded = frame(target, result, .5, Event())
    differing = sum(original.pixelColor(x, y) != encoded.pixelColor(x, y)
                    for x in range(result.width // 2, result.width, 4)
                    for y in range(10, 70, 4))
    assert differing > 40
    ending = frame(target, result, result.duration - .4, Event())
    corner = ending.pixelColor(2, 2)
    assert abs(corner.red() - 17) < 8 and abs(corner.blue() - 39) < 8
    assert not list(tmp_path.glob(".auto-credit-*"))


def test_phone_rotation(tmp_path):
    source = tmp_path / "normal.mp4"
    rotated = tmp_path / "phone.mp4"
    make_video(source, audio=False)
    ffmpeg("-display_rotation:v:0", "90", "-i", source, "-c", "copy", rotated)
    info = probe(rotated)
    assert (info.width, info.height) == (360, 640)
    target = tmp_path / "rotated-credit.mp4"
    result = export_video(rotated, target, Credit("X", "@a", "https://example.com/a", 1), Event())
    assert (result.width, result.height) == (360, 640)
    image = frame(target, result, .5, Event())
    assert (image.width(), image.height()) == (360, 640)


def test_existing_file_and_input_are_protected(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original")
    credit = Credit("YouTube", "@a", "https://example.com/a")
    with pytest.raises(ValueError, match="原始影片"):
        export_video(source, source, credit, Event())
    target = tmp_path / "existing.mp4"
    target.write_bytes(b"keep me")
    with pytest.raises(ValueError, match="已存在"):
        export_video(source, target, credit, Event())
    assert target.read_bytes() == b"keep me"


def test_cancel_running_encoder_cleans_temp(tmp_path):
    source = tmp_path / "source.mp4"
    make_video(source, "1280x720", audio=False, duration="8")
    target = tmp_path / "cancelled.mp4"
    cancel = Event()
    def stop_after_progress(value):
        if value > 0:
            cancel.set()
    with pytest.raises(Cancelled):
        export_video(source, target, Credit("X", "@a", "https://example.com/a", 2),
                     cancel, stop_after_progress)
    assert not target.exists()
    assert not list(tmp_path.glob(".auto-credit-*"))


def test_broken_file_fails_without_output(tmp_path):
    source = tmp_path / "broken.mp4"
    source.write_text("not a video", encoding="utf-8")
    target = tmp_path / "result.mp4"
    with pytest.raises(ValueError):
        export_video(source, target, Credit("X", "@a", "https://example.com/a"), Event())
    assert not target.exists()


def test_anamorphic_display_aspect(tmp_path):
    source = tmp_path / "sar.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=480x360:rate=24:duration=1",
           "-vf", "setsar=4/3", "-c:v", "libx264", source)
    assert (probe(source).width, probe(source).height) == (640, 360)


def test_delayed_audio_stays_in_sync_and_ending_is_silent(tmp_path):
    source = tmp_path / "delayed.mp4"
    target = tmp_path / "result.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=2",
           "-itsoffset", "0.5", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1.5",
           "-c:v", "libx264", "-c:a", "aac", source)
    export_video(source, target, Credit("X", "@a", "https://example.com/a", 1), Event())
    def rms(at):
        result = subprocess.run([executable("ffmpeg"), "-v", "error", "-ss", str(at),
                                 "-i", str(target), "-t", "0.2", "-vn", "-ac", "1", "-ar", "48000",
                                 "-f", "s16le", "pipe:1"], capture_output=True, check=True)
        samples = array.array("h", result.stdout)
        return math.sqrt(sum(s * s for s in samples) / len(samples))
    assert rms(.1) < 20
    assert rms(.7) > 1000
    assert rms(2.5) < 20


def test_gui_load_preview_and_export(qt_app, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from auto_credit.app import Window
    import time
    source = tmp_path / "input.mp4"
    target = tmp_path / "10月18日 (1)_credit.mp4"
    make_video(source, audio=False)
    window = Window(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    errors = []
    monkeypatch.setattr(window, "show_error", errors.append)
    def finish():
        deadline = time.monotonic() + 20
        while window.job is not None and time.monotonic() < deadline:
            qt_app.processEvents()
            time.sleep(.01)  # Release the GIL for the Python worker, as app.exec() does.
        if window.job is not None:
            window.job.cancel.set()
            window.job.wait(5000)
            qt_app.processEvents()
            pytest.fail("GUI job did not finish within 20 seconds")
        assert window.job is None
        assert errors == []
    window.show()
    window.load_source(source)
    finish()
    window.author.setText("@作者")
    window.url.setText("https://example.com/original")
    window.seconds.setValue(1)
    window.refresh_preview()
    finish()
    assert not window.end_preview.image.isNull()
    window.copy_caption()
    assert "@作者" in QApplication.clipboard().text()
    # Exercise the actual save dialog rather than bypassing it with a stub.
    observed = []
    def accept_new_file():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QFileDialog):
            observed.append(not target.exists())
            dialog.selectFile(str(target))
            dialog.accept()
    def dismiss_stuck_dialogs():
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, (QFileDialog, QMessageBox)):
                widget.reject()
    watchdog = QTimer(window)
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(dismiss_stuck_dialogs)
    watchdog.start(3000)
    QTimer.singleShot(50, accept_new_file)
    window.start_export()
    watchdog.stop()
    assert observed == [True]
    finish()
    assert target.is_file()
    assert window.progress.value() == 100
    assert window.open_file.isEnabled()
    assert window.output == target
    window.close()
