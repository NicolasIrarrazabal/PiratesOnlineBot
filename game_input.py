import threading
import time
import enum
import winsound

import frida

import config
from frida_script import FRIDA_SCRIPT


# ─────────────────────────────────────────────────────────────────
#  Script de autowalk embebido — SOLUCIÓN FINAL
# ─────────────────────────────────────────────────────────────────
AUTOWALK_SCRIPT = r"""
let estructuraDestino = null;
let addrX = null;
let addrY = null;

const moduleBase = Process.findModuleByName("game.exe")?.base;

if (!moduleBase) {
    send({ type: 'autowalk_error', msg: "No se pudo obtener la base de game.exe" });
} else {
    // Estructura original encargada de la ruta de destino (Caminar)
    estructuraDestino = moduleBase.add(0x7C2DA0);
    
    // Direcciones estáticas de Cheat Engine para leer tu posición actual
    addrX = moduleBase.add(0x151EB90);
    addrY = moduleBase.add(0x151EB00);
    
    send({ type: 'autowalk_ready', base: moduleBase.toString() });
}

function readPosition() {
    if (!addrX || !addrY) return null;
    try {
        // Lee tu posición real exacta usando Float como indica tu Cheat Table
        return {
            x: addrX.readFloat(),
            y: addrY.readFloat(),
            z: 0.0
        };
    } catch (e) {
        return null;
    }
}

function fijarDestino(nuevoX, nuevoY) {
    if (!estructuraDestino) {
        send({ type: 'autowalk_error', msg: "Estructura de destino no inicializada" });
        return;
    }
    try {
        // Escribimos en los offsets de destino para activar la rutina de caminata nativa
        const direccionX = estructuraDestino.add(0x1C);
        const direccionY = estructuraDestino.add(0x20);

        const valX = parseInt(nuevoX, 10);
        const valY = parseInt(nuevoY, 10);

        direccionX.writeInt(valX);
        direccionY.writeInt(valY);

        send({ type: 'autowalk_set', x: valX, y: valY });
    } catch (e) {
        send({ type: 'autowalk_error', msg: e.message });
    }
}

// PUSH automático cada 150ms a Python
setInterval(function() {
    const pos = readPosition();
    if (pos) {
        send({ type: 'autowalk_pos', x: pos.x, y: pos.y, z: pos.z });
    }
}, 150);

// Receptor para procesar las llamadas de movimiento de Python
recv('autowalk_set', function handler(msg) {
    fijarDestino(msg.x, msg.y);
    recv('autowalk_set', handler);
});
"""


