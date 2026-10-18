import sys
from pathlib import Path
from threading import Event

from PySide6.QtCore import QSettings, QSize, QThread, QUrl, Signal, Qt
from PySide6.QtGui import QCloseEvent, QDesktopServices, QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
)

from .artwork import composite, end_card, ensure_fonts, overlay
from .engine import Cancelled, executable, export_video, frame, probe
from .models import Credit


class Job(QThread):
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(int)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.cancel = Event()
        self.function = function

    def run(self):
        try:
            value = self.function(self.cancel, lambda value: self.progress.emit(round(value * 100)))
            self.succeeded.emit(value)
        except Cancelled:
            self.cancelled.emit()
        except Exception as error:
            self.failed.emit(str(error))


class Preview(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.image = QImage()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(260, 240)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setWordWrap(True)
        self.setStyleSheet("background:#0a101b; color:#8797af; border-radius:12px; padding:12px;")

    def set_image(self, image):
        self.image = image
        self.refresh()

    def refresh(self):
        if not self.image.isNull():
            self.setPixmap(QPixmap.fromImage(self.image).scaled(
                self.size() - QSize(24, 24),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh()


STYLE = """
QMainWindow, QWidget#root { background:#111927; color:#e7edf5; }
QWidget { font-family:'Microsoft JhengHei','Noto Sans CJK TC'; font-size:14px; color:#e7edf5; }
QFrame#panel { background:#192436; border:1px solid #2a384d; border-radius:14px; }
QLabel#eyebrow { color:#71dbc4; font-weight:bold; font-size:12px; }
QLabel#title { font-size:28px; font-weight:bold; }
QLabel#muted { color:#9aabc2; }
QLineEdit, QComboBox, QDoubleSpinBox { background:#101a2a; border:1px solid #3a4a62;
    border-radius:7px; padding:9px; selection-background-color:#287f70; }
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus { border:1px solid #71dbc4; }
QPushButton { background:#293b53; border:1px solid #3a4a62; border-radius:8px;
    padding:10px 14px; font-weight:bold; }
QPushButton:hover { background:#354c69; }
QPushButton#primary { color:#0d2622; background:#71dbc4; border:0; }
QPushButton#primary:hover { background:#9be8d7; }
QPushButton:disabled { color:#728198; background:#202d40; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:#192436; color:#9aabc2; padding:10px 18px; margin-right:5px;
    border-top-left-radius:8px; border-top-right-radius:8px; }
QTabBar::tab:selected { background:#2b4058; color:#ffffff; }
QProgressBar { background:#101a2a; border:0; border-radius:5px; text-align:center; min-height:20px; }
QProgressBar::chunk { background:#3caa95; border-radius:5px; }
QScrollArea { border:0; background:transparent; }
QMessageBox { background:#192436; }
QToolTip { background:#293b53; color:#ffffff; border:1px solid #71dbc4; padding:6px; }
"""


class Window(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        ensure_fonts()
        self.setWindowTitle("Auto Credit · 影片來源標註")
        self.resize(1120, 830)
        self.setMinimumSize(960, 720)
        self.setAcceptDrops(True)
        self.settings = settings if settings is not None else QSettings("AutoCredit", "AutoCredit")
        self.source = None
        self.info = None
        self.raw_frame = QImage()
        self.output = None
        self.job = None
        self.close_pending = False
        root = QWidget(objectName="root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)
        outer.addWidget(QLabel("LOCAL VIDEO TOOL", objectName="eyebrow"))
        outer.addWidget(QLabel("讓每支影片，都有清楚的來源。", objectName="title"))
        subtitle = QLabel("匯入影片 → 填寫來源 → 預覽並輸出　・　全程在本機處理", objectName="muted")
        outer.addWidget(subtitle)
        columns = QHBoxLayout()
        columns.setSpacing(20)
        panel = QFrame(objectName="panel")
        panel.setMinimumWidth(320)
        left = QVBoxLayout(panel)
        left.setContentsMargins(20, 20, 20, 20)
        left.setSpacing(12)
        left.addWidget(QLabel("01　原始影片", objectName="eyebrow"))
        self.pick = QPushButton("＋ 選擇影片，或拖曳檔案到視窗")
        self.pick.clicked.connect(self.choose_source)
        left.addWidget(self.pick)
        self.filename = QLabel("尚未選擇影片", objectName="muted")
        self.filename.setWordWrap(True)
        left.addWidget(self.filename)
        left.addWidget(QLabel("02　來源資料", objectName="eyebrow"))
        form = QFormLayout()
        form.setSpacing(10)
        self.platform = QComboBox()
        self.platform.setEditable(True)
        self.platform.addItems(["YouTube", "Instagram", "TikTok", "X", "Facebook", "Bilibili", "其他"])
        self.platform.setCurrentText(str(self.settings.value("platform", "YouTube")))
        self.author = QLineEdit()
        self.author.setMaxLength(160)
        self.author.setPlaceholderText("@creator_id")
        self.url = QLineEdit()
        self.url.setMaxLength(2048)
        self.url.setPlaceholderText("https://…")
        self.seconds = QDoubleSpinBox()
        self.seconds.setRange(1, 30)
        self.seconds.setSuffix(" 秒")
        self.seconds.setValue(float(self.settings.value("seconds", 4)))
        self.size = QDoubleSpinBox()
        self.size.setRange(1.5, 5)
        self.size.setSingleStep(.1)
        self.size.setSuffix(" %")
        self.size.setValue(float(self.settings.value("size", 3)))
        self.size.setToolTip("標註字級占影片短邊的百分比")
        for name, control in (("原始平台", self.platform), ("作者 ID", self.author),
                              ("原片連結", self.url), ("結尾長度", self.seconds), ("標註字級", self.size)):
            form.addRow(name, control)
        left.addLayout(form)
        self.copy = QPushButton("複製來源文字")
        self.copy.clicked.connect(self.copy_caption)
        left.addWidget(self.copy)
        note = QLabel("結尾會附上完整網址及 QR Code。\nMP4 畫面中的網址無法直接點擊。", objectName="muted")
        note.setWordWrap(True)
        left.addWidget(note)
        left.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(366)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(panel)
        columns.addWidget(scroll)
        right = QVBoxLayout()
        right.setSpacing(12)
        right.addWidget(QLabel("03　輸出預覽", objectName="eyebrow"))
        self.tabs = QTabWidget()
        self.body_preview = Preview("選擇影片並填寫來源後，\n按「更新預覽」查看標註效果。")
        self.end_preview = Preview("結尾會顯示平台、作者、原片網址與 QR Code。")
        self.tabs.addTab(self.body_preview, "右上角標註")
        self.tabs.addTab(self.end_preview, "結尾資訊卡")
        right.addWidget(self.tabs, 1)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("擷取時間"))
        self.seek = QDoubleSpinBox()
        self.seek.setRange(0, 0)
        self.seek.setSuffix(" 秒")
        controls.addWidget(self.seek)
        self.preview_button = QPushButton("更新預覽")
        self.preview_button.clicked.connect(self.refresh_preview)
        controls.addWidget(self.preview_button)
        controls.addStretch()
        right.addLayout(controls)
        self.preview_hint = QLabel("預覽為靜態擷取畫面；輸出影片會全程顯示 credit。", objectName="muted")
        self.preview_hint.setWordWrap(True)
        right.addWidget(self.preview_hint)
        columns.addLayout(right, 1)
        outer.addLayout(columns, 1)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        outer.addWidget(self.progress)
        self.status = QLabel("就緒。請先選擇原始影片。", objectName="muted")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        buttons = QHBoxLayout()
        self.open_file = QPushButton("開啟完成影片")
        self.open_file.setEnabled(False)
        self.open_file.clicked.connect(self.open_output)
        self.open_folder = QPushButton("開啟輸出資料夾")
        self.open_folder.setEnabled(False)
        self.open_folder.clicked.connect(self.reveal_output)
        self.cancel_button = QPushButton("取消處理")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_job)
        self.export_button = QPushButton("產生 MP4 影片", objectName="primary")
        self.export_button.clicked.connect(self.start_export)
        buttons.addWidget(self.open_file)
        buttons.addWidget(self.open_folder)
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.export_button)
        outer.addLayout(buttons)
        self.setCentralWidget(root)
        self.setStyleSheet(STYLE)
        self.author.textChanged.connect(self.mark_stale)
        self.url.textChanged.connect(self.mark_stale)
        self.platform.currentTextChanged.connect(self.mark_stale)
        self.seconds.valueChanged.connect(self.mark_stale)
        self.size.valueChanged.connect(self.mark_stale)
        self.seek.valueChanged.connect(self.mark_stale)

    def mark_stale(self, *_):
        self.preview_hint.setText("設定已變更。請按「更新預覽」查看最新效果。")

    def credit(self):
        credit = Credit(self.platform.currentText().strip(), self.author.text().strip(),
                        self.url.text().strip(), self.seconds.value(), self.size.value())
        credit.validate()
        return credit

    def save_settings(self):
        for key, value in (("platform", self.platform.currentText()),
                           ("seconds", self.seconds.value()), ("size", self.size.value())):
            self.settings.setValue(key, value)

    def show_error(self, message):
        self.status.setText("處理未完成，請檢查輸入或錯誤訊息。")
        QMessageBox.warning(self, "無法完成", message)

    def set_busy(self, busy, indeterminate=False):
        for control in (self.pick, self.platform, self.author, self.url, self.seconds,
                        self.size, self.seek, self.preview_button, self.export_button):
            control.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.progress.setRange(0, 0 if busy and indeterminate else 100)
        if busy:
            self.progress.setValue(0)

    def run_job(self, function, callback, message, indeterminate=False):
        self.set_busy(True, indeterminate)
        self.status.setText(message)
        self.job = Job(function, self)
        self.job.succeeded.connect(callback)
        self.job.failed.connect(self.show_error)
        self.job.cancelled.connect(self.on_cancelled)
        self.job.progress.connect(self.progress.setValue)
        self.job.finished.connect(self.job_finished)
        self.job.start()

    def job_finished(self):
        finished = self.job
        self.job = None
        self.set_busy(False)
        finished.deleteLater()
        if self.close_pending:
            self.close()

    def on_cancelled(self):
        self.status.setText("已取消處理，暫存檔已清理。")
        self.progress.setValue(0)

    def cancel_job(self):
        if self.job:
            self.job.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("正在停止處理並清理暫存檔…")

    def choose_source(self):
        name, _ = QFileDialog.getOpenFileName(self, "選擇原始影片", str(self.settings.value("input_dir", "")),
                                             "影片 (*.mp4 *.mov *.mkv *.webm *.avi *.m4v);;所有檔案 (*)")
        if name:
            self.load_source(Path(name))

    def load_source(self, path):
        if self.job:
            return
        def load(cancel, _progress):
            info = probe(path, cancel)
            return path, info, frame(path, info, 0, cancel)
        self.run_job(load, self.source_loaded, "正在讀取影片…", True)

    def source_loaded(self, result):
        self.source, self.info, self.raw_frame = result
        self.seek.setRange(0, max(0, self.info.duration - 1 / self.info.fps))
        self.seek.setValue(0)
        self.settings.setValue("input_dir", str(self.source.parent))
        self.filename.setText(f"{self.source.name}\n{self.info.width} × {self.info.height} · "
                              f"{self.info.duration:.1f} 秒 · {self.info.fps:.2f} fps")
        self.filename.setToolTip(str(self.source))
        self.body_preview.set_image(self.raw_frame)
        self.status.setText("影片已載入。填寫來源後，按「更新預覽」。")
        self.end_preview.clear()
        self.end_preview.image = QImage()
        self.end_preview.setText("填寫來源後，按「更新預覽」產生結尾卡。")
        self.preview_hint.setText("目前顯示原始畫面。請填寫來源並更新預覽。")

    def refresh_preview(self):
        try:
            credit = self.credit()
            if not self.source:
                raise ValueError("請先選擇原始影片。")
            source, info, seconds = self.source, self.info, self.seek.value()
            def render(cancel, _progress):
                raw = frame(source, info, seconds, cancel)
                return (composite(raw, overlay(credit, info.width, info.height)),
                        end_card(credit, info.width, info.height))
            self.run_job(render, self.preview_ready, "正在產生預覽…", True)
        except ValueError as error:
            self.show_error(str(error))

    def preview_ready(self, result):
        self.body_preview.set_image(result[0])
        self.end_preview.set_image(result[1])
        self.preview_hint.setText("預覽已更新，與輸出使用相同標註及結尾卡版面。")
        self.status.setText("預覽已就緒。可切換頁籤檢查結尾，或產生影片。")
        self.save_settings()

    def copy_caption(self):
        try:
            QApplication.clipboard().setText(self.credit().caption)
            self.status.setText("已複製來源文字，可貼到影片說明欄。")
        except ValueError as error:
            self.show_error(str(error))

    def start_export(self):
        try:
            credit = self.credit()
            if not self.source:
                raise ValueError("請先選擇原始影片。")
            executable("ffmpeg")
            name = f"{self.source.stem}_credit.mp4"
            directory = Path(str(self.settings.value("output_dir", str(self.source.parent))))
            path, _ = QFileDialog.getSaveFileName(self, "儲存標註影片（請使用新檔名）", str(directory / name),
                                                 "MP4 影片 (*.mp4)", options=QFileDialog.Option.DontConfirmOverwrite)
            if not path:
                return
            target = Path(path)
            if not target.suffix:
                target = target.with_suffix(".mp4")
            if target.exists():
                raise ValueError("檔案已存在。為保護既有影片，請選擇另一個檔名。")
            source = self.source
            self.save_settings()
            self.settings.setValue("output_dir", str(target.parent))
            def export(cancel, progress):
                export_video(source, target, credit, cancel, progress)
                return target
            self.run_job(export, self.export_ready, "正在輸出影片…")
        except ValueError as error:
            self.show_error(str(error))

    def export_ready(self, target):
        self.output = target
        self.progress.setValue(100)
        self.status.setText(f"已完成：{target}")
        self.open_file.setEnabled(True)
        self.open_folder.setEnabled(True)

    def open_output(self):
        if self.output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output)))

    def reveal_output(self):
        if self.output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output.parent)))

    def dragEnterEvent(self, event):
        if not self.job and event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).is_file():
                event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.job:
            self.load_source(Path(event.mimeData().urls()[0].toLocalFile()))
            event.acceptProposedAction()

    def closeEvent(self, event: QCloseEvent):
        if self.job:
            self.close_pending = True
            self.cancel_job()
            event.ignore()
        else:
            self.save_settings()
            event.accept()


def main():
    app = QApplication(sys.argv)
    ensure_fonts()
    app.setApplicationName("Auto Credit")
    app.setFont(QFont("Microsoft JhengHei", 10))
    if len(sys.argv) == 3 and sys.argv[1] == "--self-check":
        from .selfcheck import run_self_check
        sys.exit(run_self_check(Path(sys.argv[2]).resolve()))
    window = Window()
    window.show()
    sys.exit(app.exec())
