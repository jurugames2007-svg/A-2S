# Política de crecimiento mediante proyectos abiertos

## Decisión

A²S **no usa OmniRoute como base** y no incorpora su árbol fuente. Lo conecta
como gateway local OpenAI-compatible opcional y estudia patrones públicos para
mejorar componentes propios. El núcleo de A²S continúa siendo Python stdlib,
con su scheduler, permisos, memoria, verificadores y cadena de custodia.

La misma política se aplica a cualquier proyecto futuro:

1. leer metadatos/documentación pública;
2. confirmar licencia SPDX abierta;
3. registrar fuente, fecha y lección;
4. diseñar una solución propia ajustada a A²S;
5. probarla contra contratos y guardrails de A²S;
6. no instalar ni ejecutar código encontrado durante el scouting;
7. si alguna vez se copia/modifica código, hacerlo solo mediante una decisión
   separada con atribución, compatibilidad de licencia, revisión y tests.

## Snapshot auditado — 2026-08-22

Metadatos consultados mediante la API pública de GitHub. Las estrellas son una
foto temporal, no un criterio de seguridad ni una promesa de calidad.

| Proyecto | Licencia reportada | Señal que aporta |
|---|---:|---|
| [OmniRoute](https://github.com/diegosouzapw/OmniRoute) | MIT | topología de proveedores, ruta explicable, estados de cuota, control plane |
| [RouteLLM](https://github.com/lm-sys/RouteLLM) | Apache-2.0 | evaluación coste/calidad del router |
| [Bifrost](https://github.com/maximhq/bifrost) | Apache-2.0 | hot path, carga y latencia de gateway |
| [Portkey Gateway](https://github.com/Portkey-AI/gateway) | MIT | políticas, guardrails y fallback declarativo |
| [Semantic Router](https://github.com/aurelio-labs/semantic-router) | MIT | decisión rápida sin llamada generativa |
| [TensorZero](https://github.com/tensorzero/tensorzero) | Apache-2.0 | experimentos, evals y optimización trazable |
| [Helicone](https://github.com/Helicone/helicone) | Apache-2.0 | observabilidad de peticiones y variantes |
| [Prompt flow](https://github.com/microsoft/promptflow) | MIT | evaluaciones como código y flujo reproducible |
| [vLLM](https://github.com/vllm-project/vllm) | Apache-2.0 | inferencia local compatible y benchmarks |
| [Plano](https://github.com/katanemo/plano) | Apache-2.0 | separación control/data plane y guardrails |
| [Future AGI](https://github.com/future-agi/future-agi) | Apache-2.0 | evals, simulaciones y datasets de regresión |
| [Aisix](https://github.com/api7/aisix) | Apache-2.0 | rate limits y caché en gateway Rust |
| [OpenZiti LLM Gateway](https://github.com/openziti/llm-gateway) | Apache-2.0 | identidad y segmentación zero trust |

Los últimos cuatro fueron hallados por una ejecución real de `a2s scout` el
2026-08-22 (24 candidatos, 15 incorporados al workspace de prueba, cero código
ejecutado) y promovidos al catálogo semilla tras verificar su SPDX pública.

Repositorios cuyo endpoint de GitHub devolvió licencia `NOASSERTION` o
`UNKNOWN` se excluyen automáticamente del catálogo aceptado, aunque sean
conocidos popularmente como abiertos. El filtro es conservador: primero se
resuelve la licencia, después se estudia.

## Qué se implementó a partir del análisis

No se copiaron módulos de los proyectos anteriores. Se añadieron capacidades
nativas y acotadas:

- `ProviderPool.route_preview(kind)`: ranking y factores sin llamada upstream;
- estados `healthy`, `approaching_limit`, `exhausted` y `unknown` con fuente;
- corrección del scheduler: puntuar N candidatos ya no consume N cuotas;
- A²S Control Plane: misión, SSE, topología, radar, conocimiento y assurance;
- `a2s scout`: descubrimiento incremental de proyectos con licencia abierta;
- catálogo persistente `.a2s/ecosystem/projects.json`, con
  `code_executed: false`;
- seguridad web: CSP, `X-Frame-Options`, `nosniff`, SameSite y validación de
  Origin en mutaciones.

## OmniRoute incluido por npm

Desde A²S 1.13, OmniRoute es una dependencia npm fijada y el launcher la
administra en loopback:

```bash
npm install
a2s pool-status
a2s route-preview --kind plan
a2s run "objetivo verificable"       # auto; no requiere --provider
```

No se instala un modelo LLM local. OmniRoute aporta rutas keyless iniciales y
el modelo lógico `auto`; sus upstreams siguen requiriendo red y están sujetos
a sus propios términos. A²S no extrae credenciales del gateway ni evade
cuotas. Para ejecución Python directa, un gateway ya existente todavía puede
declararse con `A2S_OMNIROUTE_URL` o `examples/pool.omniroute.json`. El
fallback heurístico permanece disponible y `A2S_OMNIROUTE=off` impide el
arranque automático.

## Radar continuo

```bash
# Consultas multidominio predefinidas
python -m a2s scout --workspace workspace

# Investigación dirigida
python -m a2s scout --workspace workspace \
  --query "llm gateway observability evaluation self hosted"

# Evidencia estructurada
python -m a2s scout --workspace workspace --json
```

Pipeline:

```text
GitHub público → normalizar metadata → comprobar SPDX → modelo de permisos
→ puntuar relevancia/frescura → deduplicar → persistir fuente → revisión
```

El radar no garantiza que un repositorio sea seguro. Solo garantiza que la
entrada al catálogo pasó verificaciones mínimas de fuente, licencia y
relevancia. La adopción técnica exige un experimento separado según
[`METODOLOGIA_OPTIMO_TEORICO.md`](METODOLOGIA_OPTIMO_TEORICO.md).

## Cómo añadir nuevas fuentes sin perder control

- ampliar consultas, no listas de endpoints ejecutables;
- mantener un presupuesto pequeño de API y respetar `Retry-After`;
- exigir HTTPS de GitHub y `full_name` válido;
- versionar la lista SPDX aceptada;
- registrar rechazos y no reinterpretar `UNKNOWN` como aprobado;
- revisar trimestralmente licencia, actividad y lecciones;
- borrar o degradar señales que no mejoren ningún experimento;
- nunca convertir popularidad en autoridad.
