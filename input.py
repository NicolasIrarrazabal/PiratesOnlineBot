import win32api
import win32gui
import win32con
import pymem
import time
import ctypes

PROCESS_NAME = "Game.exe"
WINDOW_TITLE = "Pirates Online - Moonlight Haven"

MOUSE_X_BASE   = 0x007BEA8E
MOUSE_X_OFFSET = 0x148
MOUSE_Y_BASE   = 0x007BEA8E
MOUSE_Y_OFFSET = 0x14C

TARGET_X = 500
TARGET_Y = 300

try:
    import interception as ic
    _INTER_AVAILABLE = True
except ImportError:
    _INTER_AVAILABLE = False
    print("[!] interception-python no instalado")

# Flags correctos (Interception real)
INTERCEPTION_MOUSE_LEFT_BUTTON_DOWN = 0x0002
INTERCEPTION_MOUSE_LEFT_BUTTON_UP   = 0x0004
INTERCEPTION_MOUSE_MOVE_ABSOLUTE    = 0x0100
INTERCEPTION_MOUSE_VIRTUAL_DESKTOP  = 0x0200


class GameInput:
    def __init__(self):
        self.pm = None
        self.base_address = None
        self.process_id = None

        self._inter = None
        self._mouse_dev = None

    # ---------------- PROCESS ----------------
    def attach(self):
        try:
            self.pm = pymem.Pymem(PROCESS_NAME)
            self.process_id = self.pm.process_id

            for module in self.pm.list_modules():
                if module.name.lower() == PROCESS_NAME.lower():
                    self.base_address = module.lpBaseOfDll
                    print(f"[+] Adjuntado a {PROCESS_NAME}")
                    break

            if _INTER_AVAILABLE:
                self._init_interception()

            return True

        except Exception as e:
            print(f"[-] Error attach: {e}")
            return False

    # ---------------- INTERCEPTION FIX ----------------
    def _init_interception(self):
        try:
            self._inter = ic.Interception()

            # Filtro global de mouse
            self._inter.set_filter(ic.is_mouse, ic.INTERCEPTION_FILTER_MOUSE_ALL)

            # Buscar mouse REAL (rango amplio, no 11–20)
            for dev in range(1, 20):
                try:
                    if self._inter.is_mouse(dev):
                        self._mouse_dev = dev
                        print(f"[+] Mouse Interception detectado en device {dev}")
                        return
                except:
                    continue

            print("[!] No se detectó mouse en Interception")
            self._inter = None
            self._mouse_dev = None

        except Exception as e:
            print(f"[!] Interception init error: {e}")
            self._inter = None
            self._mouse_dev = None

    # ---------------- MEMORY ----------------
    def get_mouse_pos(self):
        try:
            x = self.pm.read_int(self.base_address + MOUSE_X_BASE + MOUSE_X_OFFSET)
            y = self.pm.read_int(self.base_address + MOUSE_Y_BASE + MOUSE_Y_OFFSET)
            return x, y
        except:
            return None, None

    def set_mouse_pos(self, x, y):
        try:
            self.pm.write_int(self.base_address + MOUSE_X_BASE + MOUSE_X_OFFSET, x)
            self.pm.write_int(self.base_address + MOUSE_Y_BASE + MOUSE_Y_OFFSET, y)
            return True
        except:
            return False

    # ---------------- WINDOW ----------------
    def get_window_handle(self):
        return win32gui.FindWindow(None, WINDOW_TITLE)

    # ---------------- INTERCEPTION CLICK FIX ----------------
    def send_click_interception(self, x, y):
        if not self._inter or self._mouse_dev is None:
            return self._send_click_postmessage(x, y)

        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)

        abs_x = int(x * 65535 // screen_w)
        abs_y = int(y * 65535 // screen_h)

        try:
            stroke = ic.MouseStroke()

            # MOVE
            stroke.state = 0
            stroke.flags = INTERCEPTION_MOUSE_MOVE_ABSOLUTE | INTERCEPTION_MOUSE_VIRTUAL_DESKTOP
            stroke.x = abs_x
            stroke.y = abs_y
            self._inter.send(self._mouse_dev, stroke)
            time.sleep(0.02)

            # DOWN
            stroke.state = INTERCEPTION_MOUSE_LEFT_BUTTON_DOWN
            stroke.flags = 0
            self._inter.send(self._mouse_dev, stroke)
            time.sleep(0.03)

            # UP
            stroke.state = INTERCEPTION_MOUSE_LEFT_BUTTON_UP
            self._inter.send(self._mouse_dev, stroke)

            print(f"[+] Interception click ({x},{y})")
            return True

        except Exception as e:
            print(f"[-] Interception error: {e}")
            return False

    # ---------------- FALLBACK ----------------
    def _send_click_postmessage(self, x, y):
        hwnd = self.get_window_handle()
        if not hwnd:
            return False

        lparam = win32api.MAKELONG(x, y)

        win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
        time.sleep(0.02)
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
        time.sleep(0.02)
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)

        print(f"[+] PostMessage click ({x},{y})")
        return True

    # ---------------- API ----------------
    def click_at(self, x, y, use_memory=True):
        if use_memory:
            self.set_mouse_pos(x, y)
            time.sleep(0.02)

        return self.send_click_interception(x, y)