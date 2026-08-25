// ====================================================================
// SCRIPT DE MOVIMIENTO (AUTOWALK) CORREGIDO - TALES OF PIRATES
// Optimizado para Frida 17+ (Windows x64)
// ====================================================================

let estructuraDestino = null;
let ptrPosicionX = null;

const moduleBase = Process.findModuleByName("game.exe")?.base;

if (!moduleBase) {
    console.log("[-] Error: No se pudo obtener la base de 'game.exe'.");
} else {
    estructuraDestino = moduleBase.add(0x7C2DA0);
    ptrPosicionX = moduleBase.add(0x823510);

    console.log("[+] Base de Game.exe detectada en: " + moduleBase);
    console.log("[+] Sistema de sincronización de Autowalk cargado.");
    console.log("[!] Funciones listas: fijarDestino(x, y) y verPosicion()");
}

function verPosicion() {
    if (!ptrPosicionX) return null;
    try {
        return ptrPosicionX.readAnsiString();
    } catch (e) {
        return null;
    }
}

/**
 * Modifica las coordenadas con un desfase de tiempo controlado para obligar
 * al pathfinding del juego a trazar la diagonal correcta hacia (X, Y).
 */
function fijarDestino(nuevoX, nuevoY) {
    if (!estructuraDestino) {
        console.log("[-] Error: La estructura de memoria de destino no está inicializada.");
        return;
    }

    try {
        const direccionX = estructuraDestino.add(0x1C);
        const direccionY = estructuraDestino.add(0x20);

        const valX = parseInt(nuevoX, 10);
        const valY = parseInt(nuevoY, 10);

        // PASO 1: Escribimos primero el eje Y
        direccionY.writeInt(valY);

        // PASO 2: Introducimos un retraso de 20 milisegundos antes de meter la X.
        // Esto rompe el conflicto del algoritmo del juego y lo fuerza a sincronizar ambos ejes.
        setTimeout(function() {
            direccionX.writeInt(valX);
            console.log(`[+] Destino sincronizado con éxito -> X: ${valX} | Y: ${valY}`);
        }, 20);

    } catch (e) {
        console.log("[-] Error al escribir el destino en memoria: " + e.message);
    }
}