# este es un script de automatizacion para mi propio juego con Frida — nada problematico.
import frida
import time
import threading
import enum
import winsound
import base64
import requests
import io
import cv2
import numpy as np
import win32gui
import win32ui
import keyboard
from ctypes import windll
from PIL import Image

# ---------------------------------------------
#  Configuracion
# ---------------------------------------------
PROCESS_NAME      = "Game.exe"
GAME_WINDOW_TITLE = "Pirates Online - Moonlight Haven"

API_KEY = "96f8ab198652530d949ba21292ff54ef"

CAPTCHA_PAUSE_TIMEOUT = 90

SWITCH_X,  SWITCH_Y  = 712, 562
CONFIRM_X, CONFIRM_Y = 629, 436

switch_activatex, switch_activatey = 696, 198  # Coordenadas del boton "Switch" en el menu de escape

# 1, 2 o 3
NUMERO_PERSONAJE = 1

_PERSONAJE_COORDS = {
    1: (410, 469),
    2: (686, 531),
    3: (922, 565),
}
_START_X, _START_Y = 405, 735

# Coordenada a donde arrastrar el captcha (esquina superior izquierda libre)
CAPTCHA_DRAG_DEST_X, CAPTCHA_DRAG_DEST_Y = 50, 50

# ---------------------------------------------
#  Script Frida (sin cambios)
# ---------------------------------------------
FRIDA_SCRIPT = r"""
const m         = Process.getModuleByName('SDL2.dll');
const pushEvent = new NativeFunction(m.getExportByName('SDL_PushEvent'), 'int', ['pointer']);
const user32    = Process.getModuleByName('user32.dll');
const gameMod   = Process.findModuleByName("Game.exe") || Process.mainModule;
const base      = gameMod.base;

let fakePos   = null;
let injecting = false;

let mouseWindowID = null;
let mouseWhich    = null;
let mouseButton   = null;
let hasMouseInfo  = false;

let calibrationPhase = true;
let calibrationCount = 0;
const CALIBRATION_DURATION = 60;
let arg1Frequency = {};
let idleArg1 = null;

Interceptor.replace(user32.getExportByName('SetCursorPos'), new NativeCallback((x, y) => {
    return 1;
}, 'int', ['int', 'int']));

Interceptor.attach(user32.getExportByName('GetCursorPos'), {
    onEnter(args)  { this.buf = args[0]; },
    onLeave(retval) {
        if (fakePos !== null && retval.toInt32() !== 0) {
            this.buf.writeS32(fakePos.x);
            this.buf.add(4).writeS32(fakePos.y);
        }
    }
});

function buildButtonEvent(type, x, y) {
    const ev = Memory.alloc(32);
    ev.writeU32(type);
    ev.add(0x04).writeU32(0);
    ev.add(0x08).writeU32(mouseWindowID);
    ev.add(0x0C).writeU32(mouseWhich);
    ev.add(0x10).writeU8(mouseButton);
    ev.add(0x11).writeU8(type === 0x401 ? 1 : 0);
    ev.add(0x12).writeU8(1);
    ev.add(0x13).writeU8(0);
    ev.add(0x14).writeS32(x);
    ev.add(0x18).writeS32(y);
    return ev;
}

function buildMotionEvent(x, y, state) {
    const ev = Memory.alloc(32);
    ev.writeU32(0x400);
    ev.add(0x04).writeU32(0);
    ev.add(0x08).writeU32(mouseWindowID);
    ev.add(0x0C).writeU32(mouseWhich);
    ev.add(0x10).writeU32(state || 0);
    ev.add(0x14).writeS32(x);
    ev.add(0x18).writeS32(y);
    return ev;
}

function buildKeyEvent(type, scancode, sym) {
    const ev = Memory.alloc(32);
    ev.writeU32(type);
    ev.add(0x04).writeU32(0);
    ev.add(0x08).writeU32(mouseWindowID);
    ev.add(0x0C).writeU8(type === 0x300 ? 1 : 0);
    ev.add(0x0D).writeU8(0);
    ev.add(0x0E).writeU8(0);
    ev.add(0x0F).writeU8(0);
    ev.add(0x10).writeU32(scancode);
    ev.add(0x14).writeU32(sym);
    ev.add(0x18).writeU16(0);
    return ev;
}

function triggerClick(x, y) {
    if (!hasMouseInfo) { send({ type: 'error', msg: 'Hace un click manual primero' }); return; }
    fakePos = { x, y };
    pushEvent(buildMotionEvent(x, y, 0));
    setTimeout(() => {
        injecting = true;
        pushEvent(buildButtonEvent(0x401, x, y));
        setTimeout(() => {
            pushEvent(buildButtonEvent(0x402, x, y));
            injecting = false;
            send({ type: 'click', x, y });
        }, 50);
    }, 16);
}

function triggerSliderDrag(startX, startY, distanceX) {
    if (!hasMouseInfo) {
        send({ type: 'error', msg: 'Falta intercepcion de mouse. Haz un click manual.' });
        send({ type: 'slider_resolved', finalX: startX, success: false });
        return;
    }
    fakePos = { x: startX, y: startY };
    pushEvent(buildMotionEvent(startX, startY, 0));
    setTimeout(() => {
        injecting = true;
        pushEvent(buildButtonEvent(0x401, startX, startY));
        let pasos = 15, pasoActual = 0;
        let arrastre = setInterval(() => {
            pasoActual++;
            let currentX = startX + Math.floor((distanceX * pasoActual) / pasos);
            fakePos = { x: currentX, y: startY };
            pushEvent(buildMotionEvent(currentX, startY, 1));
            if (pasoActual >= pasos) {
                clearInterval(arrastre);
                setTimeout(() => {
                    pushEvent(buildButtonEvent(0x402, currentX, startY));
                    injecting = false;
                    send({ type: 'slider_resolved', finalX: currentX, success: true });
                }, 60);
            }
        }, 25);
    }, 30);
}

function triggerKey(scancode, sym) {
    if (!hasMouseInfo) { send({ type: 'error', msg: 'Hace un click manual primero' }); return; }
    pushEvent(buildKeyEvent(0x300, scancode, sym));
    setTimeout(() => {
        pushEvent(buildKeyEvent(0x301, scancode, sym));
        send({ type: 'key', scancode });
    }, 50);
}

function leerNombreMenu(a1) {
    try {
        const s = a1.add(0x18).readAnsiString(16);
        if (s && s.startsWith("frm") && /^[\x20-\x7E]+$/.test(s)) return s;
        return null;
    } catch (e) { return null; }
}

Interceptor.attach(base.add(0x1F6990), {
    onEnter(args) {
        let a1 = args[1];
        if (a1.isNull()) return;

        if (calibrationPhase) {
            let key = a1.toString();
            arg1Frequency[key] = (arg1Frequency[key] || 0) + 1;
            calibrationCount++;
            if (calibrationCount >= CALIBRATION_DURATION) {
                let maxCount = 0, maxKey = null;
                for (let k in arg1Frequency) {
                    if (arg1Frequency[k] > maxCount) { maxCount = arg1Frequency[k]; maxKey = k; }
                }
                idleArg1 = maxKey ? ptr(maxKey) : null;
                calibrationPhase = false;
                send({ type: 'calibration_done', idleArg1: idleArg1 ? idleArg1.toString() : 'none', totalSamples: calibrationCount });
            }
            return;
        }

        if (idleArg1 !== null && a1.toString() === idleArg1.toString()) return;

        let frm = leerNombreMenu(a1);
        if (frm) send({ type: 'debug_frm', name: frm, arg1: a1.toString() });
        if (frm === "frmCaptcha") send({ type: 'captcha_alert' });
    }
});

Interceptor.attach(m.getExportByName('SDL_PollEvent'), {
    onEnter(args)  { this.eventPtr = args[0]; },
    onLeave(retval) {
        if (retval.toInt32() !== 1 || this.eventPtr.isNull()) return;
        const eventType = this.eventPtr.readU32();
        if (eventType === 0x401 && !injecting) {
            mouseWindowID = this.eventPtr.add(0x08).readU32();
            mouseWhich    = this.eventPtr.add(0x0C).readU32();
            mouseButton   = this.eventPtr.add(0x10).readU8();
            hasMouseInfo  = true;
            fakePos = {
                x: this.eventPtr.add(0x14).readS32(),
                y: this.eventPtr.add(0x18).readS32()
            };
            send({ type: 'captured', x: fakePos.x, y: fakePos.y });
        }
    }
});

recv('click',       function handler(msg) { triggerClick(msg.x, msg.y);                              recv('click',       handler); });
recv('key',         function handler(msg) { triggerKey(msg.scancode, msg.sym);                        recv('key',         handler); });
recv('drag_slider', function handler(msg) { triggerSliderDrag(msg.startX, msg.startY, msg.distanceX); recv('drag_slider', handler); });
recv('init_mouse', function handler(msg) {
    mouseWindowID = (msg.windowID !== undefined) ? msg.windowID : 1;
    mouseWhich    = (msg.which    !== undefined) ? msg.which    : 0;
    mouseButton   = (msg.button   !== undefined) ? msg.button   : 1;
    hasMouseInfo  = true;
    fakePos = { x: msg.x || 0, y: msg.y || 0 };
    send({ type: 'mouse_initialized', windowID: mouseWindowID, which: mouseWhich, button: mouseButton });
    recv('init_mouse', handler);
});
recv('spell', function handler(msg) {
    const x = msg.x, y = msg.y;
    pushEvent(buildKeyEvent(0x300, msg.scancode, msg.sym));
    setTimeout(() => {
        pushEvent(buildKeyEvent(0x301, msg.scancode, msg.sym));
        fakePos = { x, y };
        pushEvent(buildMotionEvent(x, y, 0));
        setTimeout(() => {
            injecting = true;
            pushEvent(buildButtonEvent(0x401, x, y));
            setTimeout(() => {
                pushEvent(buildButtonEvent(0x402, x, y));
                injecting = false;
                send({ type: 'click', x, y });
            }, 50);
        }, 16);
    }, 50);
    recv('spell', handler);
});

send({ type: 'ready' });
"""


