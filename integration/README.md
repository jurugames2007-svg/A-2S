Resumen del plan de integración
===============================

Este directorio contiene utilidades y planes para ingestar, analizar y preparar la integración
de una lista de repositorios y recursos externos en el agente A-2S.

IMPORTANTE: Muchos recursos listados pueden incluir herramientas de seguridad ofensiva o código
potencialmente peligroso. El script de automatización exige la bandera `--allow-dangerous` para
operaciones que clonen o ejecuten/analicen repositorios marcados como "peligrosos". Asegúrate de
entender y aceptar los riesgos antes de ejecutar.

Archivos principales
- `catalog.json`: Lista de fuentes a integrar (63 links)
- `clone_and_analyze.py`: Script inicial para clonar y ejecutar análisis estático básico

Uso rápido
```
python integration/clone_and_analyze.py --catalog integration/catalog.json --out integration/results
```

Requisitos
- Git instalado y accesible en `PATH`.
- Python 3.10+ recomendado.
