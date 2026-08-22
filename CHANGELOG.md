# Changelog

Todos los cambios relevantes de A²S se documentan aquí. El proyecto usa
versionado semántico mientras la API pública permanece en evolución.

## [1.10.0] — 2026-08-22

### Añadido

- Distribución npm `a2s-agent-control-plane`, sin dependencias npm de runtime.
- Ejecutables npm `a2s` y `a2s-control-plane` para Linux, macOS y Windows.
- Detección explícita de Python ≥3.9 y soporte de `A2S_PYTHON`.
- `npm run build`: genera zipapp ejecutable y tarball npm en `artifacts/`.
- `npm run test:npm`: instala el tarball en un prefijo aislado y prueba CLI,
  doctor, servidor HTTP, healthz y GUI empaquetada.
- `npm run release:local`: ejecuta todos los gates y construye la distribución.
- Archivo de licencia MIT incluido en los artefactos Python y npm.

### Compatibilidad

- El paquete npm es un launcher: Node administra la UX de instalación y Python
  stdlib ejecuta el núcleo A²S. No descarga Python ni ejecuta scripts de
  instalación ocultos.
- Requiere Node.js ≥18 y Python ≥3.9 disponibles en la máquina.

## [1.9.0] — 2026-08-22

### Añadido

- Agent Control Plane industrial, local-first y sin dependencias/CDN.
- Mission control con proveedor, estrategia, timebox, rondas y planes candidatos.
- Parada cooperativa, telemetría SSE y estado reanudable.
- Topología SORL, ranking de candidatos y factores de ruta explicables.
- `a2s route-preview`: decisión de cero llamadas y cero consumo de cuota.
- `a2s scout`: radar incremental de proyectos públicos con filtro SPDX.
- Catálogo OSS con OmniRoute, RouteLLM, Bifrost, Portkey, Semantic Router,
  TensorZero, Helicone, Prompt flow, vLLM y nuevas señales descubiertas.
- Integración explícita opcional de OmniRoute mediante `A2S_OMNIROUTE_URL`.
- Metodología abierta de mejora hacia el óptimo teórico y validación de propósito.
- 22 pruebas HTTP/GUI/ecosistema/ruteo/fuzz nuevas y misiones completas ungated.

### Corregido

- El scheduler ya no consume un hueco de cuota por cada candidato puntuado;
  reserva únicamente el endpoint elegido.
- El mini-shell espera todos los procesos de un pipeline y cierra pipes incluso
  en timeout, eliminando procesos huérfanos y `ResourceWarning`.
- Lecturas de auditoría, búsqueda, guardianes y tests cierran sus archivos.

### Seguridad

- CSP estricta, `X-Frame-Options: DENY`, `nosniff` y `Referrer-Policy`.
- Validación same-origin para mutaciones del Control Plane.
- Opciones de misión validadas/acotadas; no se expone `--unsafe` en la GUI.
- El radar no clona ni ejecuta código y rechaza licencias desconocidas.
- El dashboard ya no inicia una demo automáticamente salvo `--autodemo`.

### Verificación

- `python -m unittest discover -s tests -v`: 192 tests, sin skips.
- `a2s audit`: 5.0/5 en gates medibles.
- pureza runtime stdlib y complejidad media 4.53, máximo 34.
- wheel verificado con activos `a2s/ui/*` incluidos.

## [1.8.0] — anterior

- Modo servicio experimental con RBAC, fachada async y auditor ejecutable.

Para el historial de decisiones previo, véanse `README.md`, `LIMITACIONES.md`
y `ROADMAP_V2.md`.