# ---------------------------------------------
#  Captura de ventana
# ---------------------------------------------
def capture_window_full():
    hwnd = win32gui.FindWindow(None, GAME_WINDOW_TITLE)
    if not hwnd:
        print(f"[-] Ventana '{GAME_WINDOW_TITLE}' no encontrada.")
        return None, None

    rect  = win32gui.GetWindowRect(hwnd)
    win_w = rect[2] - rect[0]
    win_h = rect[3] - rect[1]

    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()
    bmp    = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfcDC, win_w, win_h)
    saveDC.SelectObject(bmp)

    windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)

    bmpinfo = bmp.GetInfo()
    bmpstr  = bmp.GetBitmapBits(True)
    img     = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                               bmpstr, 'raw', 'BGRX', 0, 1)

    win32gui.DeleteObject(bmp.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)

    return img, rect


# ---------------------------------------------
#  Estado de resultado de espera de formulario
# ---------------------------------------------
class WaitResult(enum.Enum):
    SUCCESS    = "success"
    OTHER_FORM = "other_form"
    TIMEOUT    = "timeout"


class FormWaitResult:
    def __init__(self, status: WaitResult, form: str | None = None):
        self.status = status
        self.form   = form

    @property
    def success(self) -> bool:
        return self.status == WaitResult.SUCCESS

    def __repr__(self):
        return f"FormWaitResult({self.status.value}, form={self.form!r})"