# ─────────────────────────────────────────────────────────────────
#  Captura de ventana (screenshot para debug / captcha) -- Obsoleto/innecesario
# ─────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────
#  Tipos auxiliares
# ─────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────
#  GameInput
# ─────────────────────────────────────────────────────────────────
class GameInput:
    """Interfaz de alto nivel entre Python y el script Frida inyectado."""

    def __init__(self):
        self._session  = None
        self._script   = None
        self._ready    = threading.Event()

        self._aw_session = None
        self._aw_script  = None
        self._aw_ready   = threading.Event()
        self._aw_pos     = None          
        self._aw_pos_lock = threading.Lock()
        self._aw_pos_ts  = 0.0           

        self._last_captured      = None
        self._mouse_initialized  = False
        self._calibration_done   = False

        self._paused_by_captcha  = False
        self._pause_lock         = threading.Lock()
        self._reconnect_in_progress = False

        self._current_form: str | None = None
        self._form_lock  = threading.Lock()
        self._form_event = threading.Event()

        self._on_resume_callback = None

    def _set_paused(self, value: bool):
        with self._pause_lock:
            self._paused_by_captcha = value

    def _is_paused(self) -> bool:
        with self._pause_lock:
            return self._paused_by_captcha

    def set_resume_callback(self, callback):
        self._on_resume_callback = callback

    def attach(self, auto_init_mouse: bool = True,
               window_id: int = 1, which: int = 0, button: int = 1,
               calibrate_x: int = config.RECONNECT_CALIBRATE_X,
               calibrate_y: int = config.RECONNECT_CALIBRATE_Y) -> bool:
        try:
            self._session = frida.attach(config.PROCESS_NAME)
            self._script  = self._session.create_script(FRIDA_SCRIPT)
            self._script.on('message', self._on_message)
            self._script.load()
            if not self._ready.wait(timeout=5):
                return False
            print(f"[+] Adjuntado a {config.PROCESS_NAME}")

            self.set_autoloot()

            if auto_init_mouse:
                self.init_mouse(window_id=window_id, which=which, button=button)
                time.sleep(0.2)
                self.calibrate_click(calibrate_x, calibrate_y)

            self._aw_session = frida.attach(config.PROCESS_NAME)
            self._aw_script  = self._aw_session.create_script(AUTOWALK_SCRIPT)
            self._aw_script.on('message', self._on_autowalk_message)
            self._aw_script.load()
            if not self._aw_ready.wait(timeout=5):
                print("[!] Autowalk no respondió, movimiento desactivado.")
            else:
                print("[+] Autowalk cargado (Lectura CE + Ruta Destino).")

            return True
        except Exception as e:
            print(f"[-] Error attach: {e}")
            return False

    def close(self):
        if self._aw_session:
            self._aw_session.detach()
        if self._session:
            self._session.detach()
        print("[*] Desconectado.")

    def set_autoloot(self):
        if self._script:
            self._script.post({
                'type': 'set_autoloot',
                'offset': hex(config.AUTOLOOT_OFFSET),
                'value': config.AUTOLOOT_VALUE,
            })

    def init_mouse(self, window_id: int = 1, which: int = 0, button: int = 1,
                   x: int = 0, y: int = 0):
        if self._script:
            self._script.post({
                'type': 'init_mouse',
                'windowID': window_id, 'which': which,
                'button': button, 'x': x, 'y': y,
            })

    def calibrate_click(self, x: int, y: int):
        if self._script:
            print(f"   [CALIBRATE] Click de calibración -> ({x}, {y})")
            self._script.post({'type': 'calibrate_click', 'x': x, 'y': y})

    def cancel_pending_action(self):
        if self._script:
            self._script.post({'type': 'cancel_pending'})

    def _reset_form_state(self):
        with self._form_lock:
            self._current_form = None
        self._form_event.clear()

    def _set_form(self, form_name: str):
        with self._form_lock:
            self._current_form = form_name
        self._form_event.set()

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

    def _drag_captcha_away(self, from_x: int, from_y: int):
        distance_x = config.CAPTCHA_DRAG_DEST_X - from_x
        print(f"   [CAPTCHA DRAG] ({from_x},{from_y}) -> "
              f"({config.CAPTCHA_DRAG_DEST_X},{config.CAPTCHA_DRAG_DEST_Y})")
        self._script.post({
            'type': 'drag_slider',
            'startX': from_x,
            'startY': from_y,
            'distanceX': distance_x,
        })
        time.sleep(0.6)

    def _handle_captcha(self):
        print("\n[CAPTCHA DETECTADO] — reconectando automáticamente...")
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
        self.reconnect(config.SWITCH_X, config.SWITCH_Y,
                       config.CONFIRM_X, config.CONFIRM_Y)

    def _handle_death(self):
        winsound.Beep(400, 150)
        time.sleep(0.5)
        self._reset_form_state()
        self._script.post({'type': 'click', 'x': config.REVIVE_X, 'y': config.REVIVE_Y})
        print("   [REVIVIR] Click enviado.")

    def reconnect(self,
                  switch_x: int, switch_y: int,
                  confirm_x: int, confirm_y: int,
                  max_retries: int = 5,
                  wait_after: float = 6.0):
        if self._reconnect_in_progress:
            print("[RECONNECT] Ya hay uno en curso, ignorando.")
            return
        threading.Thread(target=self._do_reconnect,
                         args=(switch_x, switch_y, confirm_x, confirm_y,
                               max_retries, wait_after),
                         daemon=True).start()

    def _do_reconnect(self, switch_x, switch_y, confirm_x, confirm_y,
                      max_retries, wait_after):
        self._reconnect_in_progress = True
        self._set_paused(True)
        print("\n[RECONNECT] Iniciando (basado en estados)...")
        try:
            print("   [1/4] Escape -> esperando frmSettings...")
            self._reset_form_state()
            sc, sym = config.KEY_ESCAPE
            self._script.post({'type': 'key', 'scancode': sc, 'sym': sym})
            r = self.wait_for_form("frmSettings", timeout=8.0)
            if not r.success:
                print(f"   [!] frmSettings no apareció ({r}). Abortando.")
                return
            print("   [ok] frmSettings detectado.")
            time.sleep(0.35)

            print("   [2/4] Switch -> esperando frmAskChange...")
            switch_ok = False
            for attempt in range(1, max_retries + 1):
                self._reset_form_state()
                self._script.post({'type': 'click', 'x': switch_x, 'y': switch_y})
                r = self.wait_for_form("frmAskChange", timeout=1.0)
                if r.success:
                    switch_ok = True
                    print(f"   [ok] frmAskChange detectado (intento {attempt}).")
                    break
                if r.form == 'frmCaptcha':
                    print(f"   [!] frmCaptcha sobre Switch (intento {attempt}). Arrastrando...")
                    self._drag_captcha_away(switch_x, switch_y)
                    continue
                print(f"   [Switch {attempt}/{max_retries}] {r}")
            if not switch_ok:
                print("   [!] No se pudo abrir frmAskChange. Abortando.")
                return

            print("   [3/4] Confirm -> esperando frmSelect...")
            select_ok = False
            for attempt in range(1, max_retries + 1):
                self._reset_form_state()
                self._script.post({'type': 'click', 'x': confirm_x, 'y': confirm_y})
                r = self.wait_for_form("frmSelect", timeout=6.0)
                if r.success:
                    select_ok = True
                    print(f"   [ok] frmSelect detectado (intento {attempt}).")
                    break
                if r.form == 'frmCaptcha':
                    print(f"   [!] frmCaptcha sobre Confirm (intento {attempt}). Arrastrando...")
                    self._drag_captcha_away(confirm_x, confirm_y)
                    continue
                print(f"   [Confirm {attempt}/{max_retries}] {r}")
            if not select_ok:
                print("   [!] frmSelect nunca apareció. Abortando.")
                return

            time.sleep(1.0) 
            char_x, char_y = config.PERSONAJE_COORDS.get(
                config.NUMERO_PERSONAJE, config.PERSONAJE_COORDS[1])
            print(f"   [4/4] Personaje {config.NUMERO_PERSONAJE} ({char_x},{char_y}) + Start...")
            self._reset_form_state()
            self._script.post({'type': 'click', 'x': char_x, 'y': char_y})
            time.sleep(0.4)
            self._script.post({'type': 'click',
                               'x': config.START_X, 'y': config.START_Y})
            r = self.wait_for_form("frmMain800", timeout=wait_after)
            if r.success:
                print("   [ok] frmMain800 detectado — pantalla de carga lista.")
            else:
                print(f"   [!] Timeout frmMain800 ({r}). Esperando frmBell de todas formas.")
            print("   [4/4] Esperando frmBell (juego realmente listo)...")
            r_bell = self.wait_for_form("frmBell", timeout=15.0)
            if r_bell.success:
                print("   [ok] frmBell detectado — reanudando.")
            else:
                print(f"   [!] Timeout frmBell ({r_bell}). Reanudando igual.")
            time.sleep(0.3)
            self.calibrate_click(config.RECONNECT_CALIBRATE_X,
                                 config.RECONNECT_CALIBRATE_Y)
            self.set_autoloot()
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

    # ═════════════════════════════════════════════════════════════════
    #  AUTOWALK / TRAYECTOS
    # ═════════════════════════════════════════════════════════════════
    def get_position(self) -> dict | None:
        with self._aw_pos_lock:
            pos = self._aw_pos
        if pos is None:
            return None
        if time.monotonic() - self._aw_pos_ts > 3.0:
            return None
        return pos

    def walk_to(self, x: int, y: int):
        if self._aw_script:
            self._aw_script.post({'type': 'autowalk_set', 'x': x, 'y': y})
            print(f"   [WALK] Destino enviado: ({x}, {y})")

    def wait_for_arrival(self, target_x: int, target_y: int,
                         timeout: float = config.WALK_TIMEOUT,
                         threshold: float = config.WALK_ARRIVE_THRESHOLD) -> bool:
        deadline = time.monotonic() + timeout
        check_interval = 0.15
        tick_count = 0
        last_printed = ""

        while time.monotonic() < deadline:
            if self._is_paused():
                print("   [WALK] Bot pausado, esperando...")
                time.sleep(0.5)
                continue

            pos = self.get_position()
            tick_count += 1

            if pos is None:
                if tick_count % 10 == 0:
                    print(f"   [WALK] Esperando posición... (tick {tick_count})")
                time.sleep(check_interval)
                continue

            dx = abs(pos['x'] - target_x)
            dy = abs(pos['y'] - target_y)
            dist = (dx * dx + dy * dy) ** 0.5

            current_str = f"({pos['x']:.1f},{pos['y']:.1f}) dist={dist:.1f}"
            if tick_count % 10 == 0 or current_str != last_printed:
                print(f"   [WALK] Revisando... Pos: ({pos['x']:.2f}, {pos['y']:.2f}) | "
                      f"Destino: ({target_x}, {target_y}) | "
                      f"Dist: {dist:.2f} | Tick: {tick_count}")
                last_printed = current_str

            if dx <= threshold and dy <= threshold:
                print(f"   [WALK] ✓ LLEGADO a ({pos['x']:.2f}, {pos['y']:.2f}) — "
                      f"destino ({target_x}, {target_y}) en {tick_count} ticks")
                return True

            time.sleep(check_interval)

        print(f"   [WALK] ✗ Timeout esperando llegada a ({target_x}, {target_y}) "
              f"después de {tick_count} ticks ({timeout}s)")
        return False

    def execute_step(self, step: dict) -> bool:
        if self._is_paused():
            return False

        step_type = step.get('type')

        if step_type == 'walk':
            tx, ty = step['x'], step['y']
            timeout = step.get('wait_timeout', config.WALK_TIMEOUT)
            threshold = step.get('threshold', config.WALK_ARRIVE_THRESHOLD)
            max_walk_retries = step.get('retries', 3)

            for attempt in range(1, max_walk_retries + 1):
                pos = self.get_position()
                if pos:
                    print(f"   [DEBUG] Pos actual: ({pos['x']:.2f}, {pos['y']:.2f})  →  "
                          f"Caminando a: ({tx}, {ty})  (intento {attempt}/{max_walk_retries})")
                else:
                    print(f"   [DEBUG] Pos actual: (desconocida)  →  "
                          f"Caminando a: ({tx}, {ty})  (intento {attempt}/{max_walk_retries})")

                self.walk_to(tx, ty)
                arrived = self.wait_for_arrival(tx, ty, timeout=timeout, threshold=threshold)
                if arrived:
                    return True
                if attempt < max_walk_retries:
                    print(f"   [WALK] No llegó, reintentando en 1s...")
                    time.sleep(1.0)
            print(f"   [WALK] Falló después de {max_walk_retries} intentos. "
                  f"NO se ejecuta el siguiente paso.")
            return False

        elif step_type == 'spell':
            sx, sy = step['x'], step['y']
            spell_num = step.get('spell', config.SPELL_NUMBER)
            print(f"   [TRAYECTO] Lanzando hechizo {spell_num} en ({sx}, {sy})")
            return self.cast_spell(spell_num, sx, sy)

        elif step_type == 'click':
            cx, cy = step['x'], step['y']
            print(f"   [TRAYECTO] Click en ({cx}, {cy})")
            self.click_at(cx, cy)
            return True

        elif step_type == 'wait':
            secs = step.get('seconds', 1.0)
            print(f"   [TRAYECTO] Esperando {secs}s...")
            time.sleep(secs)
            return True

        else:
            print(f"   [TRAYECTO] Paso desconocido: {step}")
            return False

    def run_trayecto(self, trayecto: list, stop_event: threading.Event,
                     loop: bool = False):
        print(f"[*] Trayecto iniciado — {len(trayecto)} pasos"
              f"{' (en bucle)' if loop else ''}")
        iteration = 0

        while not stop_event.is_set():
            iteration += 1
            if loop:
                print(f"\n[*] === Iteración {iteration} ===")

            for i, step in enumerate(trayecto, 1):
                if stop_event.is_set():
                    break
                if self._is_paused():
                    print("   [TRAYECTO] Bot pausado, esperando reanudación...")
                    while self._is_paused() and not stop_event.is_set():
                        time.sleep(0.5)
                    if stop_event.is_set():
                        break

                print(f"\n   [TRAYECTO] Paso {i}/{len(trayecto)}: {step}")
                ok = self.execute_step(step)
                if not ok:
                    print(f"   [TRAYECTO] Paso {i} FALLÓ. Trayecto DETENIDO.")
                    if not loop:
                        stop_event.set()
                    break

            if not loop:
                break

        print("[*] Trayecto detenido.")

    # ── Handlers Frida ─────────────────────────────────────────────────────
    def _on_message(self, message, data):
        if message['type'] != 'send':
            return
        payload = message['payload']
        kind    = payload.get('type')

        if kind == 'ready':
            self._ready.set()
        elif kind == 'calibration_done':
            self._calibration_done = True
            print(f"[ok] Calibración lista. idleArg1={payload.get('idleArg1')} "
                  f"| muestras={payload.get('totalSamples')}")
        elif kind == 'mouse_initialized':
            self._mouse_initialized = True
            print(f"[ok] Mouse inicializado "
                  f"(windowID={payload.get('windowID')}, "
                  f"which={payload.get('which')}, button={payload.get('button')})")
        elif kind == 'death_alert':
            self._set_form('frmRelive')
            self.cancel_pending_action()
            if self._reconnect_in_progress:
                print("[MUERTE] Reconnect en curso, ignorando alerta duplicada.")
                return
            print("\n[MUERTE DETECTADA] — reviviendo automáticamente...")
            threading.Thread(target=self._handle_death, daemon=True).start()
        elif kind == 'captured':
            self._last_captured = (payload['x'], payload['y'])
            print(f"[+] Click capturado en ({payload['x']}, {payload['y']})")
        elif kind == 'debug_frm':
            form_name = payload.get('name')
            print(f"   [DEBUG] Form: {form_name} | arg1={payload.get('arg1')}")
            self._set_form(form_name)
        elif kind == 'error':
            print(f"[-] {payload['msg']}")
        elif kind == 'autoloot_set':
            print(f"[ok] Autoloot activado (offset={payload.get('offset')}, value={payload.get('value')})")
        elif kind == 'captcha_alert':
            self._set_form('frmCaptcha')
            self.cancel_pending_action()
            if self._reconnect_in_progress:
                print("[CAPTCHA] Reconnect ya en curso, ignorando alerta duplicada.")
                return
            threading.Thread(target=self._handle_captcha, daemon=True).start()

    def _on_autowalk_message(self, message, data):
        if message['type'] != 'send':
            return
        payload = message['payload']
        kind = payload.get('type')

        if kind == 'autowalk_ready':
            self._aw_ready.set()
            print(f"[ok] Autowalk ready (base={payload.get('base')})")
        elif kind == 'autowalk_pos':
            with self._aw_pos_lock:
                self._aw_pos = {
                    'x': payload.get('x'),
                    'y': payload.get('y'),
                    'z': payload.get('z')
                }
                self._aw_pos_ts = time.monotonic()
        elif kind == 'autowalk_set':
            print(f"   [AUTOWALK] Destino escrito en memoria: ({payload.get('x')}, {payload.get('y')})")
        elif kind == 'autowalk_error':
            print(f"[-] Autowalk error: {payload.get('msg')}")

    @property
    def ready(self) -> bool:
        return self._mouse_initialized or self._last_captured is not None

    def click_at(self, x: int, y: int):
        if not self._is_paused() and self._script:
            self._script.post({'type': 'click', 'x': x, 'y': y})

    def press_key(self, spell_number: int):
        if self._is_paused() or not self.ready:
            return
        sc, sym = config.SPELL_KEYS[spell_number]
        self._script.post({'type': 'key', 'scancode': sc, 'sym': sym})

    def cast_spell(self, spell_number: int, x: int, y: int) -> bool:
        if self._is_paused() or not self.ready:
            return False
        sc, sym = config.SPELL_KEYS[spell_number]
        self._script.post({'type': 'spell', 'scancode': sc, 'sym': sym, 'x': x, 'y': y})
        return True