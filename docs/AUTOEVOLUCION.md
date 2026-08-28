# Autoevolucion gobernada

Aegis puede estudiar fuentes publicas y promover mejoras de su modelo de
 gobernanza automaticamente, pero solo despues de superar controles medibles.

## Informe de aprendizaje explicable

El historial persistido de misiones puede consultarse sin acceder a fuentes ni
ejecutar herramientas externas:

```python
from a2s import AegisJupyter

informe = AegisJupyter("workspace").learning_report(
	objective="reversing", tool="ghidra", limit=100)
```

El resultado es JSON serializable e incluye el historial filtrado, métricas
agregadas, evidencia de herramientas seleccionadas por objetivo, exclusiones y
recomendaciones. Estas últimas solo aparecen cuando existe una aceptación
persistida; los registros corruptos se omiten y el límite evita informes sin
acotar.

## Activacion

En PowerShell:

```powershell
$env:A2S_AUTO_LEARN="1"
$env:A2S_AUTO_EVOLVE="1"
python -m a2s dashboard
```

`A2S_AUTO_EVOLVE` esta desactivado por defecto. La evolucion se intenta al
cerrar una mision cuando ya hay suficientes episodios. El aprendizaje de
repositorios sigue siendo documental: Aegis no ejecuta codigo remoto.

## Gates

- minimo de episodios para evolucion: 8;
- holdout independiente separado del entrenamiento;
- topologia compatible `12 -> 8 -> 1`;
- comparacion contra el `governance.json` existente;
- no se promueve un candidato peor que el baseline;
- escritura atomica y copia previa `governance.json.bak`;
- fallo registrado en el ledger como `neuroevolution_failed`;
- el modelo anterior permanece utilizable si un gate falla.

## Rollback

```python
from a2s.neuroevolve import rollback_governance
rollback_governance("workspace/.a2s")
```

El rollback restaura solo el ultimo backup gobernado. La autoevolucion no
modifica el codigo fuente de Aegis ni instala dependencias. Los cambios de
codigo requieren el flujo de staging, pruebas y revision del agente
DevLoop-MAX.

## Loop local de propuestas

Para mejoras controladas dentro de un workspace se puede usar
`AutonomousLoop` desde `AegisProject`. Las propuestas solo contienen rutas
relativas y contenido (o `None` para borrar); no ejecutan comandos ni cargan
repositorios externos. El evaluador recibe el `Path` del workspace y debe
devolver una métrica numérica reproducible.

```python
from a2s import ChangeProposal

loop = project.autonomy_loop()
loop.register_baseline(evaluate)
proposal = ChangeProposal("ajuste", {"config.json": "{}"})
loop.register_proposal(proposal)
result = loop.step(proposal, evaluate)
if result["accepted"]:
	loop.rollback(result["run_id"])
```

Cada iteración queda en `.a2s/autonomy/` con `diff.patch`, `result.json` y
`undo.json`, además de eventos encadenados en el `Ledger`. La aceptación exige
una mejora estricta y respeta `ChangeLimits(max_iterations, max_changed_files,
max_diff_lines, max_file_bytes, min_improvement)`; los rechazos se restauran
automáticamente.