# ---------------------------------------------
#  GameInput
# ---------------------------------------------
class GameInput:
    def __init__(self):
        self._session           = None
        self._script            = None
        self._ready             = threading.Event()
        self._last_captured     = None
        self._mouse_initialized = False
        self._paused_by_captcha = False
        self._calibration_done  = False
        self._pause_lock        = threading.Lock()
        self._reconnect_in_progress = False

        self._current_form: str | None = None
        self._form_lock  = threading.Lock()
        self._form_event = threading.Event()

        self._on_resume_callback = None

    # -- Pause helpers ---------------------------------------------------------
    def _set_paused(self, value: bool):
        with self._pause_lock:
            self._paused_by_captcha = value

    def _is_paused(self) -> bool:
        with self._pause_lock:
            return self._paused_by_captcha

    # -- Resume callback -------------------------------------------------------
    def set_resume_callback(self, callback):
        self._on_resume_callback = callback

    # -- Frida attach / detach -------------------------------------------------
    def attach(self, auto_init_mouse: bool = True,
               window_id: int = 1, which: int = 0, button: int = 1) -> bool:
        try:
            self._session = frida.attach(PROCESS_NAME)
            self._script  = self._session.create_script(FRIDA_SCRIPT)
            self._script.on('message', self._on_message)
            self._script.load()
            if not self._ready.wait(timeout=5):
                return False
            print(f"[+] Adjuntado a {PROCESS_NAME}")

            if auto_init_mouse:
                self.init_mouse(window_id=window_id, which=which, button=button)

            return True
        except Exception as e:
            print(f"[-] Error attach: {e}")
            return False

    def init_mouse(self, window_id: int = 1, which: int = 0, button: int = 1,
                   x: int = 0, y: int = 0):
        if self._script:
            self._script.post({
                'type': 'init_mouse',
                'windowID': window_id,
                'which': which,
                'button': button,
                'x': x,
                'y': y,
            })

    def close(self):
        if self._session:
            self._session.detach()
            print("[*] Desconectado.")

    # -- Helpers internos de form --------------------------------------------
    def _reset_form_state(self):
        with self._form_lock:
            self._current_form = None
        self._form_event.clear()

    def _set_form(self, form_name: str):
        with self._form_lock:
            self._current_form = form_name
        self._form_event.set()

    # -- wait_for_form ---------------------------------------------------------
    def wait_for_form(self, expected: str, timeout: float = 5.0) -> FormWaitResult:
        deadline  = time.monotonic() + timeout
        last_seen = None

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return FormWaitResult(WaitResult.TIMEOUT, last_seen)

            self._form_event.clear()

            with self._form_lock:
                current = self._current_form

            if current is not None:
                if current != last_seen:
                    print(f"   [DBG] wait_for_form('{expected}') vio: '{current}'")
                    last_seen = current

                if current == expected:
                    return FormWaitResult(WaitResult.SUCCESS, current)

                with self._form_lock:
                    self._current_form = None

            self._form_event.wait(timeout=min(remaining, 0.1))

    # -- Drag captcha helper ---------------------------------------------------
    def _drag_captcha_away(self, from_x: int, from_y: int):
        """Arrastra frmCaptcha desde (from_x, from_y) hacia la esquina configurada."""
        distance_x = CAPTCHA_DRAG_DEST_X - from_x
        distance_y = CAPTCHA_DRAG_DEST_Y - from_y
        print(f"   [CAPTCHA DRAG] Arrastrando desde ({from_x},{from_y}) "
              f"hacia ({CAPTCHA_DRAG_DEST_X},{CAPTCHA_DRAG_DEST_Y}) "
              f"(delta: {distance_x},{distance_y})")
        self._script.post({
            'type': 'drag_slider',
            'startX': from_x,
            'startY': from_y,
            'distanceX': distance_x,
        })
        # Esperar a que termine el drag (15 pasos * 25ms + margen)
        time.sleep(0.6)

    # -- Reconnect guiado por estados ------------------------------------------
    _KEY_ESCAPE = (41, 0x0000001B)

    def _send_key(self, scancode: int, sym: int):
        if self._script:
            self._script.post({'type': 'key', 'scancode': scancode, 'sym': sym})

    def reconnect(self,
                  switch_x: int, switch_y: int,
                  confirm_x: int, confirm_y: int,
                  max_retries: int = 5,
                  wait_after: float = 6.0):
        if self._reconnect_in_progress:
            print("[RECONNECT] Ya hay uno en curso, ignorando.")
            return

        def _do_reconnect():
            self._reconnect_in_progress = True
            self._set_paused(True)
            print("\n[RECONNECT] Iniciando (basado en estados)...")

            try:
                # -- FASE 1: Escape -> frmSettings ----------------------------
                print("   [1/4] Escape -> esperando frmSettings...")
                self._reset_form_state()
                sc, sym = self._KEY_ESCAPE
                self._send_key(sc, sym)

                r = self.wait_for_form("frmSettings", timeout=8.0)
                if not r.success:
                    print(f"   [!] frmSettings no aparecio ({r}). Abortando.")
                    return

                print(f"   [ok] frmSettings detectado.")
                time.sleep(0.35)

                # -- FASE 2: Switch -> frmAskChange (con reintentos + captcha) -
                print("   [2/4] Switch -> esperando frmAskChange...")
                switch_ok = False

                for attempt in range(1, max_retries + 1):
                    self._reset_form_state()
                    t0 = time.monotonic()
                    print(f"   [DBG] t+{t0:.3f} | click Switch -> ({switch_x}, {switch_y})")
                    self._script.post({'type': 'click', 'x': switch_x, 'y': switch_y})

                    r = self.wait_for_form("frmAskChange", timeout=1.0)
                    elapsed = time.monotonic() - t0
                    print(f"   [DBG] t+{elapsed:.3f}s despues del click | resultado: {r}")

                    if r.success:
                        switch_ok = True
                        print(f"   [ok] frmAskChange detectado (intento {attempt}).")
                        break

                    # Si aparecio frmCaptcha encima del boton Switch, arrastrarlo y reintentar
                    if r.form == 'frmCaptcha':
                        print(f"   [!] frmCaptcha detectado sobre Switch (intento {attempt}). "
                              "Arrastrando fuera...")
                        self._drag_captcha_away(switch_x, switch_y)
                        continue  # reintenta el mismo attempt

                    print(f"   [Switch intento {attempt}/{max_retries}] {r} — "
                          f"form actual: {self._current_form!r}")

                if not switch_ok:
                    print("   [!] No se pudo abrir frmAskChange. Abortando.")
                    return

                # -- FASE 3: Confirm -> frmSelect (con reintentos + captcha) -
                print("   [3/4] Confirm -> esperando frmSelect...")
                select_ok = False

                for attempt in range(1, max_retries + 1):
                    self._reset_form_state()
                    t0 = time.monotonic()
                    print(f"   [DBG] t+{t0:.3f} | click Confirm -> ({confirm_x}, {confirm_y})")
                    self._script.post({'type': 'click',
                                       'x': confirm_x, 'y': confirm_y})

                    r = self.wait_for_form("frmSelect", timeout=6.0)
                    elapsed = time.monotonic() - t0
                    print(f"   [DBG] t+{elapsed:.3f}s | Confirm resultado: {r}")

                    if r.success:
                        select_ok = True
                        print(f"   [ok] frmSelect detectado (intento {attempt}).")
                        break

                    # Si aparecio frmCaptcha encima del boton Confirm, arrastrarlo y reintentar
                    if r.form == 'frmCaptcha':
                        print(f"   [!] frmCaptcha detectado sobre Confirm (intento {attempt}). "
                              "Arrastrando fuera...")
                        self._drag_captcha_away(confirm_x, confirm_y)
                        continue  # reintenta el mismo attempt

                    print(f"   [Confirm intento {attempt}/{max_retries}] {r}")

                if not select_ok:
                    print("   [!] frmSelect nunca aparecio. Abortando.")
                    return

                # -- FASE 4: Personaje + Start -> frmMain800 ------------------
                time.sleep(100.0)
                char_x, char_y = _PERSONAJE_COORDS.get(
                    NUMERO_PERSONAJE, _PERSONAJE_COORDS[1])
                print(f"   [4/4] Personaje {NUMERO_PERSONAJE} "
                      f"({char_x},{char_y}) + Start -> esperando frmMain800...")

                self._reset_form_state()
                print(f"   [DBG] click Personaje -> ({char_x}, {char_y})")
                self._script.post({'type': 'click', 'x': char_x, 'y': char_y})
                time.sleep(0.4)
                print(f"   [DBG] click Start -> ({_START_X}, {_START_Y})")
                self._script.post({'type': 'click', 'x': _START_X, 'y': _START_Y})

                r = self.wait_for_form("frmMain800", timeout=wait_after)
                if r.success:
                    print("   [ok] frmMain800 detectado — juego cargado.")
                else:
                    print(f"   [!] Timeout esperando frmMain800 ({r}). "
                          "El bot se reanuda de todas formas.")

            finally:
                self._reconnect_in_progress = False
                self._set_paused(False)
                print("[*] Bot REANUDADO.")
                winsound.Beep(800, 200)

                if self._on_resume_callback:
                    try:
                        self._on_resume_callback()
                    except Exception as e:
                        print(f"[-] Error en resume callback: {e}")

        threading.Thread(target=_do_reconnect, daemon=True).start()

    # -- Captcha handler -> reconnect directo ----------------------------------
    def _handle_captcha(self):
        print("\n[CAPTCHA DETECTADO] — reconectando automaticamente...")
        for _ in range(3):
            winsound.Beep(1600, 100)
            time.sleep(0.03)

        time.sleep(1.0)

        try:
            img, _ = capture_window_full()
            if img:
                fname = f"captcha_{int(time.time())}.jpg"
                img.save(fname, format="JPEG", quality=92)
                print(f"   [CAPTCHA] Screenshot guardado: {fname}")
        except Exception as e:
            print(f"   [CAPTCHA] No se pudo guardar screenshot: {e}")

        self.reconnect(SWITCH_X, SWITCH_Y, CONFIRM_X, CONFIRM_Y)

    # -- Message handler -------------------------------------------------------
    def _on_message(self, message, data):
        if message['type'] != 'send':
            return
        payload = message['payload']
        kind    = payload.get('type')

        if kind == 'ready':
            self._ready.set()

        elif kind == 'calibration_done':
            self._calibration_done = True
            print(f"[ok] Calibracion lista. idleArg1={payload.get('idleArg1')} "
                  f"| muestras={payload.get('totalSamples')}")

        elif kind == 'mouse_initialized':
            self._mouse_initialized = True
            print(f"[ok] Mouse inicializado sin click manual "
                  f"(windowID={payload.get('windowID')}, "
                  f"which={payload.get('which')}, button={payload.get('button')})")

        elif kind == 'captured':
            self._last_captured = (payload['x'], payload['y'])
            print(f"[+] Click capturado en ({payload['x']}, {payload['y']})")

        elif kind == 'debug_frm':
            form_name = payload.get('name')
            print(f"   [DEBUG] Form: {form_name} | arg1={payload.get('arg1')}")
            self._set_form(form_name)

        elif kind == 'error':
            print(f"[-] {payload['msg']}")

        elif kind == 'captcha_alert':
            # frmCaptcha actualiza el estado de form (permite que wait_for_form lo vea)
            self._set_form('frmCaptcha')
            if self._reconnect_in_progress:
                # El reconnect activo ya detectara frmCaptcha via wait_for_form
                # y lo arrastrara por su cuenta. No lanzar uno nuevo.
                print("[CAPTCHA] Reconnect ya en curso, ignorando alerta duplicada.")
                return
            threading.Thread(target=self._handle_captcha, daemon=True).start()

    # -- Spell / key map -------------------------------------------------------
    _SPELL_KEYS = {
        1: (58, 0x4000003A),
        2: (59, 0x4000003B),
        3: (60, 0x4000003C),
        4: (61, 0x4000003D),
    }

    # -- Acciones publicas -----------------------------------------------------
    def click_at(self, x: int, y: int):
        if self._is_paused():
            return
        if self._script:
            self._script.post({'type': 'click', 'x': x, 'y': y})

    def press_key(self, spell_number: int):
        if self._is_paused():
            return
        if self.ready:
            sc, sym = self._SPELL_KEYS[spell_number]
            self._script.post({'type': 'key', 'scancode': sc, 'sym': sym})

    def cast_spell(self, spell_number: int, x: int, y: int):
        if self._is_paused():
            return
        if self.ready:
            sc, sym = self._SPELL_KEYS[spell_number]
            self._script.post({'type': 'spell', 'scancode': sc, 'sym': sym, 'x': x, 'y': y})

    @property
    def ready(self):
        return self._mouse_initialized or self._last_captured is not None


