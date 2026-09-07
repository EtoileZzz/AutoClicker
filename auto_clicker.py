# -*- coding: utf-8 -*-
"""
自动点击器 v6.0

运行逻辑：
  - F8 进入“监听选择”状态（冷启动，不立即点击）
  - 出现半透明悬浮窗，显示预设 1~6 的名称与任务数
  - 按数字 1~6 启动对应预设；运行中可按 1~6 即时切换
  - F8 或 Esc 退出监听 / 停止运行

其他：
  - 支持 1~6 普通预设 + 特殊“预设 7”（等待鼠标/按键触发后执行）
  - 预设 7 触发后保持监听，可随时切回 1~6
  - 每个预设下有线性流程图，可拖拽排序、双击编辑
  - 每个任务可单独设置运行间隔、OCR 校验开关/文字/框选区域
  - 任务支持上移 / 下移排序
"""

import copy
import ctypes
import ctypes.wintypes as wt
import json
import os
import queue
import random
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_NAME = "自动点击器"
APP_VERSION = "6.0"

BG = "#eef3f9"
PANEL = "#ffffff"
FG = "#1e2a3a"
MUTED = "#6b7a90"
ACCENT = "#2f7cf6"
GREEN = "#1c9e62"
RED = "#e5484d"
AMBER = "#e8a13a"


# ---------------------------------------------------------------------------
# Win32
# ---------------------------------------------------------------------------
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

WM_HOTKEY = 0x0312
VK_F8 = 0x77
VK_ESCAPE = 0x1B
VK_1 = 0x31
VK_6 = 0x36
VK_7 = 0x37
MOD_NOREPEAT = 0x4000
HK_F8 = 1
HK_ESC = 2

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120

SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

CLICK_BUTTONS = (("左键", "left"), ("右键", "right"), ("双击左键", "double"))
SCROLL_DIRECTIONS = ("向上", "向下")
OCR_FAIL_CHOICES = (
    ("停止并提示", "stop"),
    ("跳过本任务", "skip"),
    ("不匹配也执行", "pass"),
)
TRIGGER_CHOICES = (
    ("鼠标左键", "mouse_left"),
    ("鼠标右键", "mouse_right"),
    ("鼠标中键", "mouse_middle"),
    ("空格键", "vk_space"),
    ("回车键", "vk_enter"),
    ("F1", "vk_f1"),
    ("F2", "vk_f2"),
    ("F3", "vk_f3"),
    ("F4", "vk_f4"),
    ("F5", "vk_f5"),
    ("F6", "vk_f6"),
    ("F7", "vk_f7"),
    ("F8", "vk_f8"),
    ("F9", "vk_f9"),
    ("F10", "vk_f10"),
    ("F11", "vk_f11"),
    ("F12", "vk_f12"),
)

TRIGGER_VK = {
    "mouse_left": 0x01,
    "mouse_right": 0x02,
    "mouse_middle": 0x04,
    "vk_space": 0x20,
    "vk_enter": 0x0D,
    "vk_f1": 0x70,
    "vk_f2": 0x71,
    "vk_f3": 0x72,
    "vk_f4": 0x73,
    "vk_f5": 0x74,
    "vk_f6": 0x75,
    "vk_f7": 0x76,
    "vk_f8": 0x77,
    "vk_f9": 0x78,
    "vk_f10": 0x79,
    "vk_f11": 0x7A,
    "vk_f12": 0x7B,
}
LOOP_MODES = (("不循环", "none"), ("按次数循环", "count"),
              ("按时间循环", "seconds"))


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wt.HWND),
        ("message", wt.UINT),
        ("wParam", wt.WPARAM),
        ("lParam", wt.LPARAM),
        ("time", wt.DWORD),
        ("pt", wt.POINT),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def set_cursor_pos(x: int, y: int) -> bool:
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.SetCursorPos.restype = wt.BOOL
    return bool(user32.SetCursorPos(int(round(x)), int(round(y))))


def get_cursor_pos():
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
    user32.GetCursorPos.restype = wt.BOOL
    pt = wt.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def get_virtual_screen():
    user32.GetSystemMetrics.restype = ctypes.c_int
    x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return x, y, w, h


def _mouse_event(flags: int, data: int = 0) -> None:
    user32.mouse_event.argtypes = [
        wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t,
    ]
    user32.mouse_event(flags, 0, 0, data & 0xFFFFFFFF, 0)


def send_click(kind: str) -> None:
    if kind == "left":
        _mouse_event(MOUSEEVENTF_LEFTDOWN)
        time.sleep(0.02)
        _mouse_event(MOUSEEVENTF_LEFTUP)
    elif kind == "right":
        _mouse_event(MOUSEEVENTF_RIGHTDOWN)
        time.sleep(0.02)
        _mouse_event(MOUSEEVENTF_RIGHTUP)
    elif kind == "double":
        for _ in range(2):
            _mouse_event(MOUSEEVENTF_LEFTDOWN)
            time.sleep(0.03)
            _mouse_event(MOUSEEVENTF_LEFTUP)
            time.sleep(0.04)


def send_wheel(direction: str, notches: int) -> None:
    amount = max(1, int(notches)) * WHEEL_DELTA
    if direction == "向下":
        amount = -amount
    _mouse_event(MOUSEEVENTF_WHEEL, amount)


def gdi_capture(x: int, y: int, width: int, height: int):
    """快速截取屏幕矩形，返回 BGRA 字节。"""
    user32.GetDC.argtypes = [wt.HWND]
    user32.GetDC.restype = wt.HDC
    user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
    gdi32.CreateCompatibleDC.restype = wt.HDC
    gdi32.CreateDIBSection.argtypes = [
        wt.HDC, ctypes.POINTER(BITMAPINFO), wt.UINT,
        ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD,
    ]
    gdi32.CreateDIBSection.restype = wt.HBITMAP
    gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
    gdi32.SelectObject.restype = wt.HGDIOBJ
    gdi32.BitBlt.argtypes = [
        wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD,
    ]
    gdi32.BitBlt.restype = wt.BOOL
    gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wt.HDC]

    width = max(1, int(width))
    height = max(1, int(height))
    screen_dc = user32.GetDC(None)
    if not screen_dc:
        return b""

    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height          # top-down
    header.biPlanes = 1
    header.biBitCount = 32
    header.biCompression = BI_RGB
    info = BITMAPINFO()
    info.bmiHeader = header

    bits = ctypes.c_void_p()
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateDIBSection(
        screen_dc, ctypes.byref(info), DIB_RGB_COLORS,
        ctypes.byref(bits), None, 0,
    )
    old = gdi32.SelectObject(mem_dc, bitmap)
    gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc,
                 int(x), int(y), SRCCOPY)
    data = ctypes.string_at(bits, width * height * 4)
    gdi32.SelectObject(mem_dc, old)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(None, screen_dc)
    return data


# ---------------------------------------------------------------------------
# OCR（Windows.Media.Ocr + GDI 快速截图，引擎按线程缓存）
# ---------------------------------------------------------------------------
_OCR_MODULES = None
_OCR_ENGINES = {}


def _ocr_libs():
    global _OCR_MODULES
    if _OCR_MODULES is None:
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import (
            BitmapAlphaMode,
            BitmapPixelFormat,
            SoftwareBitmap,
        )
        from winrt.windows.media.ocr import OcrEngine
        _OCR_MODULES = (Language, BitmapAlphaMode, BitmapPixelFormat,
                        SoftwareBitmap, OcrEngine)
    return _OCR_MODULES


def _get_ocr_engine():
    key = threading.get_ident()
    if key in _OCR_ENGINES:
        return _OCR_ENGINES[key]
    Language, _, _, _, OcrEngine = _ocr_libs()
    engine = None
    for code in ("zh-CN", "zh-Hans", "zh-Hant-TW", "en-US"):
        try:
            engine = OcrEngine.try_create_from_language(Language(code))
            if engine is not None:
                break
        except Exception:
            continue
    if engine is None:
        try:
            engine = OcrEngine.try_create_from_user_profile_languages()
        except Exception:
            engine = None
    if engine is None:
        raise RuntimeError("系统未安装可用的 OCR 语言包")
    _OCR_ENGINES[key] = engine
    return engine


def ocr_bgra(data: bytes, width: int, height: int) -> str:
    _, AlphaMode, PixelFormat, SoftwareBitmap, _ = _ocr_libs()
    engine = _get_ocr_engine()
    width = max(1, int(width))
    height = max(1, int(height))
    need = width * height * 4
    if len(data) < need:
        raise ValueError("OCR 图像数据长度不足")
    bitmap = SoftwareBitmap(
        PixelFormat.BGRA8, width, height, AlphaMode.PREMULTIPLIED
    )
    bitmap.copy_from_buffer(data[:need])
    result = engine.recognize_async(bitmap).get()
    return result.text or ""


