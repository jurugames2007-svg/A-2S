# Distribución ejecutable con npm

A²S 1.10.0 se puede instalar como paquete npm sin reescribir ni duplicar el
núcleo Python. Node aporta el launcher y npm aporta instalación/versionado; el
runtime real sigue siendo Python stdlib auditable.

## Requisitos

- Node.js 18 o superior;
- npm 9 o superior recomendado;
- Python 3.9 o superior en `PATH`, o `A2S_PYTHON=/ruta/python`.

No hay dependencias npm ni Python de runtime. La instalación no define hooks
`install`, `postinstall` o `prepare`.

## Release local completa

```bash
npm ci --ignore-scripts
npm run release:local
```

`release:local` ejecuta:

1. sintaxis de todos los scripts Node/GUI/Electron;
2. compilación Python;
3. pureza stdlib y complejidad;
4. 198 pruebas Python, incluidas misiones, fuzz y contrato Python 3.9;
5. auditoría viva;
6. creación de zipapp y tarball;
7. instalación del tarball en un prefijo temporal;
8. smoke de los tres comandos npm;
9. `doctor`, `/healthz` y GUI HTTP del paquete instalado.

Artefactos:

```text
artifacts/a2s.pyz
artifacts/a2s-agent-control-plane-1.10.0.tgz
```

## Instalación del tarball

```bash
npm install -g ./artifacts/a2s-agent-control-plane-1.10.0.tgz

a2s --version
a2s doctor
a2s dashboard
```

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
