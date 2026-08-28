# A²S · OmniRoute Studio (Electron)

Consola de escritorio para el gateway OmniRoute: lo arranca solo, lo vigila,
trae chat de prueba y mantiene la regla *Caution* siempre a la vista.
100% local — la UI solo habla con `127.0.0.1`.

## Puesta en marcha (tu máquina)

```bash
# 1) el gateway (una vez)
npm install -g omniroute@latest

# 2) esta app
cd electron/
npm install          # descarga Electron (~100 MB, una sola vez)
npm start            # abre la consola
```

Si el gateway ya estaba corriendo, la app lo respeta y NO lo apaga al salir
(solo mata procesos que ella misma arrancó).

## Qué verificested ya el repo (sin Electron)

```bash
npm run check   # node --check de main.js y gateway.js + prueba real del gateway
```

`gateway.js` es Node puro (sin dependencias): arranque/detección del
proceso, salud por sondeo de puerto y chat de prueba — verificado contra un
omniroute 3.8.49 real en ejecución.

## La regla que vive en la UI

La lista *Caution* (los 17 proveedores con cláusulas de uso personal o
anti-proxy + cualquier endpoint `-web` revertido) está renderizada en rojo
en la ventana, siempre visible. Fuente: `docs/reference/FREE_TIERS.md` del
propio OmniRoute (reauditada cada 2 semanas). Los free tiers legítimos
(Kilo Code, Requesty, Z.AI GLM, Cerebras, OpenRouter :free, Ollama) van en
verde. Decides tú — la app no enciende nada por ti.

## Notas de seguridad

- `contextIsolation: true`, `nodeIntegration: false`: la ventana no tiene
  acceso a Node, solo HTTP a localhost.
- El gateway escucha en tu máquina; lo que envíe a proveedores depende de
  los que TÚ enciendas (regla Caution arriba).
- Un solo gateway por puerto: si :20128 está ocupado por otra cosa, la app
  lo detecta y lo usa tal cual (no lo mata).
