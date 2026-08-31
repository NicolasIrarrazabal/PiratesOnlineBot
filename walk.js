/*
 * ============================================================
 * MOVIMIENTO MEDIANTE RADAR - Frida
 * ============================================================
 *
 * Estructura encontrada con Cheat Engine:
 *
 * Game.exe base: 0x140000000
 * Estructura de movimiento:    0x1407C5DE0
 * Offset:        0x7C5DE0
 *
 * Offsets identificados dentro de la estructura:
 *
 * +0x14 = X actual
 * +0x18 = Y actual
 * +0x1C = X objetivo
 * +0x20 = Y objetivo
 *
 * Posición actual del personaje:
 *
 * +0x1521C30 = X (float)
 * +0x1521BA0 = Y (float)
 *
 * 0x35AE0 fue encontrado mediante Cheat Engine
 * observando la función ejecutada al utilizar el radar.
 *
 * La función recibe:
 *
 * RCX = estructura del radar
 * RDX = X actual
 * R8  = Y actual
 * R9  = X objetivo
 * 5º parámetro = Y objetivo
 *
 * A diferencia de escribir directamente +0x1C/+0x20,
 * 0x35AE0 ejecuta además la lógica interna del juego
 * necesaria para iniciar el movimiento.
 * ============================================================
 */

const game = Process.getModuleByName("Game.exe");

// Estructura del radar
const radar = game.base.add(0x7C5DE0);

// Posición actual del personaje (float)
const ptrActualX = game.base.add(0x1521C30);
const ptrActualY = game.base.add(0x1521BA0);

// Se importa fnMover encontrada dentro del juego
const fnMover = game.base.add(0x35AE0);

const llamarMover = new NativeFunction(
    fnMover,
    "void",
    [
        "pointer", // RCX = estructura movimiento
        "uint32",  // RDX = X actual
        "uint32",  // R8  = Y actual
        "uint32",  // R9  = X objetivo
        "uint32"   // Y objetivo
    ]
);

function mover(x, y) {

    // Leer posición actual como float
    const actualX = Math.trunc(ptrActualX.readFloat());
    const actualY = Math.trunc(ptrActualY.readFloat());

    console.log(
        "Moviendo:",
        actualX,
        actualY,
        "->",
        x,
        y
    );

    // Ejecutar la función interna del juego
    llamarMover(
        radar,
        actualX,
        actualY,
        x,
        y
    );
}