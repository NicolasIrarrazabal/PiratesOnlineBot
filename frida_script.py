# ─────────────────────────────────────────────────────────────────
#  Script Frida embebido (JavaScript inyectado en Game.exe)
#
#  Bloques principales:
#   1. Hooks de SetCursorPos / GetCursorPos  — suprime el cursor real
#      y devuelve la posición falsa al juego.
#   2. Constructores de eventos SDL2          — buildMotionEvent,
#      buildButtonEvent, buildKeyEvent arman structs SDL_Event en
#      memoria que luego se meten con SDL_PushEvent.
#   3. triggerClick / triggerSliderDrag /     — secuencias de eventos
#      triggerKey / spell                       con timers escalonados.
#   4. Calibración de idleArg1               — 60 muestras del primer
#      argumento de la función de menú para filtrar el "idle" y no
#      spamear logs con la forma que siempre está activa.
#   5. Hook de la función de menú (base+0x1F6990) — detecta cambios
#      de formulario (frmSettings, frmAskChange, frmCaptcha, etc.)
#      y los envía a Python via send().
#   6. Hook de SDL_PollEvent                 — captura windowID/which/
#      button de clicks reales para usarlos en eventos sintéticos.
#   7. Sistema de cancelación (pendingTimers / cancel_pending)
#      — todos los timers que arman secuencias de input se registran
#        en pendingTimers; al recibir 'cancel_pending' se borran de
#        golpe para no ejecutar acciones con estado desactualizado.
#   8. Receptores de mensajes Python         — click, key, drag_slider,
#      spell, cancel_pending, init_mouse, calibrate_click, set_autoloot.
# ─────────────────────────────────────────────────────────────────

FRIDA_SCRIPT = r"""
const m         = Process.getModuleByName('SDL2.dll');
const pushEvent = new NativeFunction(m.getExportByName('SDL_PushEvent'), 'int', ['pointer']);
const user32    = Process.getModuleByName('user32.dll');
const gameMod   = Process.findModuleByName("Game.exe") || Process.mainModule;
const base      = gameMod.base;

let fakePos   = null;
let injecting = false;

// ── Valores capturados de un click real (necesarios para eventos sintéticos) ──
let mouseWindowID = null;
let mouseWhich    = null;
let mouseButton   = null;
let hasMouseInfo  = false;

// ── Calibración de la forma "idle" ────────────────────────────────────────────
// Durante las primeras CALIBRATION_DURATION llamadas a la función de menú
// se cuenta cuál arg1 aparece más: ese es el "idle". A partir de ahí se
// filtra para no enviar debug_frm en cada frame.
let calibrationPhase = true;
let calibrationCount = 0;
const CALIBRATION_DURATION = 60;
let arg1Frequency = {};
let idleArg1 = null;

// ── Sistema de cancelación de acciones en vuelo ───────────────────────────────
// Cada setTimeout/setInterval que forma parte de una secuencia de input
// (key down→up, motion→button down→up, drag steps) se registra aquí.
// 'cancel_pending' los borra todos sin esperar confirmación.
let pendingTimers = [];

function track(fn, ms) {
    const id = setTimeout(fn, ms);
    pendingTimers.push(id);
    return id;
}

// ── 1. Hooks de cursor ────────────────────────────────────────────────────────
Interceptor.replace(user32.getExportByName('SetCursorPos'), new NativeCallback((x, y) => {
    return 1;  // no-op: el cursor real no se mueve
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

// ── 2. Constructores de eventos SDL2 ─────────────────────────────────────────
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

// ── 3. Acciones de input ──────────────────────────────────────────────────────
function triggerClick(x, y) {
    if (!hasMouseInfo) { send({ type: 'error', msg: 'Hace un click manual primero' }); return; }
    fakePos = { x, y };
    pushEvent(buildMotionEvent(x, y, 0));
    track(() => {
        injecting = true;
        pushEvent(buildButtonEvent(0x401, x, y));
        track(() => {
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
    track(() => {
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
                track(() => {
                    pushEvent(buildButtonEvent(0x402, currentX, startY));
                    injecting = false;
                    send({ type: 'slider_resolved', finalX: currentX, success: true });
                }, 60);
            }
        }, 25);
        pendingTimers.push(arrastre);
    }, 30);
}

function triggerKey(scancode, sym) {
    if (!hasMouseInfo) { send({ type: 'error', msg: 'Hace un click manual primero' }); return; }
    pushEvent(buildKeyEvent(0x300, scancode, sym));
    track(() => {
        pushEvent(buildKeyEvent(0x301, scancode, sym));
        send({ type: 'key', scancode });
    }, 50);
}

// ── 4 + 5. Calibración y detección de formularios ────────────────────────────
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

// ── 6. Hook SDL_PollEvent — captura windowID/which/button reales ──────────────
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

// ── 7 + 8. Receptores de mensajes Python ─────────────────────────────────────
recv('click',       function handler(msg) { triggerClick(msg.x, msg.y);                              recv('click',       handler); });
recv('key',         function handler(msg) { triggerKey(msg.scancode, msg.sym);                        recv('key',         handler); });
recv('drag_slider', function handler(msg) { triggerSliderDrag(msg.startX, msg.startY, msg.distanceX); recv('drag_slider', handler); });

recv('cancel_pending', function handler(msg) {
    for (const id of pendingTimers) { clearTimeout(id); clearInterval(id); }
    pendingTimers = [];
    injecting = false;
    recv('cancel_pending', handler);
});

recv('init_mouse', function handler(msg) {
    mouseWindowID = (msg.windowID !== undefined) ? msg.windowID : 1;
    mouseWhich    = (msg.which    !== undefined) ? msg.which    : 0;
    mouseButton   = (msg.button   !== undefined) ? msg.button   : 1;
    hasMouseInfo  = true;
    fakePos = { x: msg.x || 0, y: msg.y || 0 };
    send({ type: 'mouse_initialized', windowID: mouseWindowID, which: mouseWhich, button: mouseButton });
    recv('init_mouse', handler);
});

recv('calibrate_click', function handler(msg) {
    triggerClick(msg.x, msg.y);
    recv('calibrate_click', handler);
});

recv('spell', function handler(msg) {
    const x = msg.x, y = msg.y;
    pushEvent(buildKeyEvent(0x300, msg.scancode, msg.sym));
    track(() => {
        pushEvent(buildKeyEvent(0x301, msg.scancode, msg.sym));
        fakePos = { x, y };
        pushEvent(buildMotionEvent(x, y, 0));
        track(() => {
            injecting = true;
            pushEvent(buildButtonEvent(0x401, x, y));
            track(() => {
                pushEvent(buildButtonEvent(0x402, x, y));
                injecting = false;
                send({ type: 'click', x, y });
            }, 50);
        }, 16);
    }, 50);
    recv('spell', handler);
});

recv('set_autoloot', function handler(msg) {
    try {
        base.add(ptr(msg.offset)).writeU32(msg.value);
        send({ type: 'autoloot_set', offset: msg.offset, value: msg.value });
    } catch (e) {
        send({ type: 'error', msg: 'No se pudo escribir autoloot: ' + e.message });
    }
    recv('set_autoloot', handler);
});

send({ type: 'ready' });
"""