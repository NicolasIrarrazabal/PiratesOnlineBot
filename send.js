const m = Process.getModuleByName('SDL2.dll');
const pushEvent = new NativeFunction(m.getExportByName('SDL_PushEvent'), 'int', ['pointer']);
const user32 = Process.getModuleByName('user32.dll');

let lastClick = null;
let fakePos = null;
let injecting = false;

Interceptor.replace(user32.getExportByName('SetCursorPos'), new NativeCallback((x, y) => {
    return 1;
}, 'int', ['int', 'int']));

Interceptor.attach(user32.getExportByName('GetCursorPos'), {
    onEnter(args) { this.buf = args[0]; },
    onLeave(retval) {
        if (fakePos !== null && retval.toInt32() !== 0) {
            this.buf.writeS32(fakePos.x);
            this.buf.add(4).writeS32(fakePos.y);
        }
    }
});

function buildButtonEvent(type, windowID, which, button, x, y) {
    const ev = Memory.alloc(64);
    ev.writeU32(type);
    ev.add(0x08).writeU32(windowID);
    ev.add(0x0C).writeU32(which);
    ev.add(0x10).writeU8(button);
    ev.add(0x11).writeU8(type === 0x401 ? 1 : 0);
    ev.add(0x12).writeU8(1);
    ev.add(0x14).writeS32(x);
    ev.add(0x18).writeS32(y);
    return ev;
}

function buildMotionEvent(windowID, which, x, y, state) {
    const ev = Memory.alloc(64);
    ev.writeU32(0x400);
    ev.add(0x08).writeU32(windowID);
    ev.add(0x0C).writeU32(which);
    ev.add(0x10).writeU32(state);
    ev.add(0x14).writeS32(x);
    ev.add(0x18).writeS32(y);
    return ev;
}

const getAsyncKeyState = new NativeFunction(
    user32.getExportByName('GetAsyncKeyState'),
    'int16', ['int']
);

let f6WasDown = false;
let f7WasDown = false;

setInterval(() => {
    const f6Down = getAsyncKeyState(0x75) < 0;
    const f7Down = getAsyncKeyState(0x76) < 0;

    if (f6Down && !f6WasDown && lastClick !== null) triggerClick(
        new Int32Array(lastClick.slice(0x14, 0x18))[0],
        new Int32Array(lastClick.slice(0x18, 0x1C))[0]
    );
    f6WasDown = f6Down;

    if (f7Down && !f7WasDown && lastClick !== null) triggerClick(500, 300);
    f7WasDown = f7Down;
}, 50);

function triggerClick(x, y) {
    injecting = true;
    const windowID = new Uint32Array(lastClick.slice(0x08, 0x0C))[0];
    const which    = new Uint32Array(lastClick.slice(0x0C, 0x10))[0];
    const button   = new Uint8Array(lastClick.slice(0x10, 0x11))[0];

    fakePos = {x, y};
    pushEvent(buildMotionEvent(windowID, which, x, y, 1 << (button - 1)));
    pushEvent(buildButtonEvent(0x401, windowID, which, button, x, y));

    setTimeout(() => {
        pushEvent(buildButtonEvent(0x402, windowID, which, button, x, y));
        injecting = false;
        console.log(`[*] Click en (${x}, ${y})`);
    }, 30);
}

Interceptor.attach(m.getExportByName('SDL_PollEvent'), {
    onEnter(args) { this.eventPtr = args[0]; },
    onLeave(retval) {
        if (retval.toInt32() !== 1 || this.eventPtr.isNull()) return;
        const eventType = this.eventPtr.readU32();

        if (injecting && eventType === 0x401) return;

        if (eventType === 0x401) {
            lastClick = this.eventPtr.readByteArray(64);
            fakePos = {
                x: this.eventPtr.add(0x14).readS32(),
                y: this.eventPtr.add(0x18).readS32()
            };
            console.log(`[+] Click capturado en (${fakePos.x}, ${fakePos.y})`);
        }
    }
});

console.log('[+] Hook activo | F6 = reinyectar capturado | F7 = reinyectar en (500,300)');