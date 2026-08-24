# Distribución ejecutable con npm

A²S 1.17.0 se puede instalar como paquete npm sin reescribir ni duplicar el
núcleo Python. Node aporta el launcher, instala y supervisa OmniRoute; el
runtime del agente sigue siendo Python stdlib auditable.

## Requisitos

- Node.js `>=22.22.2 <23` o Node.js 24–26 (contrato del OmniRoute incluido);
- npm 10 o superior recomendado;
- Python 3.9 o superior en `PATH`, o `A2S_PYTHON=/ruta/python`.

No hay dependencias **Python** de runtime. npm instala exactamente OmniRoute
`3.8.49`; en el checkout, `package-lock.json` fija también la resolución
transitiva. A²S no define hooks de instalación propios; npm sí ejecuta el
`postinstall` publicado por OmniRoute,
necesario para ajustar sus módulos nativos a la plataforma. Por eso una
instalación operativa no debe usar `--ignore-scripts`.

## Release local completa

```bash
npm ci --ignore-scripts
npm run release:local
```

`release:local` ejecuta:

1. sintaxis de todos los scripts Node/GUI/Electron;
2. compilación Python;
3. pureza stdlib y complejidad;
4. suite Python completa, incluidas misiones, fuzz y contrato Python 3.9;
5. auditoría viva;
6. creación de zipapp y tarball;
7. instalación del tarball en un prefijo temporal;
8. smoke de los tres comandos npm y de OmniRoute incluido;
9. `doctor`, `/healthz` y GUI HTTP del paquete instalado.

Artefactos:

```text
artifacts/a2s.pyz
artifacts/a2s-agent-control-plane-1.15.0.tgz
```

## Instalación del tarball

```bash
npm install -g ./artifacts/a2s-agent-control-plane-1.17.0.tgz

a2s --version
a2s doctor                         # arranca/verifica OmniRoute incluido
a2s run "objetivo verificable"     # no requiere --provider
a2s research "tema"                # repos + PDF abiertos + aprendizaje
a2s book "tema"                    # Markdown + HTML + PDF + quality gate
a2s protocol "analiza tres opciones" --json  # capacidades, sin proveedor
a2s dashboard
```

El launcher arranca OmniRoute como sidecar local cuando un comando necesita
razonamiento. No utiliza el CLI que importa `src`/tsx: ejecuta directamente
`dist/server-ws.mjs` (o `dist/server.js`), prepara el directorio de datos y su
clave de cifrado, y espera un catálogo válido. Si ya escucha en
`127.0.0.1:20128`, lo reutiliza. En procesos largos lo comprueba cada 15 s y lo
recupera si cae. La ruta `auto` siempre entra por SORL y conserva el fallback
heurístico si el gateway o sus upstreams no pueden responder.

El sidecar que A²S inicia queda ligado a loopback y con login desactivado; el
Control Plane A²S también abre sin login en localhost. `--auth` sigue
existiendo como opción explícita para quien decida exponer el dashboard en
red. No se crea ni se solicita contraseña.

Alias equivalentes:

```bash
a2s-control-plane dashboard
a2s-agent-control-plane dashboard
```

Desinstalación:

```bash
npm uninstall -g a2s-agent-control-plane
```

Los workspaces creados por A²S no se borran durante la desinstalación.

## Uso desde el registry

Después de que el operador publique explícitamente el paquete:

```bash
npm install -g a2s-agent-control-plane
# o, sin instalación permanente:
npx a2s-agent-control-plane --version
npx a2s-agent-control-plane dashboard
```

La publicación no es parte de `npm run build` ni de `release:local`. Requiere
una cuenta npm configurada por el operador y se realiza conscientemente:

```bash
npm login
npm publish
```

`prepublishOnly` vuelve a ejecutar los gates y el E2E antes de permitir la
publicación.

## Comandos para desarrollo

```bash
npm test                 # suite Python completa
npm run test:fuzz        # fuzz determinista
npm run test:npm         # tarball instalado + CLI/HTTP/GUI
npm run check            # todos los gates sin empaquetar
npm run build            # zipapp + tarball
npm run release:local    # check + build + E2E
npm start                # Control Plane desde el checkout
npm run doctor
npm run a2s -- run "objetivo"
```

## Resolución de problemas

### «A²S requiere Python 3.9 o superior»

Instala Python o indica la ruta sin argumentos adicionales:

```bash
A2S_PYTHON=/opt/python3.12/bin/python3 a2s --version
```

En Windows PowerShell:

```powershell
$env:A2S_PYTHON = "C:\Python312\python.exe"
a2s --version
```

### OmniRoute no arranca

Comprueba primero que la versión de Node satisface el rango requerido y que la
instalación se hizo sin `--ignore-scripts`:

```bash
node --version
npm rebuild omniroute
npm run gateway
npm run gateway:status
npm run gateway:stop       # detener el daemon en un checkout
```

A²S administra su sidecar sin login ni intervención. `a2s doctor` informa si
un gateway externo reutilizado pide clave; solo en ese caso, y si el operador
eligió mantener esa autenticación, puede definir `A2S_OMNIROUTE_KEY`. Para
omitir totalmente el gateway: `A2S_OMNIROUTE=off a2s run "objetivo"`; el agente
seguirá con su fallback heurístico. Para conservar deliberadamente el login de
un sidecar administrado, el escape avanzado es `A2S_OMNIROUTE_LOGIN=on`.

### El dashboard no debe ser público

Por defecto escucha únicamente en `127.0.0.1`. Para exponerlo, utiliza token y
TLS en un reverse proxy:

```bash
a2s token --workspace workspace --hours 1
a2s dashboard --workspace workspace --public --auth
```

### Verificar el tarball sin instalar

```bash
npm pack --dry-run --json --ignore-scripts
npm run test:npm
```

El E2E usa un directorio temporal y lo elimina al finalizar. Los artefactos de
`artifacts/` están ignorados por Git y se pueden reconstruir en cualquier
momento.
