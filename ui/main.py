#!/usr/bin/env python3
"""Yeti GX control UI"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton,
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot

try:
    from yeti_gx import YetiGX, YetiGXError
except ImportError:
    YetiGX = None
    YetiGXError = Exception

STYLE_ROOT = """
    QWidget { background: #1c1c1c; color: #ddd; font-family: sans-serif; }
"""

STYLE_SLIDER = """
    QSlider::groove:horizontal {
        height: 4px; background: #333; border-radius: 2px;
    }
    QSlider::handle:horizontal {
        width: 16px; height: 16px; background: #ccc;
        border-radius: 8px; margin: -6px 0;
    }
    QSlider::sub-page:horizontal {
        background: #3a9; border-radius: 2px;
    }
"""

def _mute_style(muted: bool) -> str:
    if muted:
        return """QPushButton {
            background: #4a0e0e; color: #ff5555;
            border: 1px solid #882222; border-radius: 8px;
            font-size: 15px; font-weight: bold; letter-spacing: 2px;
        }
        QPushButton:hover { background: #5a1010; }"""
    else:
        return """QPushButton {
            background: #0e3a1a; color: #44ee77;
            border: 1px solid #226633; border-radius: 8px;
            font-size: 15px; font-weight: bold; letter-spacing: 2px;
        }
        QPushButton:hover { background: #104520; }"""

def _lock_style(enabled: bool) -> str:
    if enabled:
        return """QPushButton {
            background: #0a3535; color: #33ddcc;
            border: 1px solid #117766; border-radius: 8px;
            font-size: 12px; letter-spacing: 1px;
        }
        QPushButton:hover { background: #0d3f3f; }"""
    else:
        return """QPushButton {
            background: #252525; color: #666;
            border: 1px solid #3a3a3a; border-radius: 8px;
            font-size: 12px;
        }
        QPushButton:hover { background: #2e2e2e; }"""


class MainWindow(QMainWindow):
    _sig_mute      = pyqtSignal(bool)
    _sig_gain      = pyqtSignal(int)
    _sig_smartlock = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Yeti GX")
        self._mic = None
        self._muted = False
        self._gain = 50
        self._smartlock = False

        self._build_ui()

        self._sig_mute.connect(self._on_mute_slot)
        self._sig_gain.connect(self._on_gain_slot)
        self._sig_smartlock.connect(self._on_smartlock_slot)

        self._connect_device()

    def _build_ui(self):
        root = QWidget()
        root.setStyleSheet(STYLE_ROOT)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # ── Gain row ──────────────────────────────────────────────────────────
        gain_row = QHBoxLayout()
        gain_row.setSpacing(10)

        gain_lbl = QLabel("GAIN")
        gain_lbl.setStyleSheet("color: #555; font-size: 10px; letter-spacing: 1px;")
        gain_lbl.setFixedWidth(34)

        self._gain_slider = QSlider(Qt.Orientation.Horizontal)
        self._gain_slider.setRange(0, 100)
        self._gain_slider.setValue(50)
        self._gain_slider.setStyleSheet(STYLE_SLIDER)
        self._gain_slider.valueChanged.connect(self._slider_changed)

        self._gain_val = QLabel("50")
        self._gain_val.setStyleSheet("color: #aaa; font-size: 13px;")
        self._gain_val.setFixedWidth(28)
        self._gain_val.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        gain_row.addWidget(gain_lbl)
        gain_row.addWidget(self._gain_slider)
        gain_row.addWidget(self._gain_val)

        # ── Button row ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._mute_btn = QPushButton("● LIVE")
        self._mute_btn.setFixedHeight(52)
        self._mute_btn.setStyleSheet(_mute_style(False))
        self._mute_btn.clicked.connect(self._toggle_mute)

        self._lock_btn = QPushButton("Smart Lock")
        self._lock_btn.setFixedHeight(52)
        self._lock_btn.setFixedWidth(110)
        self._lock_btn.setStyleSheet(_lock_style(False))
        self._lock_btn.clicked.connect(self._toggle_smartlock)

        btn_row.addWidget(self._mute_btn, stretch=1)
        btn_row.addWidget(self._lock_btn)

        layout.addLayout(gain_row)
        layout.addLayout(btn_row)

        self.setCentralWidget(root)
        self.setFixedSize(380, 148)

    # ── device connection ─────────────────────────────────────────────────────

    def _connect_device(self):
        if YetiGX is None:
            self.setWindowTitle("Yeti GX — library not found")
            return
        try:
            self._mic = YetiGX()
            self._mic.listen(
                on_mute=lambda v: self._sig_mute.emit(v),
                on_gain=lambda v: self._sig_gain.emit(v),
                on_smartlock=lambda v: self._sig_smartlock.emit(v),
            )
            self._apply_state(
                self._mic.get_mute(),
                self._mic.get_gain(),
                self._mic.get_smartlock(),
            )
        except YetiGXError as e:
            self.setWindowTitle(f"Yeti GX — {e}")

    def closeEvent(self, event):
        if self._mic:
            self._mic.close()
        super().closeEvent(event)

    # ── state ─────────────────────────────────────────────────────────────────

    def _apply_state(self, muted: bool, gain: int, smartlock: bool):
        self._muted = muted
        self._gain = gain
        self._smartlock = smartlock

        self._mute_btn.setText("● MUTED" if muted else "● LIVE")
        self._mute_btn.setStyleSheet(_mute_style(muted))

        self._lock_btn.setStyleSheet(_lock_style(smartlock))

        self._gain_slider.blockSignals(True)
        self._gain_slider.setValue(gain)
        self._gain_slider.blockSignals(False)
        self._gain_val.setText(str(gain))

    # ── device callbacks (listener thread → main thread) ──────────────────────

    @pyqtSlot(bool)
    def _on_mute_slot(self, muted):
        self._apply_state(muted, self._gain, self._smartlock)

    @pyqtSlot(int)
    def _on_gain_slot(self, gain):
        self._apply_state(self._muted, gain, self._smartlock)

    @pyqtSlot(bool)
    def _on_smartlock_slot(self, enabled):
        self._apply_state(self._muted, self._gain, enabled)

    # ── UI actions ────────────────────────────────────────────────────────────

    def _toggle_mute(self):
        new = not self._muted
        if self._mic:
            self._mic.set_mute(new)
        self._apply_state(new, self._gain, self._smartlock)

    def _toggle_smartlock(self):
        new = not self._smartlock
        if self._mic:
            self._mic.set_smartlock(new)
        self._apply_state(self._muted, self._gain, new)

    def _slider_changed(self, value: int):
        self._gain_val.setText(str(value))
        if value != self._gain:
            self._gain = value
            if self._mic:
                self._mic.set_gain(value)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("yeti-gx")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
