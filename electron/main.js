/** A²S · OmniRoute Studio — proceso principal de Electron.
 *
 *  Qué hace: asegura que el gateway OmniRoute (npm, puerto 20128) esté
 *  arriba (lo arranca como proceso hijo si hace falta), abre la consola
 *  (renderer/index.html) y mata al gateway SOLO si fue él quien lo arrancó.
 *
 *  Seguridad: contextIsolation on, nodeIntegration off — la UI solo habla
 *  HTTP con 127.0.0.1. Todo local: nada sale de tu máquina salvo lo que
 *  el propio gateway envíe a los proveedores que TÚ enciendas.
 */
"use strict";

const { app, BrowserWindow, Menu } = require("electron");
const path = require("path");
const { asegurarGateway, PUERTO } = require("./gateway");

let win = null;
let child = null;           // solo se mata al salir si lo arrancamos nosotros

if (!app.requestSingleInstanceLock()) {
  console.log("ya hay una instancia de A²S·OmniRoute Studio corriendo");
  app.quit();
}

async function crearVentana() {
  const log = [];
  try {
    const r = await asegurarGateway(log);
    child = r.child;        // null si ya estaba corriendo
  } catch (e) {
    log.push("error arrancando gateway: " + e.message);
  }
  win = new BrowserWindow({
    width: 1280,
    height: 880,
    title: "A²S · OmniRoute Studio",
    icon: path.join(__dirname, "renderer", "icon.png"),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      spellcheck: false,
    },
  });
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { role: "appMenu" },
    { role: "editMenu" },
    { label: "Gateway", submenu: [
      { label: `Abrir panel (:${PUERTO})`, click: () => {
          require("electron").shell.openExternal(`http://127.0.0.1:${PUERTO}/dashboard`);
        } },
      { label: "Recargar consola", accelerator: "CmdOrCtrl+R", click: () => win.reload() },
    ] },
    { role: "viewMenu" },
  ]));
  await win.loadFile(path.join(__dirname, "renderer", "index.html"));
  win.webContents.send === undefined || win.setTitle("A²S · OmniRoute Studio");
  if (log.length) console.log(log.join("\n"));
}

app.whenReady().then(crearVentana);
app.on("second-instance", () => { if (win) { win.restore(); win.focus(); } });
app.on("window-all-closed", () => app.quit());
app.on("before-quit", () => {
  if (child) { try { child.kill(); } catch (_) {} }   // solo si lo arrancó la app
});