def ocr_region(x: int, y: int, width: int, height: int) -> str:
    """以 (x, y) 为中心截取小区域并 OCR。"""
    vx, vy, vw, vh = get_virtual_screen()
    width = max(10, int(width))
    height = max(10, int(height))
    left = max(vx, int(x) - width // 2)
    top = max(vy, int(y) - height // 2)
    right = min(vx + vw, int(x) + (width - width // 2))
    bottom = min(vy + vh, int(y) + (height - height // 2))
    if right <= left or bottom <= top:
        return ""
    data = gdi_capture(left, top, right - left, bottom - top)
    if not data:
        return ""
    return ocr_bgra(data, right - left, bottom - top)


def ocr_box_region(x1: int, y1: int, x2: int, y2: int) -> str:
    """对图形化框选出来的矩形区域 OCR。"""
    left, top = min(x1, x2), min(y1, y2)
    right, bottom = max(x1, x2), max(y1, y2)
    width = max(2, right - left)
    height = max(2, bottom - top)
    data = gdi_capture(left, top, width, height)
    if not data:
        return ""
    return ocr_bgra(data, width, height)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "").casefold()


def text_matches(expected: str, recognized: str) -> bool:
    exp = normalize_text(expected)
    got = normalize_text(recognized)
    return bool(exp) and exp in got


# ---------------------------------------------------------------------------
# 全局热键线程
# ---------------------------------------------------------------------------
class HotkeyThread(threading.Thread):
    def __init__(self, event_queue):
        super().__init__(name="HotkeyThread", daemon=True)
        self._queue = event_queue
        self.commands = queue.Queue()
        self._msg = MSG()
        self._nums_registered = False

    def run(self):
        user32.PeekMessageW.argtypes = [
            ctypes.POINTER(MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT,
        ]
        user32.PeekMessageW.restype = wt.BOOL
        user32.PeekMessageW(ctypes.byref(self._msg), None, 0, 0, 0)

        user32.RegisterHotKey.argtypes = [
            wt.HWND, ctypes.c_int, wt.UINT, wt.UINT,
        ]
        user32.RegisterHotKey.restype = wt.BOOL
        ok_f8 = user32.RegisterHotKey(None, HK_F8, MOD_NOREPEAT, VK_F8)
        ok_esc = user32.RegisterHotKey(None, HK_ESC, MOD_NOREPEAT, VK_ESCAPE)
        failed = []
        if not ok_f8:
            failed.append("F8")
        if not ok_esc:
            failed.append("Esc")
        if failed:
            self._queue.put(("hotkey_error", "、".join(failed)))
            return
        self._queue.put(("ready", None))

        while True:
            try:
                command = self.commands.get_nowait()
            except queue.Empty:
                command = None
            if command:
                action = command[0]
                if action == "numbers" and command[1]:
                    self._register_numbers()
                elif action == "numbers":
                    self._unregister_numbers()
                elif action == "quit":
                    return

            while user32.PeekMessageW(
                    ctypes.byref(self._msg), None, 0, 0, 1) > 0:
                if self._msg.message == WM_HOTKEY:
                    if self._msg.wParam == HK_F8:
                        self._queue.put(("key", "f8"))
                    elif self._msg.wParam == HK_ESC:
                        self._queue.put(("key", "esc"))
                    elif 10 <= self._msg.wParam <= 16:
                        self._queue.put(
                            ("key", f"num{self._msg.wParam - 9}"))
                elif self._msg.message == 0x0012:  # WM_QUIT
                    return
            time.sleep(0.015)

    def _register_numbers(self):
        if self._nums_registered:
            return
        user32.RegisterHotKey.restype = wt.BOOL
        ok = True
        for i in range(7):
            if not user32.RegisterHotKey(
                    None, 10 + i, MOD_NOREPEAT, VK_1 + i):
                ok = False
        self._nums_registered = ok
        if not ok:
            self._queue.put(("hotkey_error", "数字键 1~7"))

    def _unregister_numbers(self):
        if not self._nums_registered:
            return
        user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wt.BOOL
        for i in range(7):
            user32.UnregisterHotKey(None, 10 + i)
        self._nums_registered = False


# ---------------------------------------------------------------------------
# 执行线程
# ---------------------------------------------------------------------------
class TriggerMonitor(threading.Thread):
    """全局轮询鼠标/键盘触发键，检测按下沿。"""
    def __init__(self, out_queue, trigger_code):
        super().__init__(name="TriggerMonitor", daemon=True)
        self.out = out_queue
        self.vk = TRIGGER_VK.get(trigger_code, 0x01)
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
        pressed = False
        while not self.stop_event.is_set():
            down = bool(user32.GetAsyncKeyState(self.vk) & 0x8000)
            if down and not pressed:
                self.out.put(("trigger", None))
            pressed = down
            self.stop_event.wait(0.008)


class NumberMonitor(threading.Thread):
    """区分普通点击 / 长按 / Ctrl+数字 的 1~7 键监控。"""
    LONG_MS = 0.38

    def __init__(self, out_queue):
        super().__init__(name="NumberMonitor", daemon=True)
        self.out = out_queue
        self.stop_event = threading.Event()
        self.keys = {
            i: {"down": False, "t0": 0.0, "long": False}
            for i in range(1, 8)
        }

    def stop(self):
        self.stop_event.set()

    def run(self):
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
        vk_ctrl = 0x11
        while not self.stop_event.is_set():
            ctrl = bool(user32.GetAsyncKeyState(vk_ctrl) & 0x8000)
            now = time.monotonic()
            for number in range(1, 8):
                state = self.keys[number]
                down = bool(
                    user32.GetAsyncKeyState(VK_1 + number - 1) & 0x8000)
                if down and not state["down"]:
                    state["down"] = True
                    state["t0"] = now
                    state["long"] = False
                    if ctrl:
                        state["long"] = True
                        self.out.put(("loopkey", number))
                elif down and state["down"] and not state["long"]:
                    if now - state["t0"] >= self.LONG_MS:
                        state["long"] = True
                        self.out.put(("longkey", number))
                elif state["down"] and not down:
                    if not state["long"]:
                        self.out.put(("numkey", number))
                    state["down"] = False
                    state["long"] = False
            self.stop_event.wait(0.01)


class ClickWorker(threading.Thread):
    def __init__(self, tasks, options, out_queue, run_id=1,
                 loop_spec=None, is_loop=False):
        super().__init__(name="ClickWorker", daemon=True)
        self.tasks = tasks
        self.options = options
        self.out = out_queue
        self.run_id = run_id
        self.stop_event = threading.Event()
        self.running_event = threading.Event()
        self.running_event.set()
        self.done_count = 0
        self.total_actions = sum(t.get("count", 1) for t in tasks)
        self.loop_spec = loop_spec or {}
        self.is_loop = bool(is_loop)

    def _ready(self) -> bool:
        while not self.running_event.is_set():
            if self.stop_event.is_set():
                return False
            self.running_event.wait(0.05)
        return not self.stop_event.is_set()

    def _sleep_ok(self, seconds: float) -> bool:
        end = time.monotonic() + max(0.0, seconds)
        while time.monotonic() < end:
            if self.stop_event.is_set():
                return False
            if not self.running_event.is_set():
                while not self.running_event.is_set():
                    if self.stop_event.is_set():
                        return False
                    self.running_event.wait(0.05)
                if time.monotonic() >= end:
                    return True
            else:
                time.sleep(min(0.015, max(0.0, end - time.monotonic())))
        return not self.stop_event.is_set()

    def _jitter(self, value, amount):
        if amount <= 0:
            return value
        return value + random.randint(-amount, amount)

    def _interval(self):
        base = self.options.get("interval_ms", 100)
        amount = self.options.get("interval_jitter_ms", 0)
        if amount <= 0:
            return max(0, base) / 1000.0
        return max(0, base + random.randint(-amount, amount)) / 1000.0

    def run(self):
        if self.is_loop and self.loop_spec.get("mode") == "count":
            total = self.total_actions * max(
                1, int(self.loop_spec.get("count", 1)))
        else:
            total = self.total_actions
        self.out.put(("start", {"id": self.run_id, "total": total}))
        mode = self.loop_spec.get("mode", "none") if self.is_loop else "none"
        if mode == "count":
            self._run_loop_count()
        elif mode == "seconds":
            self._run_loop_seconds()
        else:
            reason, message = self._execute_once()
            self._finish(reason, message)

    def _finish(self, reason, message):
        self.out.put(("finished", {
            "reason": reason, "id": self.run_id,
            "done": self.done_count, "message": message,
        }))

    def _execute_once(self):
        reason = "completed"
        message = ""
        try:
            for seg_index, task in enumerate(self.tasks):
                if not self._ready():
                    reason = "stopped"
                    break
                expected = str(task.get("expected", "") or "")
                fail_mode = str(task.get("ocr_fail", "stop") or "stop")
                skip_this_task = False
                if task.get("ocr_check", False) and expected.strip():
                    self.out.put(("ocr_scan", {
                        "id": self.run_id, "seg": seg_index}))
                    try:
                        recognized = self._ocr_region_text(task)
                    except Exception as exc:
                        recognized = f"OCR 失败：{exc}"
                    matched = text_matches(expected, recognized)
                    if not matched:
                        if fail_mode == "skip":
                            skip_this_task = True
                            self.out.put(("ocr_skip", {
                                "id": self.run_id, "seg": seg_index}))
                        elif fail_mode == "pass":
                            pass
                        else:
                            reason = "ocr_mismatch"
                            message = (
                                f"任务 {seg_index + 1} 校验区域文字不符：\n"
                                f"期望：{expected}\n"
                                f"识别：{recognized or '（空）'}"
                            )
                            break
                if skip_this_task:
                    continue

                if task.get("type") == "wheel":
                    ok = self._run_wheel(seg_index, task)
                else:
                    ok = self._run_click(seg_index, task)
                if not ok:
                    reason = "stopped"
                    break
                if seg_index + 1 < len(self.tasks):
                    if not self._sleep_ok(self._effective_interval(task)):
                        reason = "stopped"
                        break
        except Exception as exc:
            reason = "error"
            message = f"{type(exc).__name__}: {exc}"
        return reason, message

    def _run_loop_count(self):
        count = max(1, int(self.loop_spec.get("count", 1)))
        interval = max(0, int(self.loop_spec.get("interval_ms", 0))) / 1000.0
        reason, message = "completed", ""
        for iteration in range(count):
            if not self._ready():
                reason = "stopped"
                break
            reason, message = self._execute_once()
            if reason != "completed":
                break
            if iteration + 1 < count:
                if not self._sleep_ok(interval):
                    reason = "stopped"
                    break
        self._finish(reason, message)

    def _run_loop_seconds(self):
        seconds = max(1, int(self.loop_spec.get("seconds", 1)))
        interval = max(0, int(self.loop_spec.get("interval_ms", 0))) / 1000.0
        start = time.monotonic()
        reason, message = "completed", ""
        while time.monotonic() - start < seconds:
            if not self._ready():
                reason = "stopped"
                break
            reason, message = self._execute_once()
            if reason != "completed":
                break
            if time.monotonic() - start < seconds and not self._sleep_ok(interval):
                reason = "stopped"
                break
        self._finish(reason, message)

    def _ocr_region_text(self, task):
        x = task["x"]
        y = task["y"]
        if task.get("use_cursor"):
            x, y = get_cursor_pos()
        box = task.get("ocr_box")
        if isinstance(box, dict) and box.get("dx2") is not None:
            x1 = x + int(box["dx1"])
            y1 = y + int(box["dy1"])
            x2 = x + int(box["dx2"])
            y2 = y + int(box["dy2"])
            return ocr_box_region(x1, y1, x2, y2)
        width = int(self.options.get("ocr_width", 220))
        height = int(self.options.get("ocr_height", 64))
        return ocr_region(x, y, width, height)

    def _run_click(self, seg_index, task) -> bool:
        jitter = self.options.get("xy_jitter", 0)
        button = task.get("button", "left")
        total = task.get("count", 1)
        for index in range(total):
            if index > 0 and not self._sleep_ok(self._effective_interval(task)):
                return False
            if not self._ready():
                return False
            if task.get("use_cursor"):
                send_click(button)
            else:
                x = self._jitter(task["x"], jitter)
                y = self._jitter(task["y"], jitter)
                if set_cursor_pos(x, y):
                    send_click(button)
            self.done_count += 1
            self.out.put(("progress", {
                "id": self.run_id,
                "seg": seg_index,
                "done": self.done_count,
            }))
        return True

    def _run_wheel(self, seg_index, task) -> bool:
        jitter = self.options.get("xy_jitter", 0)
        direction = task.get("direction", "向上")
        notches = max(1, int(task.get("notches", 1)))
        total = task.get("count", 1)
        for index in range(total):
            if index > 0 and not self._sleep_ok(self._effective_interval(task)):
                return False
            if not self._ready():
                return False
            if task.get("use_cursor"):
                send_wheel(direction, notches)
            else:
                x = self._jitter(task["x"], jitter)
                y = self._jitter(task["y"], jitter)
                if set_cursor_pos(x, y):
                    send_wheel(direction, notches)
            self.done_count += 1
            self.out.put(("progress", {
                "id": self.run_id,
                "seg": seg_index,
                "done": self.done_count,
            }))
        return True

    def _effective_interval(self, task):
        base = int(task.get("interval_ms") or 0)
        amount = self.options.get("interval_jitter_ms", 0)
        if base <= 0:
            base = self.options.get("interval_ms", 100)
        if amount <= 0:
            return max(0, base) / 1000.0
        return max(0, base + random.randint(-amount, amount)) / 1000.0


# ---------------------------------------------------------------------------
# 界面
# ---------------------------------------------------------------------------
def _blend(c1, c2, t):
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


class ClickerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self._events = queue.Queue()
        self._state = "idle"
        self.presets = [
            {
                "name": f"预设{i + 1}", "tasks": [],
                "loop": {"mode": "none", "count": 10,
                         "seconds": 10, "interval_ms": 1000},
            } for i in range(6)
        ] + [{
            "name": "触发预设7", "tasks": [], "trigger": "mouse_left",
            "loop": {"mode": "none", "count": 10,
                     "seconds": 10, "interval_ms": 1000},
        }]
        self._preset_index = 0
        self._runtime_index = None
        self._manual_exit = False
        self._special_mode = False
        self._trigger_monitor = None
        self._number_monitor = None
        self._loop_active = False
        self._loop_preset_index = None
        self._tasks = self.presets[0]["tasks"]
        self._worker = None
        self._run_id = 0
        self._run_done = 0
        self._run_total = 0
        self._current_seg = None
        self._pick_mode = False
        self._single_pick_after = None
        self._overlay = None
        self._overlay_labels = []
        self._anim_pos = 0
        self._anim_dir = 1
        self._dot_phase = 0
        self._header_w = 1
        self._box = None            # 图形化框选的相对范围
        self._box_anchor = None

        self.type_var = tk.StringVar(value="点击")
        self.x_var = tk.StringVar(value="")
        self.y_var = tk.StringVar(value="")
        self.cursor_var = tk.BooleanVar(value=False)
        self.count_var = tk.StringVar(value="1")
        self.button_var = tk.StringVar(value=CLICK_BUTTONS[0][0])
        self.direction_var = tk.StringVar(value=SCROLL_DIRECTIONS[0])
        self.notches_var = tk.StringVar(value="3")
        self.expected_var = tk.StringVar(value="")
        self.interval_var = tk.StringVar(value="100")
        self.interval_jitter_var = tk.StringVar(value="0")
        self.xy_jitter_var = tk.StringVar(value="0")
        self.ocr_width_var = tk.StringVar(value="220")
        self.ocr_height_var = tk.StringVar(value="64")
        self.box_var = tk.StringVar(value="OCR 范围：自动（以点击点为中心）")
        self.preset_name_var = tk.StringVar(value="预设1")
        self.task_interval_var = tk.StringVar(value="0")
        self.task_ocr_var = tk.BooleanVar(value=False)
        self.ocr_fail_var = tk.StringVar(value=OCR_FAIL_CHOICES[0][0])
        self.trigger_var = tk.StringVar(value=TRIGGER_CHOICES[0][0])
        self.double_edit_var = tk.BooleanVar(value=True)
        self.loop_mode_var = tk.StringVar(value="不循环")
        self.loop_count_var = tk.StringVar(value="10")
        self.loop_seconds_var = tk.StringVar(value="10")
        self.loop_interval_var = tk.StringVar(value="1000")
        self.status_var = tk.StringVar(
            value="就绪：按 F8 进入监听，再按 1~6 选择预设运行")
        self.summary_var = tk.StringVar(value="0 个任务 · 0 次动作")

        self._setup_style()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Key>", self._on_local_key)
        self._build_overlay()
        self._load_presets_file()
        self._sync_preset_ui(init=True)

        self._hotkey = HotkeyThread(self._events)
        self._hotkey.start()
        self.root.after(80, self._poll_events)
        self._animate()

    # --------------------------- 样式 ---------------------------
    def _setup_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 9))
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Card.TLabel", background=PANEL, foreground=FG)
        style.configure("Card.TLabelframe", background=PANEL,
                        bordercolor="#dce5f0", relief="flat")
        style.configure("Card.TLabelframe.Label", background=PANEL,
                        foreground=ACCENT,
                        font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("TButton", background="#e8eef7", foreground=FG,
                        bordercolor="#d2dceb", focusthickness=0,
                        padding=(8, 4), relief="flat")
        style.map("TButton",
                  background=[("active", "#d7e4f5"), ("pressed", "#c3d5ee")],
                  bordercolor=[("active", "#9fb9de")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#fff",
                        bordercolor=ACCENT, padding=(11, 5),
                        font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Accent.TButton",
                  background=[("active", "#1f6ef0"), ("pressed", "#175fc9")])
        style.configure("Success.TButton", background=GREEN, foreground="#fff",
                        bordercolor=GREEN, padding=(12, 6),
                        font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Success.TButton",
                  background=[("active", "#138653"), ("pressed", "#0e6b43")])
        style.configure("Warn.TButton", background=AMBER, foreground="#fff",
                        bordercolor=AMBER, padding=(10, 5))
        style.map("Warn.TButton",
                  background=[("active", "#d89427"), ("pressed", "#c07d18")])
        style.configure("Danger.TButton", background=RED, foreground="#fff",
                        bordercolor=RED, padding=(10, 5))
        style.map("Danger.TButton",
                  background=[("active", "#d63c41"), ("pressed", "#bd2f34")])
        style.configure("TCheckbutton", background=PANEL, foreground=FG,
                        focuscolor=PANEL)
        style.map("TCheckbutton", background=[("active", PANEL)])
        style.configure("Treeview", background="#fff", fieldbackground="#fff",
                        foreground=FG, rowheight=27, bordercolor="#d8e1ec")
        style.map("Treeview", background=[("selected", "#cfe3ff")],
                  foreground=[("selected", FG)])
        style.configure("Treeview.Heading", background="#e9eff7",
                        foreground="#33475f", relief="flat",
                        font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Treeview.Heading", background=[("active", "#dde7f3")])
        style.configure("TSpinbox", arrowsize=12, padding=2,
                        fieldbackground="#fff")
        style.configure("TCombobox", padding=2, fieldbackground="#fff")
        self.root.configure(bg=BG)

    # --------------------------- 界面 ---------------------------
    def _build_ui(self):
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = min(1280, max(980, sw - 50))
        h = min(800, max(640, sh - 110))
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(1020, 640)

        self.header = tk.Canvas(self.root, height=48, highlightthickness=0, bd=0)
        self.header.pack(fill="x")
        self.header.bind("<Configure>", lambda _e: self._paint_header())

        self.anim_bar = tk.Canvas(self.root, height=4, highlightthickness=0,
                                  bd=0, bg=BG)
        self.anim_bar.pack(fill="x")
        self._bar_item = self.anim_bar.create_rectangle(
            0, 0, 130, 4, fill="#b9d3fa", outline="",
        )

        outer = ttk.Frame(self.root, padding=(10, 6))
        outer.pack(fill="both", expand=True)

        # 预设 1~6
        preset_frame = ttk.LabelFrame(
            outer, text=" 预设配置（F8 后按 1~6 选普通预设，7 进入触发预设） ",
            style="Card.TLabelframe", padding=(9, 5),
        )
        preset_frame.pack(fill="x", pady=(0, 5))
        preset_row = ttk.Frame(preset_frame, style="Card.TFrame")
        preset_row.pack(fill="x")
        self.preset_buttons = []
        for i in range(7):
            btn = ttk.Button(
                preset_row, text=f"{i + 1} 预设{i + 1}",
                command=lambda idx=i: self._select_preset(idx),
            )
            btn.pack(side="left", padx=(0, 4))
            self.preset_buttons.append(btn)
        ttk.Label(preset_row, text="名称", style="Card.TLabel").pack(
            side="left", padx=(8, 3))
        self.ent_preset_name = ttk.Entry(
            preset_row, textvariable=self.preset_name_var, width=18)
        self.ent_preset_name.pack(side="left", padx=(0, 5))
        self.btn_rename = ttk.Button(preset_row, text="保存名称",
                                     command=self._save_preset_name)
        self.btn_rename.pack(side="left", padx=(0, 8))
        self.lbl_trigger = ttk.Label(
            preset_row, text="触发键", style="Card.TLabel")
        self.lbl_trigger.pack(side="left", padx=(0, 3))
        self.combo_trigger = ttk.Combobox(
            preset_row, textvariable=self.trigger_var,
            values=[label for label, _ in TRIGGER_CHOICES],
            state="readonly", width=9,
        )
        self.combo_trigger.pack(side="left", padx=(0, 12))
        self.chk_double_edit = ttk.Checkbutton(
            preset_row, text="双击任务直接编辑并自动保存",
            variable=self.double_edit_var)
        self.chk_double_edit.pack(side="left")

        loop_row = ttk.Frame(preset_frame, style="Card.TFrame")
        loop_row.pack(fill="x", pady=(4, 0))
        ttk.Label(loop_row, text="循环模式", style="Card.TLabel").pack(side="left")
        self.combo_loop_mode = ttk.Combobox(
            loop_row, textvariable=self.loop_mode_var,
            values=[label for label, _ in LOOP_MODES],
            state="readonly", width=9)
        self.combo_loop_mode.bind("<<ComboboxSelected>>",
                                  lambda _e: self._refresh_loop_ui())
        self.combo_loop_mode.pack(side="left", padx=(2, 8))
        self.lbl_loop_count = ttk.Label(loop_row, text="次数",
                                        style="Card.TLabel")
        self.lbl_loop_count.pack(side="left")
        self.spin_loop_count = ttk.Spinbox(
            loop_row, from_=1, to=999999, increment=1,
            textvariable=self.loop_count_var, width=7, justify="center")
        self.spin_loop_count.pack(side="left", padx=(2, 10))
        self.lbl_loop_seconds = ttk.Label(loop_row, text="时长秒",
                                          style="Card.TLabel")
        self.lbl_loop_seconds.pack(side="left")
        self.spin_loop_seconds = ttk.Spinbox(
            loop_row, from_=1, to=99999, increment=1,
            textvariable=self.loop_seconds_var, width=6, justify="center")
        self.spin_loop_seconds.pack(side="left", padx=(2, 10))
        ttk.Label(loop_row, text="循环间隔ms",
                  style="Card.TLabel").pack(side="left")
        self.spin_loop_interval = ttk.Spinbox(
            loop_row, from_=0, to=600000, increment=100,
            textvariable=self.loop_interval_var, width=7, justify="center")
        self.spin_loop_interval.pack(side="left", padx=(2, 10))
        ttk.Label(
            loop_row, text="短按1~7=执行一次；长按/Ctrl+数字=按此循环设置运行；循环中按Esc或再按同数字取消",
            style="Card.TLabel", foreground=MUTED).pack(side="left")

        # ① 任务配置
        cfg = ttk.LabelFrame(outer, text=" 任务配置 ", style="Card.TLabelframe",
                             padding=(9, 6))
        cfg.pack(fill="x", pady=(0, 5))

        row0 = ttk.Frame(cfg, style="Card.TFrame")
        row0.pack(fill="x")
        ttk.Label(row0, text="类型", style="Card.TLabel").pack(side="left")
        self.combo_type = ttk.Combobox(row0, textvariable=self.type_var,
                                       values=("点击", "滚轮"),
                                       state="readonly", width=5)
        self.combo_type.pack(side="left", padx=(2, 8))
        self.combo_type.bind("<<ComboboxSelected>>",
                             lambda _e: self._refresh_type_ui())

        ttk.Label(row0, text="X", style="Card.TLabel").pack(side="left")
        self.ent_x = ttk.Entry(row0, textvariable=self.x_var, width=7,
                               justify="center")
        self.ent_x.pack(side="left", padx=(2, 7))
        ttk.Label(row0, text="Y", style="Card.TLabel").pack(side="left")
        self.ent_y = ttk.Entry(row0, textvariable=self.y_var, width=7,
                               justify="center")
        self.ent_y.pack(side="left", padx=(2, 8))
        self.chk_cursor = ttk.Checkbutton(
            row0, text="当前鼠标位置", variable=self.cursor_var,
            command=self._refresh_cursor_ui)
        self.chk_cursor.pack(side="left", padx=(0, 8))

        ttk.Label(row0, text="次数", style="Card.TLabel").pack(side="left")
        self.spin_count = ttk.Spinbox(row0, from_=1, to=999999, increment=1,
                                      textvariable=self.count_var, width=5,
                                      justify="center")
        self.spin_count.pack(side="left", padx=(2, 8))

        self.lbl_button = ttk.Label(row0, text="按键", style="Card.TLabel")
        self.lbl_button.pack(side="left")
        self.combo_button = ttk.Combobox(row0, textvariable=self.button_var,
                                         values=[c[0] for c in CLICK_BUTTONS],
                                         state="readonly", width=8)
        self.combo_button.pack(side="left", padx=(2, 8))

        self.lbl_direction = ttk.Label(row0, text="方向", style="Card.TLabel")
        self.lbl_direction.pack(side="left")
        self.combo_direction = ttk.Combobox(
            row0, textvariable=self.direction_var, values=SCROLL_DIRECTIONS,
            state="readonly", width=5,
        )
        self.combo_direction.pack(side="left", padx=(2, 8))
        self.lbl_notches = ttk.Label(row0, text="格数/次", style="Card.TLabel")
        self.lbl_notches.pack(side="left")
        self.spin_notches = ttk.Spinbox(row0, from_=1, to=100, increment=1,
                                        textvariable=self.notches_var, width=5,
                                        justify="center")
        self.spin_notches.pack(side="left", padx=(2, 8))
        ttk.Label(row0, text="（滚轮：鼠标先移到该坐标再滚动）",
                  style="Card.TLabel", foreground=MUTED).pack(side="left")

        row1 = ttk.Frame(cfg, style="Card.TFrame")
        row1.pack(fill="x", pady=(5, 0))
        self.btn_pick = ttk.Button(row1, text="单点拾取(3s)",
                                   command=self._single_pick)
        self.btn_pick.pack(side="left", padx=(0, 6))
        self.btn_ocr_now = ttk.Button(row1, text="识别当前文字",
                                      command=self._ocr_into_field)
        self.btn_ocr_now.pack(side="left", padx=(0, 8))
        ttk.Label(row1, text="OCR预期文字(可编辑)", style="Card.TLabel").pack(side="left")
        self.ent_expected = ttk.Entry(row1, textvariable=self.expected_var, width=28)
        self.ent_expected.pack(side="left", padx=(2, 8))
        self.btn_box = ttk.Button(row1, text="图形框选OCR范围",
                                  style="Accent.TButton", command=self._graphical_ocr_box)
        self.btn_box.pack(side="left", padx=(0, 5))
        self.btn_box_clear = ttk.Button(row1, text="清除范围",
                                        command=self._clear_ocr_box)
        self.btn_box_clear.pack(side="left", padx=(0, 6))
        ttk.Label(row1, textvariable=self.box_var, style="Card.TLabel",
                  foreground=MUTED).pack(side="left")

        row2 = ttk.Frame(cfg, style="Card.TFrame")
        row2.pack(fill="x", pady=(5, 0))
        ttk.Label(row2, text="本任务间隔ms", style="Card.TLabel").pack(side="left")
        self.spin_task_interval = ttk.Spinbox(
            row2, from_=0, to=600000, increment=10,
            textvariable=self.task_interval_var, width=6, justify="center",
        )
        self.spin_task_interval.pack(side="left", padx=(2, 5))
        ttk.Label(row2, text="（0=使用全局间隔）", style="Card.TLabel",
                  foreground=MUTED).pack(side="left", padx=(0, 10))
        self.chk_task_ocr = ttk.Checkbutton(
            row2, text="本任务 OCR 校验", variable=self.task_ocr_var)
        self.chk_task_ocr.pack(side="left", padx=(0, 12))
        ttk.Label(row2, text="不匹配/失败时", style="Card.TLabel").pack(side="left")
        self.combo_ocr_fail = ttk.Combobox(
            row2, textvariable=self.ocr_fail_var,
            values=[label for label, _ in OCR_FAIL_CHOICES],
            state="readonly", width=11,
        )
        self.combo_ocr_fail.pack(side="left", padx=(3, 8))
        ttk.Label(row2, text="勾选并填写预期文字后，执行该任务前先 OCR 校验",
                  style="Card.TLabel", foreground=MUTED).pack(side="left")

        # ② 任务列表
        task_frame = ttk.LabelFrame(outer, text=" 任务列表（按顺序执行） ",
                                    style="Card.TLabelframe", padding=(8, 5))
        task_frame.pack(fill="both", expand=True, pady=(0, 5))

        btn_row = ttk.Frame(task_frame, style="Card.TFrame")
        btn_row.pack(fill="x", pady=(0, 4))
        self.btn_add = ttk.Button(btn_row, text="＋ 添加任务",
                                  style="Accent.TButton", command=self._add_task)
        self.btn_add.pack(side="left", padx=(0, 4))
        self.btn_update = ttk.Button(btn_row, text="修改选中",
                                     command=self._update_selected)
        self.btn_update.pack(side="left", padx=(0, 4))
        self.btn_delete = ttk.Button(btn_row, text="删除",
                                     command=self._delete_selected)
        self.btn_delete.pack(side="left", padx=(0, 4))
        self.btn_clear = ttk.Button(btn_row, text="清空",
                                    command=self._clear_tasks)
        self.btn_clear.pack(side="left", padx=(0, 8))
        self.btn_up = ttk.Button(btn_row, text="↑ 上移",
                                 command=lambda: self._move_selected(-1))
        self.btn_up.pack(side="left", padx=(0, 4))
        self.btn_down = ttk.Button(btn_row, text="↓ 下移",
                                   command=lambda: self._move_selected(1))
        self.btn_down.pack(side="left", padx=(0, 8))
        self.btn_import = ttk.Button(btn_row, text="导入配置",
                                     command=self._import_config)
        self.btn_import.pack(side="left", padx=(0, 4))
        self.btn_export = ttk.Button(btn_row, text="导出配置",
                                     command=self._export_config)
        self.btn_export.pack(side="left", padx=(0, 8))
        self.btn_pick_mode = ttk.Button(btn_row, text="连续拾取模式",
                                        style="Warn.TButton",
                                        command=self._toggle_pick_mode)
        self.btn_pick_mode.pack(side="left", padx=(0, 8))
        ttk.Label(btn_row, textvariable=self.summary_var, style="Card.TLabel",
                  foreground=MUTED).pack(side="right")

        tree_wrap = ttk.Frame(task_frame, style="Card.TFrame")
        tree_wrap.pack(fill="both", expand=True)
        columns = ("no", "type", "x", "y", "count", "param", "interval", "ocr")
        self.tree = ttk.Treeview(tree_wrap, columns=columns, show="headings",
                                 height=5, selectmode="browse")
        headers = {"no": "序号", "type": "类型", "x": "坐标X", "y": "坐标Y",
                   "count": "次数", "param": "方式/参数", "interval": "间隔ms",
                   "ocr": "OCR 预期文字"}
        widths = {"no": 42, "type": 50, "x": 72, "y": 72, "count": 50,
                  "param": 105, "interval": 60, "ocr": 220}
        for col in columns:
            self.tree.heading(col, text=headers[col])
            self.tree.column(col, width=widths[col], minwidth=widths[col],
                             anchor="center", stretch=(col == "ocr"))
        self.tree.pack(side="left", fill="both", expand=True)
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        vsb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.tag_configure("current", background="#cde6ff")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._load_selection())
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        # 线性流程图
        flow_frame = ttk.LabelFrame(
            task_frame,
            text=" 流程预览（单击选任务 / 拖动调顺序 / 双击直接编辑） ",
            style="Card.TLabelframe", padding=(5, 3),
        )
        flow_frame.pack(fill="x", pady=(5, 0))
        flow_inner = ttk.Frame(flow_frame, style="Card.TFrame")
        flow_inner.pack(fill="x")
        self.flow_canvas = tk.Canvas(
            flow_inner, height=68, bg="#ffffff", highlightthickness=1,
            highlightbackground="#d8e1ec", bd=0,
        )
        self.flow_canvas.pack(side="top", fill="x")
        hsb = ttk.Scrollbar(
            flow_inner, orient="horizontal", command=self.flow_canvas.xview)
        hsb.pack(side="bottom", fill="x")
        self.flow_canvas.configure(xscrollcommand=hsb.set)
        self.flow_canvas.bind("<ButtonPress-1>", self._flow_press)
        self.flow_canvas.bind("<ButtonRelease-1>", self._flow_release)
        self.flow_canvas.bind("<Double-1>", self._flow_double)
        self.flow_canvas.bind("<Configure>", lambda _e: self._refresh_flow())

        # ③ 运行选项
        opt = ttk.LabelFrame(outer, text=" 运行选项与 OCR ", style="Card.TLabelframe",
                             padding=(9, 5))
        opt.pack(fill="x", pady=(0, 5))
        opt_row = ttk.Frame(opt, style="Card.TFrame")
        opt_row.pack(fill="x")
        ttk.Label(opt_row, text="间隔ms", style="Card.TLabel").pack(side="left")
        self.spin_interval = ttk.Spinbox(opt_row, from_=0, to=600000,
                                         increment=10,
                                         textvariable=self.interval_var,
                                         width=6, justify="center")
        self.spin_interval.pack(side="left", padx=(2, 5))
        ttk.Label(opt_row, text="±随机ms", style="Card.TLabel",
                  foreground=MUTED).pack(side="left")
        self.spin_interval_jitter = ttk.Spinbox(
            opt_row, from_=0, to=600000, increment=1,
            textvariable=self.interval_jitter_var, width=5, justify="center")
        self.spin_interval_jitter.pack(side="left", padx=(2, 12))
        ttk.Label(opt_row, text="坐标±px", style="Card.TLabel").pack(side="left")
        self.spin_xy_jitter = ttk.Spinbox(opt_row, from_=0, to=500, increment=1,
                                          textvariable=self.xy_jitter_var,
                                          width=5, justify="center")
        self.spin_xy_jitter.pack(side="left", padx=(2, 12))
        ttk.Label(opt_row, text="自动区域", style="Card.TLabel",
                  foreground=MUTED).pack(side="left")
        self.spin_ocr_w = ttk.Spinbox(opt_row, from_=40, to=800, increment=10,
                                      textvariable=self.ocr_width_var, width=5,
                                      justify="center")
        self.spin_ocr_w.pack(side="left", padx=(2, 2))
        ttk.Label(opt_row, text="×", style="Card.TLabel").pack(side="left")
        self.spin_ocr_h = ttk.Spinbox(opt_row, from_=20, to=400, increment=10,
                                      textvariable=self.ocr_height_var, width=5,
                                      justify="center")
        self.spin_ocr_h.pack(side="left", padx=(2, 2))
        ttk.Label(opt_row, text="px（未图形框选时使用；OCR 由各任务独立开关）",
                  style="Card.TLabel", foreground=MUTED).pack(side="left")

        # ④ 运行区
        run = ttk.Frame(outer, style="Card.TFrame", padding=(10, 6))
        run.pack(fill="x")
        self.btn_go = ttk.Button(run, text="启动监听 (F8)", width=16,
                                 style="Success.TButton", command=self._on_f8)
        self.btn_go.pack(side="left", padx=(0, 6))
        self.btn_exit = ttk.Button(run, text="退出 (F8/Esc)", width=14,
                                   style="Danger.TButton",
                                   command=self._exit_runtime)
        self.btn_exit.pack(side="left")
        self.dot = tk.Label(run, text="●", fg="#c7d3e3", bg=PANEL,
                            font=("Microsoft YaHei UI", 10))
        self.dot.pack(side="left", padx=(12, 3))
        self.lbl_status = tk.Label(run, textvariable=self.status_var, anchor="w",
                                   fg=GREEN, bg="#f2f7f4", relief="groove",
                                   bd=1, padx=8, pady=2)
        self.lbl_status.pack(side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(
            run, orient="horizontal", length=150, maximum=100, mode="determinate",
        )
        self.progress.pack(side="right", padx=(8, 0))
        self.lbl_percent = ttk.Label(run, text="0%", width=5, anchor="e")
        self.lbl_percent.pack(side="right", padx=(0, 2))

        self._edit_widgets = [
            self.ent_x, self.ent_y, self.spin_count, self.spin_interval,
            self.spin_interval_jitter, self.spin_xy_jitter, self.spin_ocr_w,
            self.spin_ocr_h, self.spin_notches, self.combo_type,
            self.combo_button, self.combo_direction, self.ent_expected,
            self.chk_cursor,
            self.spin_task_interval, self.chk_task_ocr,
            self.combo_ocr_fail,
            self.combo_loop_mode, self.spin_loop_count,
            self.spin_loop_seconds, self.spin_loop_interval,
            self.btn_add, self.btn_update, self.btn_delete, self.btn_clear,
            self.btn_up, self.btn_down, self.btn_import, self.btn_export,
            self.btn_pick, self.btn_ocr_now,
            self.btn_box, self.btn_box_clear,
        ]
        self._refresh_type_ui()
        self._refresh_controls()

    # --------------------------- 动效 ---------------------------
    def _paint_header(self):
        w = self.header.winfo_width()
        h = self.header.winfo_height()
        if w < 10 or h < 10 or w == self._header_w:
            return
        self._header_w = w
        self.header.delete("all")
        for i in range(0, w, 2):
            self.header.create_line(
                i, 0, i, h, fill=_blend("#2563eb", "#60a5fa", i / max(1, w)),
            )
        self.header.create_text(18, h / 2, anchor="w",
                                text=f"{APP_NAME}  v{APP_VERSION}",
                                fill="#ffffff",
                                font=("Microsoft YaHei UI", 15, "bold"))
        self.header.create_text(w - 18, h / 2, anchor="e",
                                text="点击 · 滚轮 · OCR图形框选 · 配置导入导出",
                                fill="#e7f0ff",
                                font=("Microsoft YaHei UI", 9))

    def _animate(self):
        color = {"idle": "#cbd9e9", "running": ACCENT,
                 "listening": AMBER, "armed": RED}.get(self._state, "#cbd9e9")
        bar_w = 130 if self._state == "idle" else 160
        max_x = max(10, self.anim_bar.winfo_width() - bar_w)
        if self._state == "running":
            self._anim_pos += 4 * self._anim_dir
            if self._anim_pos >= max_x:
                self._anim_pos = max_x
                self._anim_dir = -1
            elif self._anim_pos <= 0:
                self._anim_pos = 0
                self._anim_dir = 1
        self.anim_bar.coords(self._bar_item, self._anim_pos, 0,
                             self._anim_pos + bar_w, 4)
        self.anim_bar.itemconfigure(self._bar_item, fill=color)
        if self._state == "running":
            self._dot_phase += 1
            colors = [ACCENT, "#5b95f8", "#8ab4fb", "#b5d1fd"]
            self.dot.configure(fg=colors[self._dot_phase % len(colors)])
        else:
            self.dot.configure(
                fg=AMBER if self._state == "listening"
                else RED if self._state == "armed" else "#c7d3e3")
        self.root.after(16, self._animate)

    # --------------------------- 类型切换 ---------------------------
    def _refresh_type_ui(self):
        is_wheel = self.type_var.get() == "滚轮"
        if self._state != "idle":
            self.lbl_direction.configure(state="disabled")
            self.combo_direction.configure(state="disabled")
            self.lbl_notches.configure(state="disabled")
            self.spin_notches.configure(state="disabled")
            self.lbl_button.configure(state="disabled")
            self.combo_button.configure(state="disabled")
            return
        if self._pick_mode:
            self.lbl_direction.configure(state="normal")
            self.combo_direction.configure(
                state="readonly" if is_wheel else "normal")
            self.lbl_notches.configure(state="normal")
            self.spin_notches.configure(state="normal")
            self.lbl_button.configure(state="normal")
            self.combo_button.configure(
                state="readonly" if not is_wheel else "normal")
            return
        self.lbl_direction.configure(state="normal" if is_wheel else "disabled")
        self.combo_direction.configure(
            state="readonly" if is_wheel else "disabled")
        self.lbl_notches.configure(state="normal" if is_wheel else "disabled")
        self.spin_notches.configure(state="normal" if is_wheel else "disabled")
        self.lbl_button.configure(state="normal" if not is_wheel else "disabled")
        self.combo_button.configure(
            state="readonly" if not is_wheel else "disabled")

    def _refresh_trigger_ui(self):
        can_edit = (self._state == "idle" and not self._pick_mode
                    and self._preset_index == 6)
        state = "normal" if can_edit else "disabled"
        self.lbl_trigger.configure(state=state)
        self.combo_trigger.configure(
            state="readonly" if can_edit else "disabled")

    def _refresh_cursor_ui(self):
        if self.cursor_var.get():
            self.ent_x.configure(state="disabled")
            self.ent_y.configure(state="disabled")
            self._box = None
            self._refresh_box_label()
            self.btn_box.configure(state="disabled")
        else:
            if self._state == "idle" and not self._pick_mode:
                self.ent_x.configure(state="normal")
                self.ent_y.configure(state="normal")
            if self._state == "idle":
                self.btn_box.configure(state="normal")

    def _refresh_loop_ui(self):
        can_edit = self._state == "idle" and not self._pick_mode
        mode = "none"
        for label, code in LOOP_MODES:
            if label == self.loop_mode_var.get():
                mode = code
        base = "normal" if can_edit else "disabled"
        self.combo_loop_mode.configure(
            state="readonly" if can_edit else "disabled")
        count_state = base if mode == "count" else "disabled"
        sec_state = base if mode == "seconds" else "disabled"
        self.lbl_loop_count.configure(state=count_state)
        self.spin_loop_count.configure(state=count_state)
        self.lbl_loop_seconds.configure(state=sec_state)
        self.spin_loop_seconds.configure(state=sec_state)
        self.spin_loop_interval.configure(
            state=base if mode != "none" else "disabled")

    # --------------------------- 任务编辑 ---------------------------
    def _parse_task(self):
        task_type = self.type_var.get()
        use_cursor = bool(self.cursor_var.get())
        if use_cursor:
            x = y = 0
        else:
            try:
                x = int(self.x_var.get().strip())
                y = int(self.y_var.get().strip())
            except ValueError:
                raise ValueError("坐标 X/Y 必须是整数")
        try:
            count = int(self.count_var.get().strip())
        except ValueError:
            raise ValueError("次数必须是整数")
        if count < 1:
            raise ValueError("次数必须 ≥ 1")
        expected = self.expected_var.get().strip()
        box = None
        if self._box:
            box = copy.deepcopy(self._box)
        try:
            task_interval = int(self.task_interval_var.get().strip())
        except ValueError:
            raise ValueError("本任务间隔必须是整数")
        if task_interval < 0:
            raise ValueError("本任务间隔不能为负数")
        task_ocr = bool(self.task_ocr_var.get())
        ocr_fail = "stop"
        for label, code in OCR_FAIL_CHOICES:
            if label == self.ocr_fail_var.get():
                ocr_fail = code
                break

        if task_type == "滚轮":
            direction = self.direction_var.get()
            if direction not in SCROLL_DIRECTIONS:
                direction = "向上"
            try:
                notches = int(self.notches_var.get().strip())
            except ValueError:
                raise ValueError("滚轮格数必须是整数")
            if notches < 1:
                raise ValueError("滚轮格数必须 ≥ 1")
            return {
                "type": "wheel", "x": x, "y": y, "count": count,
                "direction": direction, "notches": notches,
                "expected": expected, "ocr_box": box,
                "interval_ms": task_interval, "ocr_check": task_ocr,
                "ocr_fail": ocr_fail, "use_cursor": use_cursor,
            }

        label = self.button_var.get()
        button = "left"
        for name, code in CLICK_BUTTONS:
            if name == label:
                button = code
                break
        return {
            "type": "click", "x": x, "y": y, "count": count,
            "button": button, "expected": expected, "ocr_box": box,
            "interval_ms": task_interval, "ocr_check": task_ocr,
            "ocr_fail": ocr_fail, "use_cursor": use_cursor,
        }

    def _load_task_into_fields(self, task):
        self.type_var.set("滚轮" if task.get("type") == "wheel" else "点击")
        cursor_mode = bool(task.get("use_cursor", False))
        self.cursor_var.set(cursor_mode)
        self.x_var.set(str(task.get("x", 0)))
        self.y_var.set(str(task.get("y", 0)))
        self.count_var.set(str(task.get("count", 1)))
        if task.get("type") == "wheel":
            self.direction_var.set(task.get("direction", "向上"))
            self.notches_var.set(str(task.get("notches", 1)))
        else:
            for name, code in CLICK_BUTTONS:
                if code == task.get("button", "left"):
                    self.button_var.set(name)
                    break
        self.expected_var.set(task.get("expected", ""))
        self.task_interval_var.set(str(task.get("interval_ms") or 0))
        self.task_ocr_var.set(bool(task.get("ocr_check", False)))
        fail = task.get("ocr_fail", "stop")
        self.ocr_fail_var.set(
            next((label for label, code in OCR_FAIL_CHOICES if code == fail),
                 OCR_FAIL_CHOICES[0][0]))
        self._box = copy.deepcopy(task.get("ocr_box")) if isinstance(
            task.get("ocr_box"), dict) else None
        self._box_anchor = None
        self._refresh_box_label()
        self._refresh_type_ui()
        self._refresh_cursor_ui()

    def _add_task(self, x=None, y=None, source_mode=False):
        if x is not None and y is not None:
            old_x, old_y = self.x_var.get(), self.y_var.get()
            self.x_var.set(str(x))
            self.y_var.set(str(y))
        try:
            task = self._parse_task()
        except ValueError as exc:
            messagebox.showerror("输入有误", str(exc), parent=self.root)
            return None
        finally:
            if x is not None and y is not None:
                self.x_var.set(old_x)
                self.y_var.set(old_y)
        self._tasks.append(task)
        self._rebuild_tasks()
        self._save_presets_file()
        return len(self._tasks) - 1

    def _rebuild_tasks(self):
        self.tree.delete(*self.tree.get_children())
        total = sum(t.get("count", 1) for t in self._tasks)
        for index, task in enumerate(self._tasks):
            if task.get("type") == "wheel":
                kind = "滚轮"
                param = f"{task.get('direction', '向上')} × {task.get('notches', 1)} 格"
            else:
                kind = "点击"
                param = next(
                    (name for name, code in CLICK_BUTTONS
                     if code == task.get("button")), "左键")
            expected = task.get("expected", "")
            if isinstance(task.get("ocr_box"), dict):
                expected = f"{expected}  [框选]" if expected else "[框选]"
            ocr_state = "✓" if task.get("ocr_check") else "—"
            expected_col = f"{ocr_state} {expected}".strip()
            interval_col = str(task.get("interval_ms") or 0)
            if not task.get("interval_ms"):
                interval_col = "全局"
            x_text = "跟随" if task.get("use_cursor") else task.get("x")
            y_text = "鼠标" if task.get("use_cursor") else task.get("y")
            self.tree.insert("", "end", iid=str(index), tags=("",),
                             values=(index + 1, kind, x_text,
                                     y_text, task.get("count", 1),
                                     param, interval_col, expected_col))
        self.summary_var.set(f"{len(self._tasks)} 个任务 · 合计 {total} 次动作")
        self._refresh_flow()

    # --------------------------- 流程图 ---------------------------
    def _refresh_flow(self):
        if not hasattr(self, "flow_canvas"):
            return
        canvas = self.flow_canvas
        canvas.delete("all")
        count = len(self._tasks)
        spacing = 112
        node_w = 96
        node_h = 48
        top = 9
        x = 8

        def draw_box(text, fill, outline):
            canvas.create_rectangle(
                x, top, x + node_w, top + node_h,
                fill=fill, outline=outline, width=1,
            )
            canvas.create_text(
                x + node_w / 2, top + node_h / 2, text=text,
                fill="#1e2a3a", width=node_w - 8,
                font=("Microsoft YaHei UI", 8),
            )

        if self._preset_index == 6:
            trigger = self.presets[6].get("trigger", "mouse_left")
            label = next(
                (name for name, code in TRIGGER_CHOICES if code == trigger),
                "鼠标左键")
            draw_box(f"监听 {label}\n点击后触发", "#fff1cf", AMBER)
        else:
            loop_mode = self.presets[self._preset_index].get(
                "loop", {}).get("mode", "none")
            trigger_text = (
                f"F8 监听\n按 {self._preset_index + 1} 触发"
                + (" / 长按循环" if loop_mode != "none" else ""))
            draw_box(trigger_text, "#dcebff", ACCENT)
        x += node_w
        for index, task in enumerate(self._tasks):
            canvas.create_text(
                x + 8, top + node_h / 2, text="→", fill=MUTED,
                font=("Microsoft YaHei UI", 10, "bold"))
            x += 16
            if task.get("type") == "wheel":
                text = (f"#{index + 1} 滚轮\n"
                        f"{task.get('x')},{task.get('y')} "
                        f"{task.get('direction', '向上')}"
                        f"{task.get('notches', 1)}格×{task.get('count', 1)}")
                fill, outline = "#e1f6ea", GREEN
            else:
                if task.get("use_cursor"):
                    text = (f"#{index + 1} 点击\n"
                            f"当前鼠标位置 ×{task.get('count', 1)}")
                    fill, outline = "#ffe7e9", RED
                else:
                    text = (f"#{index + 1} 点击\n"
                            f"({task.get('x')},{task.get('y')}) "
                            f"×{task.get('count', 1)}")
                    fill, outline = "#e7f1ff", ACCENT
            canvas.create_rectangle(
                x, top, x + node_w, top + node_h,
                fill=fill, outline=outline, width=1, tags=("task", str(index)),
            )
            canvas.create_text(
                x + node_w / 2, top + node_h / 2, text=text,
                fill="#1e2a3a", width=node_w - 8,
                font=("Microsoft YaHei UI", 8),
            )
            x += node_w
        canvas.create_text(
            x + 8, top + node_h / 2, text="→", fill=MUTED,
            font=("Microsoft YaHei UI", 10, "bold"))
        x += 16
        canvas.create_rectangle(
            x, top, x + node_w, top + node_h, fill="#eef2f7",
            outline="#94a3b8",
        )
        canvas.create_text(
            x + node_w / 2, top + node_h / 2, text="任务完成\n自动回到监听",
            fill="#475569", width=node_w - 6,
            font=("Microsoft YaHei UI", 8),
        )
        x += node_w + 8
        visible = max(canvas.winfo_width(), 300)
        canvas.configure(scrollregion=(0, 0, max(visible, x), 68))

    def _flow_index_from_x(self, event_x):
        x = self.flow_canvas.canvasx(event_x)
        node_w = 96
        spacing = 112
        if x < 16:
            return -1
        x -= 16
        first_task_left = 8 + 96 + 16
        if x < first_task_left:
            return -1
        index = int((x - first_task_left) // spacing)
        if 0 <= index < len(self._tasks):
            return index
        return -2

    def _flow_press(self, event):
        self._flow_origin = self._flow_index_from_x(event.x)
        self._flow_start_x = self.flow_canvas.canvasx(event.x)

    def _flow_release(self, event):
        index = self._flow_index_from_x(event.x)
        origin = getattr(self, "_flow_origin", -2)
        if index is None:
            return
        if 0 <= index < len(self._tasks) and 0 <= origin < len(self._tasks):
            if index != origin:
                task = self._tasks.pop(origin)
                self._tasks.insert(index, task)
                self._rebuild_tasks()
                self._save_presets_file()
                self.tree.selection_set(str(index))
                self.tree.focus(str(index))
                self._load_task_into_fields(self._tasks[index])
                self._set_status(
                    f"流程图已调整任务顺序：第 {index + 1} 位", GREEN)
            else:
                self.tree.selection_set(str(index))
                self.tree.focus(str(index))
                self._load_selection()

    def _flow_double(self, event):
        index = self._flow_index_from_x(event.x)
        if 0 <= index < len(self._tasks) and self.double_edit_var.get():
            self._open_row_editor(index)

    def _load_selection(self):
        if self._state != "idle":
            return
        selection = self.tree.selection()
        if not selection:
            return
        self._load_task_into_fields(self._tasks[int(selection[0])])

    def _update_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先在列表中选择一条任务", parent=self.root)
            return
        try:
            task = self._parse_task()
        except ValueError as exc:
            messagebox.showerror("输入有误", str(exc), parent=self.root)
            return
        self._tasks[int(selection[0])] = task
        self._rebuild_tasks()
        self._save_presets_file()
        self._set_status("已修改选中任务", GREEN)

    def _on_tree_double_click(self, event):
        if not self.double_edit_var.get() or self._state != "idle":
            return
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self._open_row_editor(int(row))

    def _open_row_editor(self, index):
        if not 0 <= index < len(self._tasks):
            return
        task = copy.deepcopy(self._tasks[index])
        dialog = tk.Toplevel(self.root)
        dialog.title(f"编辑任务 {index + 1}（关闭即自动保存）")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)

        type_var = tk.StringVar(
            value="滚轮" if task.get("type") == "wheel" else "点击")
        x_var = tk.StringVar(value=str(task.get("x", "")))
        y_var = tk.StringVar(value=str(task.get("y", "")))
        count_var = tk.StringVar(value=str(task.get("count", 1)))
        button_var = tk.StringVar()
        direction_var = tk.StringVar(
            value=task.get("direction", "向上"))
        notches_var = tk.StringVar(value=str(task.get("notches", 1)))
        interval_var = tk.StringVar(value=str(task.get("interval_ms") or 0))
        cursor_var = tk.BooleanVar(value=bool(task.get("use_cursor", False)))
        ocr_var = tk.BooleanVar(value=bool(task.get("ocr_check", False)))
        expected_var = tk.StringVar(value=task.get("expected", ""))
        fail_var = tk.StringVar()
        for label, code in CLICK_BUTTONS:
            if code == task.get("button", "left"):
                button_var.set(label)
        for label, code in OCR_FAIL_CHOICES:
            if code == task.get("ocr_fail", "stop"):
                fail_var.set(label)

        def add_row(row, label, widget):
            ttk.Label(frame, text=label).grid(
                row=row, column=0, sticky="e", padx=(0, 6), pady=4)
            widget.grid(row=row, column=1, columnspan=3, sticky="w", pady=4)

        type_combo = ttk.Combobox(frame, textvariable=type_var,
                                  values=("点击", "滚轮"),
                                  state="readonly", width=6)
        add_row(0, "类型", type_combo)
        add_row(1, "坐标 X / Y",
                ttk.Frame(frame))
        ttk.Entry(frame, textvariable=x_var, width=9, justify="center").grid(
            row=1, column=1, padx=(0, 4))
        ttk.Entry(frame, textvariable=y_var, width=9, justify="center").grid(
            row=1, column=2, sticky="w")

        count_spin = ttk.Spinbox(frame, from_=1, to=999999,
                                 textvariable=count_var, width=8)
        add_row(2, "次数", count_spin)
        ttk.Checkbutton(
            frame, text="使用当前鼠标位置（执行时不移动鼠标）",
            variable=cursor_var,
        ).grid(row=3, column=1, columnspan=3, sticky="w", pady=4)
        btn_combo = ttk.Combobox(frame, textvariable=button_var,
                                 values=[c[0] for c in CLICK_BUTTONS],
                                 state="readonly", width=10)
        add_row(4, "鼠标按键", btn_combo)
        dir_combo = ttk.Combobox(frame, textvariable=direction_var,
                                 values=SCROLL_DIRECTIONS,
                                 state="readonly", width=8)
        add_row(5, "滚动方向", dir_combo)
        notch_spin = ttk.Spinbox(frame, from_=1, to=100,
                                 textvariable=notches_var, width=8)
        add_row(6, "每次格数", notch_spin)
        int_spin = ttk.Spinbox(frame, from_=0, to=600000,
                               increment=10, textvariable=interval_var,
                               width=10)
        add_row(7, "本任务间隔ms", int_spin)
        ttk.Checkbutton(frame, text="启用本任务 OCR 校验",
                        variable=ocr_var).grid(
            row=8, column=1, columnspan=3, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=expected_var, width=34).grid(
            row=9, column=1, columnspan=3, sticky="w", pady=4)
        ttk.Label(frame, text="OCR 预期文字").grid(
            row=9, column=0, sticky="e", padx=(0, 6), pady=4)
        fail_combo = ttk.Combobox(frame, textvariable=fail_var,
                                  values=[l for l, _ in OCR_FAIL_CHOICES],
                                  state="readonly", width=14)
        add_row(10, "OCR 失败处理", fail_combo)
        ttk.Label(frame, text="提示：坐标/文字可直接修改，关闭窗口即自动保存；"
                              "OCR 框选区域保持不变。",
                  foreground=MUTED).grid(
            row=11, column=0, columnspan=4, pady=(8, 0))

        def commit():
            try:
                x = int(x_var.get())
                y = int(y_var.get())
                count = max(1, int(count_var.get()))
                interval = max(0, int(interval_var.get()))
            except ValueError:
                messagebox.showerror("输入有误", "坐标/次数/间隔需为数字",
                                     parent=dialog)
                return
            if type_var.get() == "滚轮":
                task.update({
                    "type": "wheel", "x": x, "y": y, "count": count,
                    "direction": direction_var.get(),
                    "notches": max(1, int(notches_var.get() or 1)),
                })
            else:
                button = "left"
                for label, code in CLICK_BUTTONS:
                    if label == button_var.get():
                        button = code
                task.update({
                    "type": "click", "x": x, "y": y, "count": count,
                    "button": button,
                })
            task["interval_ms"] = interval
            task["use_cursor"] = bool(cursor_var.get())
            task["ocr_check"] = bool(ocr_var.get())
            task["expected"] = expected_var.get().strip()
            task["ocr_fail"] = next(
                (code for label, code in OCR_FAIL_CHOICES
                 if label == fail_var.get()), "stop")
            self._tasks[index] = task
            self._rebuild_tasks()
            self._save_presets_file()
            dialog.destroy()
            self._set_status(f"任务 {index + 1} 已保存", GREEN)

        dialog.protocol("WM_DELETE_WINDOW", commit)
        ttk.Button(frame, text="完成（已自动保存）",
                   style="Success.TButton", command=commit).grid(
            row=12, column=0, columnspan=4, pady=(10, 0), sticky="ew")
        dialog.grab_set()
        dialog.update_idletasks()
        dialog.geometry(f"+{self.root.winfo_x() + 80}+"
                        f"{self.root.winfo_y() + 80}")

    def _delete_selected(self):
        selection = self.tree.selection()
        if not selection:
            return
        del self._tasks[int(selection[0])]
        self._rebuild_tasks()
        self._save_presets_file()
        self._set_status("已删除选中任务", AMBER)

    def _clear_tasks(self):
        if not self._tasks:
            return
        if not messagebox.askyesno("清空", "确定清空全部任务吗？", parent=self.root):
            return
        self._tasks.clear()
        self._rebuild_tasks()
        self._save_presets_file()
        self._set_status("已清空任务列表", AMBER)

    def _move_selected(self, delta):
        selection = self.tree.selection()
        if not selection:
            return
        index = int(selection[0])
        target = index + delta
        if target < 0 or target >= len(self._tasks):
            return
        self._tasks[index], self._tasks[target] = (
            self._tasks[target], self._tasks[index])
        self._rebuild_tasks()
        self.tree.selection_set(str(target))
        self.tree.focus(str(target))
        self._load_task_into_fields(self._tasks[target])
        self._save_presets_file()
        self._set_status(
            f"任务已移至第 {target + 1} 位（顺序决定执行先后）", GREEN)

    # --------------------------- 预设管理 ---------------------------
    def _reset_editor(self):
        self.type_var.set("点击")
        self.x_var.set("")
        self.y_var.set("")
        self.cursor_var.set(False)
        self.count_var.set("1")
        self.button_var.set(CLICK_BUTTONS[0][0])
        self.direction_var.set(SCROLL_DIRECTIONS[0])
        self.notches_var.set("3")
        self.expected_var.set("")
        self.task_interval_var.set("0")
        self.task_ocr_var.set(False)
        self.ocr_fail_var.set(OCR_FAIL_CHOICES[0][0])
        self._box = None
        self._box_anchor = None
        self._refresh_box_label()
        self._refresh_type_ui()
        self._refresh_cursor_ui()

    def _select_preset(self, index):
        if self._state != "idle":
            return
        if self._pick_mode:
            return
        self._save_preset_name(quiet=True)
        self._preset_index = index
        self._sync_preset_ui()
        self._set_status(f"当前预设：{index + 1} - "
                         f"{self.presets[index]['name']}（{len(self.presets[index]['tasks'])} 个任务）",
                         GREEN)

    def _save_preset_name(self, quiet=False):
        if self._state != "idle":
            return
        name = self.preset_name_var.get().strip() or f"预设{self._preset_index + 1}"
        self.presets[self._preset_index]["name"] = name
        loop_mode = "none"
        for label, code in LOOP_MODES:
            if label == self.loop_mode_var.get():
                loop_mode = code
        try:
            loop_count = max(1, int(self.loop_count_var.get() or 1))
        except ValueError:
            loop_count = 10
        try:
            loop_seconds = max(1, int(self.loop_seconds_var.get() or 1))
        except ValueError:
            loop_seconds = 10
        try:
            loop_interval = max(0, int(self.loop_interval_var.get() or 0))
        except ValueError:
            loop_interval = 1000
        self.presets[self._preset_index]["loop"] = {
            "mode": loop_mode, "count": loop_count,
            "seconds": loop_seconds, "interval_ms": loop_interval,
        }
        if self._preset_index == 6:
            for label, code in TRIGGER_CHOICES:
                if label == self.trigger_var.get():
                    self.presets[6]["trigger"] = code
                    break
        self.preset_name_var.set(name)
        for i, preset in enumerate(self.presets):
            short = preset["name"][:7]
            self.preset_buttons[i].configure(
                text=f"{i + 1} {short}"
                + ("…" if len(preset["name"]) > 7 else ""))
        self._update_overlay_text()
        self._refresh_flow()
        self._save_presets_file()
        if not quiet:
            self._set_status(f"预设名称已保存：{name}", GREEN)

    def _sync_preset_ui(self, init=False):
        preset = self.presets[self._preset_index]
        self._tasks = preset["tasks"]
        self.preset_name_var.set(preset["name"])
        trigger = preset.get("trigger", "mouse_left")
        self.trigger_var.set(
            next((label for label, code in TRIGGER_CHOICES if code == trigger),
                 TRIGGER_CHOICES[0][0]))
        loop = preset.get("loop", {})
        self.loop_mode_var.set(
            next((label for label, code in LOOP_MODES
                  if code == loop.get("mode", "none")),
                 LOOP_MODES[0][0]))
        self.loop_count_var.set(str(loop.get("count", 10)))
        self.loop_seconds_var.set(str(loop.get("seconds", 10)))
        self.loop_interval_var.set(str(loop.get("interval_ms", 1000)))
        self._reset_editor()
        self._rebuild_tasks()
        for i, p in enumerate(self.presets):
            short = p["name"][:7]
            self.preset_buttons[i].configure(
                text=f"{i + 1} {short}"
                + ("…" if len(p["name"]) > 7 else ""))
        self._update_overlay_text()
        self._refresh_trigger_ui()
        self._refresh_loop_ui()

    # --------------------------- 悬浮窗 ---------------------------
    def _build_overlay(self):
        overlay = tk.Toplevel(self.root)
        overlay.withdraw()
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.82)
        overlay.configure(bg="#101c30")
        width = 290
        height = 46 + 7 * 26
        overlay.geometry(f"{width}x{height}+0+0")
        canvas = tk.Canvas(overlay, width=width, height=height,
                           bg="#101c30", highlightthickness=0)
        canvas.pack()
        canvas.create_text(
            width // 2, 17, fill="#9fc1ff",
            font=("Microsoft YaHei UI", 10, "bold"),
            text="自动点击器 · 数字键 1~6 预设 / 7 触发预设",
        )
        self._overlay_rows = []
        for i in range(7):
            y = 44 + i * 26
            row_id = canvas.create_text(
                12, y, anchor="w", fill="#ffffff",
                font=("Microsoft YaHei UI", 10),
                text="")
            self._overlay_rows.append(row_id)
        self._overlay_canvas = canvas
        self._overlay = overlay

        drag = {"x": 0, "y": 0}

        def on_press(event):
            drag["x"], drag["y"] = event.x, event.y

        def on_move(event):
            x = overlay.winfo_x() + event.x - drag["x"]
            y = overlay.winfo_y() + event.y - drag["y"]
            overlay.geometry(f"+{x}+{y}")

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_move)
        self._update_overlay_text()

    def _update_overlay_text(self):
        if not hasattr(self, "_overlay_rows"):
            return
        active = -1
        if self._special_mode:
            active = 6
        elif self._state == "running" and self._runtime_index is not None:
            active = self._runtime_index
        for i, row_id in enumerate(self._overlay_rows):
            preset = self.presets[i]
            count = len(preset["tasks"])
            if i == 6:
                trigger = preset.get("trigger", "mouse_left")
                trigger_label = next(
                    (label for label, code in TRIGGER_CHOICES
                     if code == trigger), "鼠标左键")
                text = (f"7  {preset['name']}（{count} 任务 / 等待{trigger_label}）"
                        if self._special_mode and self._state == "armed"
                        else f"7  {preset['name']}（{count} 任务）")
            else:
                text = f"{i + 1}  {preset['name']}（{count} 个任务）"
            self._overlay_canvas.itemconfigure(
                row_id, text=text,
                fill="#ffd76a" if i == active else "#ffffff")

    def _show_overlay(self):
        if self._overlay is None:
            return
        self._update_overlay_text()
        screen_w = self.root.winfo_screenwidth()
        x = max(0, screen_w - 320)
        self._overlay.geometry(f"+{x}+{40}")
        self._overlay.deiconify()
        self._overlay.lift()

    def _hide_overlay(self):
        if self._overlay is not None:
            self._overlay.withdraw()

    def _presets_path(self):
        if getattr(sys, "frozen", False):
            folder = os.path.dirname(sys.executable)
        else:
            folder = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(folder, "auto_clicker_presets.json")

    def _save_presets_file(self):
        data = {
            "app": APP_NAME,
            "version": APP_VERSION,
            "global": {
                "interval_ms": self.interval_var.get(),
                "interval_jitter_ms": self.interval_jitter_var.get(),
                "xy_jitter": self.xy_jitter_var.get(),
                "ocr_width": self.ocr_width_var.get(),
                "ocr_height": self.ocr_height_var.get(),
            },
            "presets": self.presets,
        }
        try:
            with open(self._presets_path(), "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _load_presets_file(self):
        path = self._presets_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return

        def to_int(value, default):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        globals_ = data.get("global", {}) if isinstance(data, dict) else {}
        self.interval_var.set(to_int(globals_.get("interval_ms"), 100))
        self.interval_jitter_var.set(to_int(
            globals_.get("interval_jitter_ms"), 0))
        self.xy_jitter_var.set(to_int(globals_.get("xy_jitter"), 0))
        self.ocr_width_var.set(to_int(globals_.get("ocr_width"), 220))
        self.ocr_height_var.set(to_int(globals_.get("ocr_height"), 64))

        raw_presets = data.get("presets", []) if isinstance(data, dict) else []
        if not raw_presets:
            return
        self.presets = []
        for i in range(7):
            raw = raw_presets[i] if i < len(raw_presets) else {}
            name = str(raw.get("name", "") or f"预设{i + 1}")
            tasks = []
            for task in raw.get("tasks", []) if isinstance(raw, dict) else []:
                if isinstance(task, dict):
                    tasks.append(self._normalize_task(task))
            if i == 6:
                trigger = raw.get("trigger", "mouse_left") if isinstance(raw, dict) else "mouse_left"
                loop = raw.get("loop", {}) if isinstance(raw, dict) else {}
                self.presets.append(
                    {"name": name, "tasks": tasks, "trigger": trigger,
                     "loop": self._default_loop(loop)})
            else:
                loop = raw.get("loop", {}) if isinstance(raw, dict) else {}
                self.presets.append(
                    {"name": name, "tasks": tasks,
                     "loop": self._default_loop(loop)})
        self._preset_index = 0
        self._tasks = self.presets[0]["tasks"]

    def _normalize_task(self, task):
        expected = str(task.get("expected", "") or "")
        box = task.get("ocr_box")
        if not isinstance(box, dict):
            box = None
        common = {
            "expected": expected,
            "ocr_box": box,
            "interval_ms": max(0, int(task.get("interval_ms") or 0)),
            "ocr_check": bool(task.get("ocr_check", False)),
            "ocr_fail": str(task.get("ocr_fail", "stop") or "stop"),
            "use_cursor": bool(task.get("use_cursor", False)),
        }
        if not common["ocr_check"] and expected.strip():
            common["ocr_check"] = True
        if task.get("type") in ("wheel", "滚轮"):
            return {
                "type": "wheel",
                "x": int(task.get("x", 0)),
                "y": int(task.get("y", 0)),
                "count": max(1, int(task.get("count", 1))),
                "direction": task.get("direction", "向上"),
                "notches": max(1, int(task.get("notches", 1))),
                **common,
            }
        return {
            "type": "click",
            "x": int(task.get("x", 0)),
            "y": int(task.get("y", 0)),
            "count": max(1, int(task.get("count", 1))),
            "button": task.get("button", "left"),
            **common,
        }

    def _default_loop(self, raw):
        if not isinstance(raw, dict):
            raw = {}
        mode = raw.get("mode", "none")
        if mode not in ("none", "count", "seconds"):
            mode = "none"
        try:
            count = max(1, int(raw.get("count", 10)))
        except (TypeError, ValueError):
            count = 10
        try:
            seconds = max(1, int(raw.get("seconds", 10)))
        except (TypeError, ValueError):
            seconds = 10
        try:
            interval = max(0, int(raw.get("interval_ms", 1000)))
        except (TypeError, ValueError):
            interval = 1000
        return {"mode": mode, "count": count,
                "seconds": seconds, "interval_ms": interval}

    # --------------------------- OCR 图形框选 ---------------------------
    def _refresh_box_label(self):
        if self._box:
            self.box_var.set(
                f"范围：相对点击点 dx={self._box['dx1']}..{self._box['dx2']}, "
                f"dy={self._box['dy1']}..{self._box['dy2']}"
            )
        else:
            w = self.ocr_width_var.get() or "220"
            h = self.ocr_height_var.get() or "64"
            self.box_var.set(f"范围：自动以点击点为中心 {w}×{h}px")

    def _clear_ocr_box(self):
        self._box = None
        self._box_anchor = None
        self._refresh_box_label()
        self._set_status("已改为自动 OCR 区域", GREEN)

    def _graphical_ocr_box(self):
        if self._state != "idle":
            return
        if self.cursor_var.get():
            messagebox.showinfo(
                "提示", "“当前鼠标位置”模式使用以实时鼠标为中心的自动 OCR 区域，"
                        "不需要图形框选。", parent=self.root)
            return
        try:
            x = int(self.x_var.get())
            y = int(self.y_var.get())
        except ValueError:
            messagebox.showwarning("提示", "请先填写有效的坐标 X/Y 再框选",
                                   parent=self.root)
            return
        self._box_anchor = (x, y)
        vx, vy, vw, vh = get_virtual_screen()
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.geometry(f"{vw}x{vh}+{vx}+{vy}")
        top.attributes("-topmost", True)
        top.attributes("-alpha", 0.22)
        top.configure(bg="#102030")
        canvas = tk.Canvas(top, bg="#102030", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        canvas.create_text(30, 24, anchor="w", fill="#ffffff",
                           font=("Microsoft YaHei UI", 13, "bold"),
                           text="拖动鼠标框选 OCR 确认区域（尽量只框住按钮文字），"
                                "Esc / 右键取消")

        start = {"x": 0, "y": 0}
        rect_id = [None]
        done = {"ok": False}

        def cancel(_event=None):
            done["ok"] = False
            top.destroy()

        def on_press(event):
            start["x"], start["y"] = event.x, event.y
            if rect_id[0] is not None:
                canvas.delete(rect_id[0])
            rect_id[0] = canvas.create_rectangle(
                event.x, event.y, event.x, event.y,
                outline="#ff5252", width=2, fill="",
            )

        def on_move(event):
            if rect_id[0] is not None:
                canvas.coords(rect_id[0], start["x"], start["y"],
                              event.x, event.y)

        def on_release(event):
            if rect_id[0] is not None:
                canvas.delete(rect_id[0])
            ax1 = vx + min(start["x"], event.x)
            ay1 = vy + min(start["y"], event.y)
            ax2 = vx + max(start["x"], event.x)
            ay2 = vy + max(start["y"], event.y)
            if ax2 - ax1 >= 5 and ay2 - ay1 >= 5:
                self._box = {
                    "dx1": ax1 - x, "dy1": ay1 - y,
                    "dx2": ax2 - x, "dy2": ay2 - y,
                }
                done["ok"] = True
            top.destroy()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_move)
        canvas.bind("<ButtonRelease-1>", on_release)
        top.bind("<Escape>", cancel)
        canvas.bind("<Button-3>", cancel)
        top.wait_window(top)

        if done["ok"]:
            self._refresh_box_label()
            self._set_status("OCR 范围已框选：执行该任务前将识别此区域文字", GREEN)
        else:
            self._set_status("已取消 OCR 框选，仍使用自动区域", MUTED)

    # --------------------------- 拾取 ---------------------------
    def _single_pick(self):
        if self._state != "idle" or self._pick_mode:
            return
        self.root.iconify()
        self._set_status("拾取中：3 秒内把鼠标移到目标位置…", AMBER)
        self._single_pick_after = self.root.after(3000, self._finish_single_pick)

    def _finish_single_pick(self):
        self._single_pick_after = None
        x, y = get_cursor_pos()
        self.x_var.set(str(x))
        self.y_var.set(str(y))
        self.root.deiconify()
        self.root.lift()
        self._set_status(f"已拾取坐标：({x}, {y})", GREEN)

    def _cancel_single_pick(self):
        if self._single_pick_after is not None:
            try:
                self.root.after_cancel(self._single_pick_after)
            except Exception:
                pass
            self._single_pick_after = None

    def _toggle_pick_mode(self):
        if self._state != "idle":
            return
        if self._pick_mode:
            self._pick_mode = False
            self.btn_pick_mode.configure(text="连续拾取模式")
            self._set_status("已退出连续拾取", GREEN)
        else:
            self._pick_mode = True
            self.btn_pick_mode.configure(text="退出连续拾取 (Esc)")
            self._set_status(
                "连续拾取：移动鼠标到目标后按 F8 自动加入列表；Esc 退出", AMBER)
        self._refresh_controls()

    def _pick_add_point(self):
        x, y = get_cursor_pos()
        old = (self.x_var.get(), self.y_var.get())
        self.x_var.set(str(x))
        self.y_var.set(str(y))
        try:
            task = self._parse_task()
        except ValueError as exc:
            messagebox.showerror("输入有误", str(exc), parent=self.root)
            return
        finally:
            self.x_var.set(old[0])
            self.y_var.set(old[1])
        self._tasks.append(task)
        self._rebuild_tasks()
        self._save_presets_file()
        index = len(self._tasks) - 1
        self._set_status(
            f"已自动添加任务 {index + 1}：坐标 ({x}, {y}) × "
            f"{self.count_var.get()} 次", GREEN)
        self._after_pick_ocr(index, x, y)

    # --------------------------- OCR ---------------------------
    def _read_region_settings(self):
        try:
            width = max(20, min(1200, int(self.ocr_width_var.get())))
            height = max(10, min(600, int(self.ocr_height_var.get())))
        except ValueError:
            width, height = 220, 64
        return width, height

    def _ocr_background(self, index, x, y, width, height):
        try:
            text = ocr_region(x, y, width, height)
            self._events.put(("ocr_task_done", {"index": index, "text": text}))
        except Exception as exc:
            self._events.put(("ocr_task_error", str(exc)))

    def _ocr_into_field(self):
        if self._state != "idle":
            return
        try:
            x = int(self.x_var.get())
            y = int(self.y_var.get())
        except ValueError:
            messagebox.showwarning("提示", "请先填写有效的坐标 X/Y", parent=self.root)
            return
        if self._box:
            def worker_box():
                try:
                    text = ocr_box_region(
                        x + self._box["dx1"], y + self._box["dy1"],
                        x + self._box["dx2"], y + self._box["dy2"],
                    )
                    self._events.put(("ocr_task_done", {"index": None, "text": text}))
                except Exception as exc:
                    self._events.put(("ocr_task_error", str(exc)))
            threading.Thread(target=worker_box, daemon=True).start()
        else:
            width, height = self._read_region_settings()
            threading.Thread(
                target=self._ocr_background,
                args=(None, x, y, width, height), daemon=True,
            ).start()
        self._set_status("OCR 识别中…", ACCENT)

    def _after_pick_ocr(self, index, x, y):
        if index is None or not self.task_ocr_var.get():
            return
        width, height = self._read_region_settings()
        threading.Thread(
            target=self._ocr_background,
            args=(index, x, y, width, height), daemon=True,
        ).start()

    # --------------------------- 配置导入导出 ---------------------------
    def _export_config(self):
        self._save_preset_name(quiet=True)
        config = {
            "app": APP_NAME, "version": APP_VERSION,
            "global": {
                "interval_ms": self.interval_var.get(),
                "interval_jitter_ms": self.interval_jitter_var.get(),
                "xy_jitter": self.xy_jitter_var.get(),
                "ocr_width": self.ocr_width_var.get(),
                "ocr_height": self.ocr_height_var.get(),
            },
            "presets": self.presets,
        }
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".json",
            filetypes=[("JSON 配置文件", "*.json")],
            initialfile=f"自动点击器配置_v{APP_VERSION}.json")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(config, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc), parent=self.root)
            return
        self._set_status(f"配置已导出：{path}", GREEN)

    def _import_config(self):
        if self._state != "idle":
            return
        path = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[("JSON 配置文件", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                config = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("导入失败", f"无法读取配置：{exc}", parent=self.root)
            return
        globals_ = config.get("global", {}) if isinstance(config, dict) else {}
        if not globals_ and isinstance(config, dict):
            globals_ = config.get("settings", {})
        presets_raw = config.get("presets", []) if isinstance(config, dict) else []
        old_tasks = config.get("tasks", []) if isinstance(config, dict) else []

        def to_int(value, default):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        self.interval_var.set(to_int(globals_.get("interval_ms"), 100))
        self.interval_jitter_var.set(to_int(
            globals_.get("interval_jitter_ms"), 0))
        self.xy_jitter_var.set(to_int(globals_.get("xy_jitter"), 0))
        self.ocr_width_var.set(to_int(globals_.get("ocr_width"), 220))
        self.ocr_height_var.set(to_int(globals_.get("ocr_height"), 64))

        old_global_ocr = bool(globals_.get("ocr_enabled", False))
        if presets_raw:
            loaded_presets = []
            for i in range(7):
                raw = presets_raw[i] if i < len(presets_raw) else {}
                if not isinstance(raw, dict):
                    raw = {}
                name = str(raw.get("name", "") or f"预设{i + 1}")
                tasks = []
                for task in raw.get("tasks", []):
                    if isinstance(task, dict):
                        task = copy.deepcopy(task)
                        if old_global_ocr and not task.get("ocr_check") and task.get("expected"):
                            task["ocr_check"] = True
                        tasks.append(self._normalize_task(task))
                if i == 6:
                    trigger = raw.get("trigger", "mouse_left")
                    loaded_presets.append(
                        {"name": name, "tasks": tasks, "trigger": trigger,
                         "loop": self._default_loop(raw.get("loop", {}))})
                else:
                    loaded_presets.append(
                        {"name": name, "tasks": tasks,
                         "loop": self._default_loop(raw.get("loop", {}))})
            self.presets = loaded_presets
        elif old_tasks:
            # 兼容旧版单列表配置，导入到预设 1
            default_loop = self._default_loop({})
            old_presets = [{"name": "预设1", "tasks": [],
                            "loop": dict(default_loop)}] + [
                {"name": f"预设{i}", "tasks": [],
                 "loop": dict(default_loop)} for i in range(2, 7)
            ] + [{"name": "触发预设7", "tasks": [], "trigger": "mouse_left",
                  "loop": dict(default_loop)}]
            for task in old_tasks:
                if isinstance(task, dict):
                    task = copy.deepcopy(task)
                    if old_global_ocr and not task.get("ocr_check") and task.get("expected"):
                        task["ocr_check"] = True
                    old_presets[0]["tasks"].append(self._normalize_task(task))
            self.presets = old_presets
        else:
            messagebox.showwarning("导入配置", "配置里没有有效任务或预设", parent=self.root)
            return
        self._preset_index = 0
        self._tasks = self.presets[0]["tasks"]
        self._sync_preset_ui()
        self._save_presets_file()
        total = sum(len(p["tasks"]) for p in self.presets)
        self._set_status(f"已导入配置：7 个预设共 {total} 个任务", GREEN)

    # --------------------------- 运行控制 ---------------------------
    def _options(self):
        def num(var, default):
            try:
                return int(var.get().strip())
            except ValueError:
                return default
        interval = max(0, min(num(self.interval_var, 100), 600000))
        jitter_ms = max(0, min(num(self.interval_jitter_var, 0), 600000))
        xy = max(0, min(num(self.xy_jitter_var, 0), 5000))
        width, height = self._read_region_settings()
        return {"interval_ms": interval, "interval_jitter_ms": jitter_ms,
                "xy_jitter": xy, "ocr_width": width, "ocr_height": height}

    def _on_f8(self):
        if self._single_pick_after is not None:
            return
        if self._pick_mode:
            self._pick_add_point()
            return
        if self._state == "idle":
            self._enter_listening()
        else:
            self._exit_runtime()

    def _on_escape(self):
        if self._pick_mode:
            self._pick_mode = False
            self.btn_pick_mode.configure(text="连续拾取模式")
            self._refresh_controls()
            self._set_status("已退出连续拾取", GREEN)
        elif self._state == "running" and self._loop_active:
            self._cancel_loop()
        elif self._state in ("listening", "running", "armed"):
            self._exit_runtime()

    def _enter_listening(self):
        if self._state != "idle":
            return
        self._save_preset_name(quiet=True)
        self._special_mode = False
        self._stop_trigger_monitor()
        self._state = "listening"
        self._manual_exit = False
        self._start_number_monitor()
        self._show_overlay()
        self._refresh_controls()
        self._set_status(
            "监听中：按数字 1~6 运行预设，7 进入触发预设；F8/Esc 退出", AMBER)

    def _enter_special(self):
        if self._state not in ("listening", "running", "armed"):
            return
        self._stop_current_worker()
        self._stop_trigger_monitor()
        self._special_mode = True
        self._runtime_index = None
        self._state = "armed"
        self._start_trigger_monitor()
        self._show_overlay()
        self._update_overlay_text()
        self._refresh_controls()
        trigger = self.presets[6].get("trigger", "mouse_left")
        label = next((t for t, c in TRIGGER_CHOICES if c == trigger),
                     "鼠标左键")
        self._set_status(
            f"触发预设 7 已开启：等待 {label} 后执行预设 7 任务；"
            f"1~6 可切回普通预设，F8/Esc 退出", AMBER)

    def _start_trigger_monitor(self):
        self._stop_trigger_monitor()
        trigger = self.presets[6].get("trigger", "mouse_left")
        self._trigger_monitor = TriggerMonitor(self._events, trigger)
        self._trigger_monitor.start()

    def _stop_trigger_monitor(self):
        monitor = self._trigger_monitor
        self._trigger_monitor = None
        if monitor is not None:
            monitor.stop()
            monitor.join(0.3)

    def _start_number_monitor(self):
        self._stop_number_monitor()
        self._number_monitor = NumberMonitor(self._events)
        self._number_monitor.start()

    def _stop_number_monitor(self):
        monitor = self._number_monitor
        self._number_monitor = None
        if monitor is not None:
            monitor.stop()
            monitor.join(0.3)

    def _start_preset(self, index, trigger_loop=False):
        if self._state not in ("listening", "running", "armed"):
            return
        tasks = self.presets[index]["tasks"]
        if not tasks:
            self._set_status(
                f"预设 {index + 1} 为空，请先在主界面添加任务"
                + ("，仍在等待触发" if index == 6 and self._special_mode else ""),
                RED)
            return
        loop_spec = None
        if trigger_loop:
            loop_spec = self.presets[index].get(
                "loop", {"mode": "none", "count": 10, "seconds": 10,
                         "interval_ms": 1000})
            if loop_spec.get("mode", "none") == "none":
                self._set_status(
                    f"预设 {index + 1} 未设置循环：请先在预设栏选择"
                    f"“按次数循环”或“按时间循环”", AMBER)
                return
            if index == 6:
                self._enter_special()
                return
        self._stop_current_worker()
        if index == 6:
            self._special_mode = True
            self._stop_trigger_monitor()
        else:
            self._special_mode = False
            self._stop_trigger_monitor()
        self._runtime_index = index
        self._loop_active = bool(trigger_loop)
        self._loop_preset_index = index if trigger_loop else None
        self._run_id += 1
        self._run_done = 0
        self._run_total = 0
        self._current_seg = None
        self._state = "running"
        snapshot = [copy.deepcopy(t) for t in tasks]
        self._worker = ClickWorker(
            snapshot, self._options(), self._events, self._run_id,
            loop_spec=loop_spec, is_loop=trigger_loop)
        self._worker.start()
        self._update_overlay_text()
        self._refresh_controls()
        if index == 6:
            self._set_status(
                f"触发预设 7 已执行：共 {len(tasks)} 个任务；"
                f"完成后自动回到触发监听", ACCENT)
        elif trigger_loop:
            mode = loop_spec.get("mode", "none")
            if mode == "count":
                detail = f"循环 {loop_spec.get('count', 1)} 次"
            else:
                detail = f"循环 {loop_spec.get('seconds', 1)} 秒"
            self._set_status(
                f"循环运行预设 {index + 1}：{detail}；"
                f"按 Esc 或再按 {index + 1} 取消", RED)
        else:
            self._set_status(
                f"运行预设 {index + 1} - {self.presets[index]['name']}："
                f"共 {len(tasks)} 个任务；按 1~6 切换，F8/Esc 退出",
                ACCENT)

    def _exit_runtime(self):
        if self._state not in ("listening", "running", "armed"):
            return
        done = self._run_done
        self._manual_exit = True
        self._stop_current_worker()
        self._stop_trigger_monitor()
        self._run_id += 1
        self._runtime_index = None
        self._special_mode = False
        self._loop_active = False
        self._loop_preset_index = None
        self._state = "idle"
        self._stop_number_monitor()
        self._hide_overlay()
        self._refresh_controls()
        self._manual_exit = False
        self._set_status(
            f"已退出运行（共执行 {done} 次动作）", GREEN)

    def _stop_current_worker(self):
        worker = self._worker
        if worker is not None:
            worker.stop_event.set()
            worker.running_event.set()
            worker.join(1.5)
            self._worker = None

    def _on_num(self, number):
        self._on_num_short(number)

    def _on_num_short(self, number):
        if self._state not in ("listening", "running", "armed"):
            return
        if (self._state == "running" and self._loop_active
                and self._loop_preset_index == number - 1):
            self._cancel_loop()
            return
        if number == 7:
            if self._special_mode and self._state == "running":
                return
            self._enter_special()
            return
        if number <= 6:
            self._start_preset(number - 1)

    def _on_num_long(self, number, ctrl=False):
        if self._state not in ("listening", "running", "armed"):
            return
        if number == 7:
            self._enter_special()
            return
        if number <= 6:
            self._start_preset(number - 1, trigger_loop=True)

    def _cancel_loop(self):
        self._stop_current_worker()
        self._run_id += 1
        self._loop_active = False
        self._loop_preset_index = None
        self._runtime_index = None
        if self._special_mode:
            self._state = "armed"
            self._start_trigger_monitor()
        else:
            self._state = "listening"
        self._show_overlay()
        self._refresh_controls()
        self._set_status(
            "已取消循环，保持监听；按 1~7 可选择/触发，F8/Esc 退出",
            AMBER)

    def _on_local_key(self, event):
        """主界面空闲时，不在输入框里按 1~6 可切换当前编辑预设。"""
        if self._state != "idle" or self._pick_mode:
            return
        if event.keysym not in (
                "1", "2", "3", "4", "5", "6", "7"):
            return
        focus = self.root.focus_get()
        if isinstance(focus, (ttk.Entry, ttk.Spinbox, ttk.Combobox,
                              tk.Entry)):
            return
        self._select_preset(int(event.keysym) - 1)

    # --------------------------- 事件 ---------------------------
    def _poll_events(self):
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "ready":
                    self._set_status("就绪：热键 F8 / Esc 已注册", GREEN)
                elif kind == "hotkey_error":
                    messagebox.showwarning(
                        "热键注册失败",
                        f"快捷键 {payload} 注册失败，可能已被占用。窗口按钮仍可用。",
                        parent=self.root)
                elif kind == "key":
                    if payload == "f8":
                        self._on_f8()
                    elif payload == "esc":
                        self._on_escape()
                    elif payload.startswith("num"):
                        self._on_num(int(payload[3:]))
                elif kind == "numkey":
                    self._on_num(payload)
                elif kind == "longkey":
                    self._on_num_long(payload)
                elif kind == "loopkey":
                    self._on_num_long(payload, ctrl=True)
                elif kind == "start":
                    if payload.get("id") == self._run_id:
                        self._run_total = payload.get("total", 0)
                        self._update_progress()
                elif kind == "trigger":
                    if self._state == "armed" and self._special_mode:
                        self._start_preset(6)
                elif kind == "progress":
                    if payload.get("id") == self._run_id:
                        self._run_done = payload.get("done", self._run_done)
                        seg = payload.get("seg")
                        if self._state == "running" and seg != self._current_seg:
                            self._current_seg = seg
                            self._highlight_task(seg)
                        if self._state == "running":
                            self._set_status(
                                f"预设 {self._runtime_index + 1} 运行中："
                                f"已执行 {self._run_done} 次动作，"
                                f"当前任务 {seg + 1}/{len(self.presets[self._runtime_index]['tasks'])}",
                                ACCENT)
                        self._update_progress()
                elif kind == "ocr_scan":
                    if payload.get("id") == self._run_id:
                        seg = payload.get("seg", 0)
                        self._highlight_task(seg)
                        self._set_status(
                            f"OCR 校验任务 {seg + 1} 的文字…", ACCENT)
                elif kind == "ocr_skip":
                    if payload.get("id") == self._run_id:
                        seg = payload.get("seg", 0)
                        self._set_status(
                            f"任务 {seg + 1} OCR 未匹配，已按设置跳过", AMBER)
                elif kind == "finished":
                    self._on_worker_finished(payload)
                elif kind == "ocr_task_done":
                    index = payload.get("index")
                    text = payload.get("text", "")
                    if index is None:
                        self.expected_var.set(text)
                        self._set_status(
                            f"识别完成：{text or '（空）'}（可编辑后加入任务）", GREEN)
                    elif 0 <= index < len(self._tasks) and self._state == "idle":
                        self._tasks[index]["expected"] = text
                        self._rebuild_tasks()
                        self._save_presets_file()
                        self._set_status(
                            f"任务 {index + 1} 已自动填入 OCR 文字："
                            f"{text or '（空）'}", GREEN)
                elif kind == "ocr_task_error":
                    self._set_status(f"OCR 识别失败：{payload}", RED)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_events)

    def _highlight_task(self, seg):
        for item in self.tree.get_children():
            if self.tree.item(item, "tags"):
                self.tree.item(item, tags=("",))
        if 0 <= seg < len(self._tasks):
            iid = str(seg)
            if self.tree.exists(iid):
                self.tree.item(iid, tags=("current",))
                self.tree.see(iid)

    def _on_worker_finished(self, payload):
        if payload.get("id") != self._run_id:
            return
        reason = payload.get("reason")
        done = payload.get("done", self._run_done)
        self._worker = None
        self._run_done = done
        self._runtime_index = None
        was_loop = self._loop_active
        self._loop_active = False
        self._loop_preset_index = None
        if self._special_mode:
            self._state = "armed"
            self._start_trigger_monitor()
            self._show_overlay()
            self._update_overlay_text()
            self._refresh_controls()
            if reason == "completed":
                self._set_status(
                    f"触发预设 7 执行完成（{done} 次动作）；"
                    f"继续等待触发键，1~6 可切换，F8/Esc 退出", GREEN)
            elif reason == "ocr_mismatch":
                self._set_status(
                    "触发预设 OCR 未通过已停止；已回到触发监听", RED)
                messagebox.showwarning(
                    "OCR 校验未通过", payload.get("message", ""), parent=self.root)
            elif reason == "error":
                self._set_status(
                    f"触发预设运行出错：{payload.get('message')}（已回到触发监听）", RED)
                messagebox.showerror(
                    "运行出错", payload.get("message", ""), parent=self.root)
            else:
                self._set_status(
                    f"触发预设已停止（{done} 次动作）；已回到触发监听", AMBER)
            return

        self._state = "listening"
        self._show_overlay()
        self._refresh_controls()
        if reason == "completed":
            if was_loop:
                self._set_status(
                    f"循环预设已完成（共执行 {done} 次动作）；"
                    f"回到监听，按 1~6/7 可继续选择", GREEN)
                return
            self._set_status(
                f"预设完成，共执行 {done} 次动作；已回到监听，"
                f"可继续按 1~6 选择，F8/Esc 退出", GREEN)
        elif reason == "ocr_mismatch":
            self._set_status(
                "OCR 校验未通过已停止；已回到监听，可按 1~6 重选或退出", RED)
            messagebox.showwarning("OCR 校验未通过", payload.get("message", ""),
                                   parent=self.root)
        elif reason == "error":
            self._set_status(
                f"运行出错：{payload.get('message')}（已回到监听）", RED)
            messagebox.showerror("运行出错", payload.get("message", ""),
                                 parent=self.root)
        else:
            self._set_status(
                f"已停止（共执行 {done} 次动作）；已回到监听", AMBER)

    def _set_status(self, text, color):
        self.status_var.set(text)
        self.lbl_status.configure(fg=color,
                                  bg="#fdf2f2" if color == RED else "#f2f7f4")

    def _update_progress(self):
        if self._run_total > 0:
            percent = min(100.0, self._run_done / self._run_total * 100)
        else:
            percent = 0
        self.progress.configure(value=percent)
        self.lbl_percent.configure(text=f"{int(percent)}%")

    def _refresh_controls(self):
        editable = self._state == "idle" and not self._pick_mode
        state = "normal" if editable else "disabled"
        for widget in self._edit_widgets:
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass
        if self._pick_mode:
            for widget in self._edit_widgets:
                try:
                    widget.configure(state="normal")
                except tk.TclError:
                    pass
        self._refresh_type_ui()

        if self._state in ("listening", "armed"):
            self.btn_go.configure(
                state="normal",
                text="退出监听/触发 (F8/Esc)",
            )
            self.btn_exit.configure(state="normal")
            self.btn_pick_mode.configure(state="disabled")
        elif self._state == "running":
            self.btn_go.configure(state="normal", text="停止并退出 (F8/Esc)")
            self.btn_exit.configure(state="normal")
            self.btn_pick_mode.configure(state="disabled")
        else:
            self.btn_go.configure(state="normal" if not self._pick_mode else "disabled",
                                  text="启动监听 (F8)")
            self.btn_exit.configure(state="disabled")
            self.btn_pick_mode.configure(
                state="normal",
                text="退出连续拾取 (Esc)" if self._pick_mode else "连续拾取模式")

        preset_editable = self._state == "idle" and not self._pick_mode
        preset_state = "normal" if preset_editable else "disabled"
        for btn in self.preset_buttons:
            btn.configure(state=preset_state)
        self.ent_preset_name.configure(state=preset_state)
        self.btn_rename.configure(state=preset_state)
        self._refresh_trigger_ui()
        self._refresh_cursor_ui()
        self._refresh_loop_ui()
        self._update_overlay_text()
        if self._state != "running":
            self.progress.configure(value=0)
            self.lbl_percent.configure(text="0%")

    def _on_close(self):
        if self._state != "idle" and not messagebox.askyesno(
                "退出", "程序正在监听/运行，确定退出吗？", parent=self.root):
            return
        self._save_preset_name(quiet=True)
        self._save_presets_file()
        self._stop_current_worker()
        self._stop_trigger_monitor()
        self._stop_number_monitor()
        self._hide_overlay()
        if self._hotkey is not None:
            self._hotkey.commands.put(("quit", None))
        self._cancel_single_pick()
        self.root.destroy()


# ---------------------------------------------------------------------------
def _selftest_ocr(out_path):
    import io
    from PIL import Image, ImageDraw, ImageFont

    try:
        img = Image.new("RGB", (560, 120), "white")
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 42)
        draw.text((14, 30), "Codex OCR 123", fill="black", font=font)
        rgba = img.convert("RGBA")
        raw = rgba.tobytes()
        data = bytearray(rgba.size[0] * rgba.size[1] * 4)
        for i in range(rgba.size[0] * rgba.size[1]):
            j = i * 4
            data[j] = raw[i * 4 + 2]
            data[j + 1] = raw[i * 4 + 1]
            data[j + 2] = raw[i * 4]
            data[j + 3] = 255
        text = ocr_bgra(bytes(data), rgba.size[0], rgba.size[1])
        result = ["OK", text]
    except Exception as exc:
        result = ["ERROR", f"{type(exc).__name__}: {exc}"]
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(result))


def main():
    if "--ocr-test" in sys.argv:
        try:
            out_path = sys.argv[sys.argv.index("--ocr-test") + 1]
        except IndexError:
            out_path = "ocr_test_result.txt"
        _selftest_ocr(out_path)
        return
    if sys.platform != "win32":
        print("仅支持 Windows")
        return
    enable_dpi_awareness()
    root = tk.Tk()
    ClickerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