# ---------------------------------------------
#  Entry point
# ---------------------------------------------
if __name__ == "__main__":
    bot = GameInput()
    if bot.attach():
        print("\n[*] Bot enlazado.")
        print("[!] Calibracion automatica (~3s)...")
        print("[!] Mouse inicializado automaticamente — no hace falta click manual.\n")

        while not bot.ready:
            time.sleep(0.4)

        print("\nListo. Hotkeys:")
        print("  F7  -> reconnect manual (guiado por estados)")
        print("  F10 -> screenshot debug")
        print("  F12 -> salir\n")

        def _hotkey_reconnect():
            print("\n[F7] Reconnect manual.")
            bot.reconnect(SWITCH_X, SWITCH_Y, CONFIRM_X, CONFIRM_Y)

        def _hotkey_screenshot():
            img, _ = capture_window_full()
            if img:
                fname = f"debug_{int(time.time())}.jpg"
                img.save(fname, format="JPEG", quality=92)
                print(f"\n[F10] Screenshot: {fname}")
            else:
                print("\n[F10] No se pudo capturar.")

        keyboard.add_hotkey('f7',  _hotkey_reconnect,  suppress=True)
        keyboard.add_hotkey('f10', _hotkey_screenshot, suppress=True)

        print("Hotkeys registrados. Presiona F12 para salir.")
        try:
            keyboard.wait('f12')
        except KeyboardInterrupt:
            pass
        finally:
            keyboard.unhook_all()
            bot.close()