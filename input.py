import frida
import time
import threading

PROCESS_NAME = "Game.exe"

FRIDA_SCRIPT = r"""
const m         = Process.getModuleByName('SDL2.dll');
const pushEvent = new NativeFunction(m.getExportByName('SDL_PushEvent'), 'int', ['pointer']);
const user32    = Process.getModuleByName('user32.dll');

let fakePos  = null;
let injecting = false;

// Valores del mouse capturados del primer click real
let mouseWindowID = null;
let mouseWhich    = null;
let mouseButton   = null;
let hasMouseInfo  = false;

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

// SDL_MouseButtonEvent layout (verificado con dump):
// 00: type     Uint32
// 04: timestamp Uint32
// 08: windowID Uint32
// 0C: which    Uint32  (mouse device id)
// 10: button   Uint8
// 11: state    Uint8
// 12: clicks   Uint8
// 13: padding
// 14: x        Sint32
// 18: y        Sint32
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

function buildMotionEvent(x, y) {
    const ev = Memory.alloc(32);
    ev.writeU32(0x400);
    ev.add(0x04).writeU32(0);
    ev.add(0x08).writeU32(mouseWindowID);
    ev.add(0x0C).writeU32(mouseWhich);
    ev.add(0x10).writeU32(0);
    ev.add(0x14).writeS32(x);
    ev.add(0x18).writeS32(y);
    return ev;
}

// SDL_KeyboardEvent layout (verificado con dump):
// 00: type      Uint32
// 04: timestamp Uint32
// 08: windowID  Uint32
// 0C: state     Uint8
// 0D: repeat    Uint8
// 0E-0F: padding
// 10: scancode  Uint32
// 14: sym       Uint32
// 18: mod       Uint16
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
    if (!hasMouseInfo) {
        send({ type: 'error', msg: 'Hacé un click manual primero' });
        return;
    }
    // Motion directo al destino, sin importar desde dónde viene el mouse
    fakePos = { x, y };
    pushEvent(buildMotionEvent(x, y));
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

function triggerKey(scancode, sym) {
    if (!hasMouseInfo) {
        send({ type: 'error', msg: 'Hacé un click manual primero' });
        return;
    }
    pushEvent(buildKeyEvent(0x300, scancode, sym));
    setTimeout(() => {
        pushEvent(buildKeyEvent(0x301, scancode, sym));
        send({ type: 'key', scancode });
    }, 50);
}

Interceptor.attach(m.getExportByName('SDL_PollEvent'), {
    onEnter(args)  { this.eventPtr = args[0]; },
    onLeave(retval) {
        if (retval.toInt32() !== 1 || this.eventPtr.isNull()) return;
        const eventType = this.eventPtr.readU32();

        // Captura click real → guarda windowID, which, button por separado
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

recv('click', function handler(msg) {
    triggerClick(msg.x, msg.y);
    recv('click', handler);
});

recv('key', function handler(msg) {
    triggerKey(msg.scancode, msg.sym);
    recv('key', handler);
});

recv('spell', function handler(msg) {
    // KEYDOWN → KEYUP → motion → click
    const x = msg.x;
    const y = msg.y;

    pushEvent(buildKeyEvent(0x300, msg.scancode, msg.sym));  // KEYDOWN
    setTimeout(() => {
        pushEvent(buildKeyEvent(0x301, msg.scancode, msg.sym));  // KEYUP
        fakePos = { x, y };
        pushEvent(buildMotionEvent(x, y));                       // motion al destino
        setTimeout(() => {
            injecting = true;
            pushEvent(buildButtonEvent(0x401, x, y));            // MOUSEBUTTONDOWN
            setTimeout(() => {
                pushEvent(buildButtonEvent(0x402, x, y));        // MOUSEBUTTONUP
                injecting = false;
                send({ type: 'click', x, y });
            }, 50);
        }, 16);
    }, 50);

    recv('spell', handler);
});

send({ type: 'ready' });
"""


class GameInput:
    def __init__(self):
        self._session       = None
        self._script        = None
        self._ready         = threading.Event()
        self._last_captured = None

    def attach(self) -> bool:
        try:
            self._session = frida.attach(PROCESS_NAME)
            self._script  = self._session.create_script(FRIDA_SCRIPT)
            self._script.on('message', self._on_message)
            self._script.load()

            if not self._ready.wait(timeout=5):
                print("[-] Timeout esperando al script Frida")
                return False

            print(f"[+] Adjuntado a {PROCESS_NAME}")
            return True

        except frida.ProcessNotFoundError:
            print(f"[-] Proceso '{PROCESS_NAME}' no encontrado")
            return False
        except Exception as e:
            print(f"[-] Error attach: {e}")
            return False

    def close(self):
        if self._session:
            self._session.detach()
            self._session = None
            self._script  = None
            print("[*] Desconectado")

    def _on_message(self, message, data):
        if message['type'] != 'send':
            return
        payload = message['payload']
        kind    = payload.get('type')

        if kind == 'ready':
            self._ready.set()
        elif kind == 'click':
            print(f"[+] Click enviado en ({payload['x']}, {payload['y']})")
        elif kind == 'captured':
            self._last_captured = (payload['x'], payload['y'])
            print(f"[+] Click capturado en ({payload['x']}, {payload['y']})")
        elif kind == 'key':
            print(f"[+] Tecla enviada (scancode={payload['scancode']})")
        elif kind == 'error':
            print(f"[-] {payload['msg']}")

    _SPELL_KEYS = {
        1: (30, 0x31),
        2: (31, 0x32),
        3: (32, 0x33),
        4: (33, 0x34),
    }

    def click_at(self, x: int, y: int):
        if self._script is None:
            print("[-] Script no cargado.")
            return
        self._script.post({'type': 'click', 'x': x, 'y': y})

    def press_key(self, spell_number: int):
        if not self.ready:
            print("[-] Hacé un click manual en el juego primero")
            return
        scancode, sym = self._SPELL_KEYS.get(spell_number, (None, None))
        if scancode is None:
            print(f"[-] Hechizo {spell_number} no soportado (1-4)")
            return
        self._script.post({'type': 'key', 'scancode': scancode, 'sym': sym})

    def cast_spell(self, spell_number: int, x: int, y: int):
        if not self.ready:
            print("[-] Hacé un click manual en el juego primero")
            return
        scancode, sym = self._SPELL_KEYS.get(spell_number, (None, None))
        if scancode is None:
            print(f"[-] Hechizo {spell_number} no soportado (1-4)")
            return
        print(f"[*] Lanzando hechizo {spell_number} en ({x}, {y})")
        self._script.post({'type': 'spell', 'scancode': scancode, 'sym': sym, 'x': x, 'y': y})

    def click_last(self):
        if self._last_captured is None:
            print("[-] No hay click capturado aún")
            return
        self.click_at(*self._last_captured)

    @property
    def last_captured(self):
        return self._last_captured

    @property
    def ready(self):
        return self._last_captured is not None