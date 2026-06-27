import frida
import time

PROCESS_NAME = "Game.exe"

FRIDA_SCRIPT = r"""
const m         = Process.getModuleByName('SDL2.dll');
const user32    = Process.getModuleByName('user32.dll');

const EVENT_NAMES = {
    0x300: 'SDL_KEYDOWN',
    0x301: 'SDL_KEYUP',
    0x400: 'SDL_MOUSEMOTION',
    0x401: 'SDL_MOUSEBUTTONDOWN',
    0x402: 'SDL_MOUSEBUTTONUP',
    0x403: 'SDL_MOUSEWHEEL',
};

let recording = false;
let sequence  = [];

function dumpKeyEvent(ptr) {
    return {
        windowID : ptr.add(0x08).readU32(),
        state    : ptr.add(0x0C).readU8(),
        repeat   : ptr.add(0x0D).readU8(),
        scancode : ptr.add(0x10).readU32(),
        sym      : ptr.add(0x14).readU32(),
        mod      : ptr.add(0x18).readU16(),
    };
}

function dumpMouseButtonEvent(ptr) {
    return {
        windowID : ptr.add(0x08).readU32(),
        which    : ptr.add(0x0C).readU32(),
        button   : ptr.add(0x10).readU8(),
        state    : ptr.add(0x11).readU8(),
        clicks   : ptr.add(0x12).readU8(),
        x        : ptr.add(0x14).readS32(),
        y        : ptr.add(0x18).readS32(),
    };
}

function dumpMotionEvent(ptr) {
    return {
        windowID : ptr.add(0x08).readU32(),
        which    : ptr.add(0x0C).readU32(),
        state    : ptr.add(0x10).readU32(),
        x        : ptr.add(0x14).readS32(),
        y        : ptr.add(0x18).readS32(),
        xrel     : ptr.add(0x1C).readS32(),
        yrel     : ptr.add(0x20).readS32(),
    };
}

Interceptor.attach(m.getExportByName('SDL_PollEvent'), {
    onEnter(args)  { this.eventPtr = args[0]; },
    onLeave(retval) {
        if (retval.toInt32() !== 1 || this.eventPtr.isNull()) return;
        const type = this.eventPtr.readU32();
        const name = EVENT_NAMES[type] || null;
        if (!name) return;  // ignorar eventos que no nos interesan

        let data = null;
        if (type === 0x300 || type === 0x301) {
            data = dumpKeyEvent(this.eventPtr);
            // Tecla 1 (scancode 30) activa/desactiva grabación
            if (type === 0x300 && data.scancode === 30) {
                recording = true;
                sequence  = [];
                send({ type: 'record_start' });
            }
        } else if (type === 0x401 || type === 0x402) {
            data = dumpMouseButtonEvent(this.eventPtr);
            // Click izquierdo (button=1) mientras grabamos → fin de secuencia
            if (recording && type === 0x402 && data.button === 1) {
                recording = false;
                send({ type: 'record_end', sequence });
            }
        } else if (type === 0x400) {
            data = dumpMotionEvent(this.eventPtr);
        }

        if (recording || (type === 0x300 && data && data.scancode === 30)) {
            const entry = { type: '0x' + type.toString(16), name, data };
            sequence.push(entry);
            send({ type: 'event', entry });
        }
    }
});

send({ type: 'ready' });
"""


def on_message(message, data):
    if message['type'] != 'send':
        return
    payload = message['payload']
    kind    = payload.get('type')

    if kind == 'ready':
        print("[+] Hook activo")
        print("[*] Lanzá un hechizo a mano (presioná 1 y hacé click en el área)")
        print("[*] Podés repetirlo varias veces — cada secuencia se muestra completa")
        print("-" * 60)

    elif kind == 'record_start':
        print("\n>>> Tecla 1 detectada — grabando secuencia...")

    elif kind == 'event':
        e = payload['entry']
        d = e['data']
        if 'scancode' in d:
            print(f"  {e['name']:25s} scancode={d['scancode']} sym=0x{d['sym']:x} repeat={d['repeat']}")
        elif 'button' in d:
            print(f"  {e['name']:25s} button={d['button']} x={d['x']} y={d['y']} which={d['which']}")
        elif 'xrel' in d:
            # mousemotion — solo mostrar si hay movimiento real
            if d['xrel'] != 0 or d['yrel'] != 0:
                print(f"  {e['name']:25s} x={d['x']} y={d['y']} rel=({d['xrel']},{d['yrel']})")

    elif kind == 'record_end':
        print("<<< Secuencia completa capturada")
        print("-" * 60)
        seq = payload['sequence']
        print(f"[*] Total eventos: {len(seq)}")
        # Buscar el click final
        for ev in seq:
            if ev['name'] == 'SDL_MOUSEBUTTONDOWN':
                d = ev['data']
                print(f"[*] Click en: x={d['x']} y={d['y']} windowID={d['windowID']} which={d['which']} button={d['button']}")
        print("-" * 60)


session = frida.attach(PROCESS_NAME)
script  = session.create_script(FRIDA_SCRIPT)
script.on('message', on_message)
script.load()

print(f"[+] Adjuntado a {PROCESS_NAME}")

try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\n[*] Saliendo...")
    session.detach()