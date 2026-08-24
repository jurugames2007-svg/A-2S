# 1000 mejoras A²S 1.19 — núcleo PCB

Catálogo canónico. `a2s pcb apply` las instala en el workspace.
Total: 1000.

## pcb

1. `IMP-0001` PCB y tabla de procesos: persistencia atómica con fsync
1. `IMP-0002` PCB y tabla de procesos: journal append-only verificable
1. `IMP-0003` PCB y tabla de procesos: checkpoint del program counter
1. `IMP-0004` PCB y tabla de procesos: registros de contexto serializados
1. `IMP-0005` PCB y tabla de procesos: prioridad con envejecimiento
1. `IMP-0006` PCB y tabla de procesos: quantum cooperativo por cola
1. `IMP-0007` PCB y tabla de procesos: preemption cooperativa al slice
1. `IMP-0008` PCB y tabla de procesos: nice ajustable por trabajo
1. `IMP-0009` PCB y tabla de procesos: afinidad de cola Q0-Q3
1. `IMP-0010` PCB y tabla de procesos: herencia de prioridad del padre
1. `IMP-0011` PCB y tabla de procesos: wait-channel nominado
1. `IMP-0012` PCB y tabla de procesos: detección de espera circular
1. `IMP-0013` PCB y tabla de procesos: reaper de procesos zombie
1. `IMP-0014` PCB y tabla de procesos: reciclado seguro de pid
1. `IMP-0015` PCB y tabla de procesos: huella del workspace al admitir
1. `IMP-0016` PCB y tabla de procesos: deduplicación por hash de meta
1. `IMP-0017` PCB y tabla de procesos: backpressure al saturar ready
1. `IMP-0018` PCB y tabla de procesos: fair-share entre colas
1. `IMP-0019` PCB y tabla de procesos: MLFQ con promoción/democión
1. `IMP-0020` PCB y tabla de procesos: round-robin dentro de la cola
1. `IMP-0021` PCB y tabla de procesos: SJF aproximado por coste
1. `IMP-0022` PCB y tabla de procesos: deadline EDF si hay plazo
1. `IMP-0023` PCB y tabla de procesos: rate monotonic para periódicos
1. `IMP-0024` PCB y tabla de procesos: lottery ponderada por prioridad
1. `IMP-0025` PCB y tabla de procesos: robo de trabajo entre colas
1. `IMP-0026` PCB y tabla de procesos: migración parked→ready
1. `IMP-0027` PCB y tabla de procesos: park al StopToken
1. `IMP-0028` PCB y tabla de procesos: unpark idempotente
1. `IMP-0029` PCB y tabla de procesos: heartbeat por tick
1. `IMP-0030` PCB y tabla de procesos: watchdog de running colgado
1. `IMP-0031` PCB y tabla de procesos: cuenta de CPU acumulada
1. `IMP-0032` PCB y tabla de procesos: cuenta de espera acumulada
1. `IMP-0033` PCB y tabla de procesos: reintentos con backoff
1. `IMP-0034` PCB y tabla de procesos: señal de cancelación cooperativa
1. `IMP-0035` PCB y tabla de procesos: traza span por transición
1. `IMP-0036` PCB y tabla de procesos: métrica counter de admits
1. `IMP-0037` PCB y tabla de procesos: métrica gauge de ready
1. `IMP-0038` PCB y tabla de procesos: histograma de latencia de slice
1. `IMP-0039` PCB y tabla de procesos: SLO de reanudación <1s
1. `IMP-0040` PCB y tabla de procesos: presupuesto de error por cola
1. `IMP-0041` PCB y tabla de procesos: cuota de jobs concurrentes
1. `IMP-0042` PCB y tabla de procesos: slice de estudio en Q3
1. `IMP-0043` PCB y tabla de procesos: slice de estudio en Q2
1. `IMP-0044` PCB y tabla de procesos: pin de misión exclusiva Q1
1. `IMP-0045` PCB y tabla de procesos: chat nunca bloquea Q1
1. `IMP-0046` PCB y tabla de procesos: carga balanceada por kind
1. `IMP-0047` PCB y tabla de procesos: índice invertido pid/goal
1. `IMP-0048` PCB y tabla de procesos: snapshot JSON para /api/pcb
1. `IMP-0049` PCB y tabla de procesos: export del catálogo aplicado
1. `IMP-0050` PCB y tabla de procesos: marcador APPLIED de las 1000
## schedule

1. `IMP-0051` Planificador multinivel: persistencia atómica con fsync
1. `IMP-0052` Planificador multinivel: journal append-only verificable
1. `IMP-0053` Planificador multinivel: checkpoint del program counter
1. `IMP-0054` Planificador multinivel: registros de contexto serializados
1. `IMP-0055` Planificador multinivel: prioridad con envejecimiento
1. `IMP-0056` Planificador multinivel: quantum cooperativo por cola
1. `IMP-0057` Planificador multinivel: preemption cooperativa al slice
1. `IMP-0058` Planificador multinivel: nice ajustable por trabajo
1. `IMP-0059` Planificador multinivel: afinidad de cola Q0-Q3
1. `IMP-0060` Planificador multinivel: herencia de prioridad del padre
1. `IMP-0061` Planificador multinivel: wait-channel nominado
1. `IMP-0062` Planificador multinivel: detección de espera circular
1. `IMP-0063` Planificador multinivel: reaper de procesos zombie
1. `IMP-0064` Planificador multinivel: reciclado seguro de pid
1. `IMP-0065` Planificador multinivel: huella del workspace al admitir
1. `IMP-0066` Planificador multinivel: deduplicación por hash de meta
1. `IMP-0067` Planificador multinivel: backpressure al saturar ready
1. `IMP-0068` Planificador multinivel: fair-share entre colas
1. `IMP-0069` Planificador multinivel: MLFQ con promoción/democión
1. `IMP-0070` Planificador multinivel: round-robin dentro de la cola
1. `IMP-0071` Planificador multinivel: SJF aproximado por coste
1. `IMP-0072` Planificador multinivel: deadline EDF si hay plazo
1. `IMP-0073` Planificador multinivel: rate monotonic para periódicos
1. `IMP-0074` Planificador multinivel: lottery ponderada por prioridad
1. `IMP-0075` Planificador multinivel: robo de trabajo entre colas
1. `IMP-0076` Planificador multinivel: migración parked→ready
1. `IMP-0077` Planificador multinivel: park al StopToken
1. `IMP-0078` Planificador multinivel: unpark idempotente
1. `IMP-0079` Planificador multinivel: heartbeat por tick
1. `IMP-0080` Planificador multinivel: watchdog de running colgado
1. `IMP-0081` Planificador multinivel: cuenta de CPU acumulada
1. `IMP-0082` Planificador multinivel: cuenta de espera acumulada
1. `IMP-0083` Planificador multinivel: reintentos con backoff
1. `IMP-0084` Planificador multinivel: señal de cancelación cooperativa
1. `IMP-0085` Planificador multinivel: traza span por transición
1. `IMP-0086` Planificador multinivel: métrica counter de admits
1. `IMP-0087` Planificador multinivel: métrica gauge de ready
1. `IMP-0088` Planificador multinivel: histograma de latencia de slice
1. `IMP-0089` Planificador multinivel: SLO de reanudación <1s
1. `IMP-0090` Planificador multinivel: presupuesto de error por cola
1. `IMP-0091` Planificador multinivel: cuota de jobs concurrentes
1. `IMP-0092` Planificador multinivel: slice de estudio en Q3
1. `IMP-0093` Planificador multinivel: slice de estudio en Q2
1. `IMP-0094` Planificador multinivel: pin de misión exclusiva Q1
1. `IMP-0095` Planificador multinivel: chat nunca bloquea Q1
1. `IMP-0096` Planificador multinivel: carga balanceada por kind
1. `IMP-0097` Planificador multinivel: índice invertido pid/goal
1. `IMP-0098` Planificador multinivel: snapshot JSON para /api/pcb
1. `IMP-0099` Planificador multinivel: export del catálogo aplicado
1. `IMP-0100` Planificador multinivel: marcador APPLIED de las 1000
## resume

1. `IMP-0101` Reanudación tras corte: persistencia atómica con fsync
1. `IMP-0102` Reanudación tras corte: journal append-only verificable
1. `IMP-0103` Reanudación tras corte: checkpoint del program counter
1. `IMP-0104` Reanudación tras corte: registros de contexto serializados
1. `IMP-0105` Reanudación tras corte: prioridad con envejecimiento
1. `IMP-0106` Reanudación tras corte: quantum cooperativo por cola
1. `IMP-0107` Reanudación tras corte: preemption cooperativa al slice
1. `IMP-0108` Reanudación tras corte: nice ajustable por trabajo
1. `IMP-0109` Reanudación tras corte: afinidad de cola Q0-Q3
1. `IMP-0110` Reanudación tras corte: herencia de prioridad del padre
1. `IMP-0111` Reanudación tras corte: wait-channel nominado
1. `IMP-0112` Reanudación tras corte: detección de espera circular
1. `IMP-0113` Reanudación tras corte: reaper de procesos zombie
1. `IMP-0114` Reanudación tras corte: reciclado seguro de pid
1. `IMP-0115` Reanudación tras corte: huella del workspace al admitir
1. `IMP-0116` Reanudación tras corte: deduplicación por hash de meta
1. `IMP-0117` Reanudación tras corte: backpressure al saturar ready
1. `IMP-0118` Reanudación tras corte: fair-share entre colas
1. `IMP-0119` Reanudación tras corte: MLFQ con promoción/democión
1. `IMP-0120` Reanudación tras corte: round-robin dentro de la cola
1. `IMP-0121` Reanudación tras corte: SJF aproximado por coste
1. `IMP-0122` Reanudación tras corte: deadline EDF si hay plazo
1. `IMP-0123` Reanudación tras corte: rate monotonic para periódicos
1. `IMP-0124` Reanudación tras corte: lottery ponderada por prioridad
1. `IMP-0125` Reanudación tras corte: robo de trabajo entre colas
1. `IMP-0126` Reanudación tras corte: migración parked→ready
1. `IMP-0127` Reanudación tras corte: park al StopToken
1. `IMP-0128` Reanudación tras corte: unpark idempotente
1. `IMP-0129` Reanudación tras corte: heartbeat por tick
1. `IMP-0130` Reanudación tras corte: watchdog de running colgado
1. `IMP-0131` Reanudación tras corte: cuenta de CPU acumulada
1. `IMP-0132` Reanudación tras corte: cuenta de espera acumulada
1. `IMP-0133` Reanudación tras corte: reintentos con backoff
1. `IMP-0134` Reanudación tras corte: señal de cancelación cooperativa
1. `IMP-0135` Reanudación tras corte: traza span por transición
1. `IMP-0136` Reanudación tras corte: métrica counter de admits
1. `IMP-0137` Reanudación tras corte: métrica gauge de ready
1. `IMP-0138` Reanudación tras corte: histograma de latencia de slice
1. `IMP-0139` Reanudación tras corte: SLO de reanudación <1s
1. `IMP-0140` Reanudación tras corte: presupuesto de error por cola
1. `IMP-0141` Reanudación tras corte: cuota de jobs concurrentes
1. `IMP-0142` Reanudación tras corte: slice de estudio en Q3
1. `IMP-0143` Reanudación tras corte: slice de estudio en Q2
1. `IMP-0144` Reanudación tras corte: pin de misión exclusiva Q1
1. `IMP-0145` Reanudación tras corte: chat nunca bloquea Q1
1. `IMP-0146` Reanudación tras corte: carga balanceada por kind
1. `IMP-0147` Reanudación tras corte: índice invertido pid/goal
1. `IMP-0148` Reanudación tras corte: snapshot JSON para /api/pcb
1. `IMP-0149` Reanudación tras corte: export del catálogo aplicado
1. `IMP-0150` Reanudación tras corte: marcador APPLIED de las 1000
## memory

1. `IMP-0151` Memoria y recall: persistencia atómica con fsync
1. `IMP-0152` Memoria y recall: journal append-only verificable
1. `IMP-0153` Memoria y recall: checkpoint del program counter
1. `IMP-0154` Memoria y recall: registros de contexto serializados
1. `IMP-0155` Memoria y recall: prioridad con envejecimiento
1. `IMP-0156` Memoria y recall: quantum cooperativo por cola
1. `IMP-0157` Memoria y recall: preemption cooperativa al slice
1. `IMP-0158` Memoria y recall: nice ajustable por trabajo
1. `IMP-0159` Memoria y recall: afinidad de cola Q0-Q3
1. `IMP-0160` Memoria y recall: herencia de prioridad del padre
1. `IMP-0161` Memoria y recall: wait-channel nominado
1. `IMP-0162` Memoria y recall: detección de espera circular
1. `IMP-0163` Memoria y recall: reaper de procesos zombie
1. `IMP-0164` Memoria y recall: reciclado seguro de pid
1. `IMP-0165` Memoria y recall: huella del workspace al admitir
1. `IMP-0166` Memoria y recall: deduplicación por hash de meta
1. `IMP-0167` Memoria y recall: backpressure al saturar ready
1. `IMP-0168` Memoria y recall: fair-share entre colas
1. `IMP-0169` Memoria y recall: MLFQ con promoción/democión
1. `IMP-0170` Memoria y recall: round-robin dentro de la cola
1. `IMP-0171` Memoria y recall: SJF aproximado por coste
1. `IMP-0172` Memoria y recall: deadline EDF si hay plazo
1. `IMP-0173` Memoria y recall: rate monotonic para periódicos
1. `IMP-0174` Memoria y recall: lottery ponderada por prioridad
1. `IMP-0175` Memoria y recall: robo de trabajo entre colas
1. `IMP-0176` Memoria y recall: migración parked→ready
1. `IMP-0177` Memoria y recall: park al StopToken
1. `IMP-0178` Memoria y recall: unpark idempotente
1. `IMP-0179` Memoria y recall: heartbeat por tick
1. `IMP-0180` Memoria y recall: watchdog de running colgado
1. `IMP-0181` Memoria y recall: cuenta de CPU acumulada
1. `IMP-0182` Memoria y recall: cuenta de espera acumulada
1. `IMP-0183` Memoria y recall: reintentos con backoff
1. `IMP-0184` Memoria y recall: señal de cancelación cooperativa
1. `IMP-0185` Memoria y recall: traza span por transición
1. `IMP-0186` Memoria y recall: métrica counter de admits
1. `IMP-0187` Memoria y recall: métrica gauge de ready
1. `IMP-0188` Memoria y recall: histograma de latencia de slice
1. `IMP-0189` Memoria y recall: SLO de reanudación <1s
1. `IMP-0190` Memoria y recall: presupuesto de error por cola
1. `IMP-0191` Memoria y recall: cuota de jobs concurrentes
1. `IMP-0192` Memoria y recall: slice de estudio en Q3
1. `IMP-0193` Memoria y recall: slice de estudio en Q2
1. `IMP-0194` Memoria y recall: pin de misión exclusiva Q1
1. `IMP-0195` Memoria y recall: chat nunca bloquea Q1
1. `IMP-0196` Memoria y recall: carga balanceada por kind
1. `IMP-0197` Memoria y recall: índice invertido pid/goal
1. `IMP-0198` Memoria y recall: snapshot JSON para /api/pcb
1. `IMP-0199` Memoria y recall: export del catálogo aplicado
1. `IMP-0200` Memoria y recall: marcador APPLIED de las 1000
## sense

1. `IMP-0201` Percepción del workspace: persistencia atómica con fsync
1. `IMP-0202` Percepción del workspace: journal append-only verificable
1. `IMP-0203` Percepción del workspace: checkpoint del program counter
1. `IMP-0204` Percepción del workspace: registros de contexto serializados
1. `IMP-0205` Percepción del workspace: prioridad con envejecimiento
1. `IMP-0206` Percepción del workspace: quantum cooperativo por cola
1. `IMP-0207` Percepción del workspace: preemption cooperativa al slice
1. `IMP-0208` Percepción del workspace: nice ajustable por trabajo
1. `IMP-0209` Percepción del workspace: afinidad de cola Q0-Q3
1. `IMP-0210` Percepción del workspace: herencia de prioridad del padre
1. `IMP-0211` Percepción del workspace: wait-channel nominado
1. `IMP-0212` Percepción del workspace: detección de espera circular
1. `IMP-0213` Percepción del workspace: reaper de procesos zombie
1. `IMP-0214` Percepción del workspace: reciclado seguro de pid
1. `IMP-0215` Percepción del workspace: huella del workspace al admitir
1. `IMP-0216` Percepción del workspace: deduplicación por hash de meta
1. `IMP-0217` Percepción del workspace: backpressure al saturar ready
1. `IMP-0218` Percepción del workspace: fair-share entre colas
1. `IMP-0219` Percepción del workspace: MLFQ con promoción/democión
1. `IMP-0220` Percepción del workspace: round-robin dentro de la cola
1. `IMP-0221` Percepción del workspace: SJF aproximado por coste
1. `IMP-0222` Percepción del workspace: deadline EDF si hay plazo
1. `IMP-0223` Percepción del workspace: rate monotonic para periódicos
1. `IMP-0224` Percepción del workspace: lottery ponderada por prioridad
1. `IMP-0225` Percepción del workspace: robo de trabajo entre colas
1. `IMP-0226` Percepción del workspace: migración parked→ready
1. `IMP-0227` Percepción del workspace: park al StopToken
1. `IMP-0228` Percepción del workspace: unpark idempotente
1. `IMP-0229` Percepción del workspace: heartbeat por tick
1. `IMP-0230` Percepción del workspace: watchdog de running colgado
1. `IMP-0231` Percepción del workspace: cuenta de CPU acumulada
1. `IMP-0232` Percepción del workspace: cuenta de espera acumulada
1. `IMP-0233` Percepción del workspace: reintentos con backoff
1. `IMP-0234` Percepción del workspace: señal de cancelación cooperativa
1. `IMP-0235` Percepción del workspace: traza span por transición
1. `IMP-0236` Percepción del workspace: métrica counter de admits
1. `IMP-0237` Percepción del workspace: métrica gauge de ready
1. `IMP-0238` Percepción del workspace: histograma de latencia de slice
1. `IMP-0239` Percepción del workspace: SLO de reanudación <1s
1. `IMP-0240` Percepción del workspace: presupuesto de error por cola
1. `IMP-0241` Percepción del workspace: cuota de jobs concurrentes
1. `IMP-0242` Percepción del workspace: slice de estudio en Q3
1. `IMP-0243` Percepción del workspace: slice de estudio en Q2
1. `IMP-0244` Percepción del workspace: pin de misión exclusiva Q1
1. `IMP-0245` Percepción del workspace: chat nunca bloquea Q1
1. `IMP-0246` Percepción del workspace: carga balanceada por kind
1. `IMP-0247` Percepción del workspace: índice invertido pid/goal
1. `IMP-0248` Percepción del workspace: snapshot JSON para /api/pcb
1. `IMP-0249` Percepción del workspace: export del catálogo aplicado
1. `IMP-0250` Percepción del workspace: marcador APPLIED de las 1000
## plan

1. `IMP-0251` Plan fractal persistente: persistencia atómica con fsync
1. `IMP-0252` Plan fractal persistente: journal append-only verificable
1. `IMP-0253` Plan fractal persistente: checkpoint del program counter
1. `IMP-0254` Plan fractal persistente: registros de contexto serializados
1. `IMP-0255` Plan fractal persistente: prioridad con envejecimiento
1. `IMP-0256` Plan fractal persistente: quantum cooperativo por cola
1. `IMP-0257` Plan fractal persistente: preemption cooperativa al slice
1. `IMP-0258` Plan fractal persistente: nice ajustable por trabajo
1. `IMP-0259` Plan fractal persistente: afinidad de cola Q0-Q3
1. `IMP-0260` Plan fractal persistente: herencia de prioridad del padre
1. `IMP-0261` Plan fractal persistente: wait-channel nominado
1. `IMP-0262` Plan fractal persistente: detección de espera circular
1. `IMP-0263` Plan fractal persistente: reaper de procesos zombie
1. `IMP-0264` Plan fractal persistente: reciclado seguro de pid
1. `IMP-0265` Plan fractal persistente: huella del workspace al admitir
1. `IMP-0266` Plan fractal persistente: deduplicación por hash de meta
1. `IMP-0267` Plan fractal persistente: backpressure al saturar ready
1. `IMP-0268` Plan fractal persistente: fair-share entre colas
1. `IMP-0269` Plan fractal persistente: MLFQ con promoción/democión
1. `IMP-0270` Plan fractal persistente: round-robin dentro de la cola
1. `IMP-0271` Plan fractal persistente: SJF aproximado por coste
1. `IMP-0272` Plan fractal persistente: deadline EDF si hay plazo
1. `IMP-0273` Plan fractal persistente: rate monotonic para periódicos
1. `IMP-0274` Plan fractal persistente: lottery ponderada por prioridad
1. `IMP-0275` Plan fractal persistente: robo de trabajo entre colas
1. `IMP-0276` Plan fractal persistente: migración parked→ready
1. `IMP-0277` Plan fractal persistente: park al StopToken
1. `IMP-0278` Plan fractal persistente: unpark idempotente
1. `IMP-0279` Plan fractal persistente: heartbeat por tick
1. `IMP-0280` Plan fractal persistente: watchdog de running colgado
1. `IMP-0281` Plan fractal persistente: cuenta de CPU acumulada
1. `IMP-0282` Plan fractal persistente: cuenta de espera acumulada
1. `IMP-0283` Plan fractal persistente: reintentos con backoff
1. `IMP-0284` Plan fractal persistente: señal de cancelación cooperativa
1. `IMP-0285` Plan fractal persistente: traza span por transición
1. `IMP-0286` Plan fractal persistente: métrica counter de admits
1. `IMP-0287` Plan fractal persistente: métrica gauge de ready
1. `IMP-0288` Plan fractal persistente: histograma de latencia de slice
1. `IMP-0289` Plan fractal persistente: SLO de reanudación <1s
1. `IMP-0290` Plan fractal persistente: presupuesto de error por cola
1. `IMP-0291` Plan fractal persistente: cuota de jobs concurrentes
1. `IMP-0292` Plan fractal persistente: slice de estudio en Q3
1. `IMP-0293` Plan fractal persistente: slice de estudio en Q2
1. `IMP-0294` Plan fractal persistente: pin de misión exclusiva Q1
1. `IMP-0295` Plan fractal persistente: chat nunca bloquea Q1
1. `IMP-0296` Plan fractal persistente: carga balanceada por kind
1. `IMP-0297` Plan fractal persistente: índice invertido pid/goal
1. `IMP-0298` Plan fractal persistente: snapshot JSON para /api/pcb
1. `IMP-0299` Plan fractal persistente: export del catálogo aplicado
1. `IMP-0300` Plan fractal persistente: marcador APPLIED de las 1000
## exec

1. `IMP-0301` Ejecución por rebanadas: persistencia atómica con fsync
1. `IMP-0302` Ejecución por rebanadas: journal append-only verificable
1. `IMP-0303` Ejecución por rebanadas: checkpoint del program counter
1. `IMP-0304` Ejecución por rebanadas: registros de contexto serializados
1. `IMP-0305` Ejecución por rebanadas: prioridad con envejecimiento
1. `IMP-0306` Ejecución por rebanadas: quantum cooperativo por cola
1. `IMP-0307` Ejecución por rebanadas: preemption cooperativa al slice
1. `IMP-0308` Ejecución por rebanadas: nice ajustable por trabajo
1. `IMP-0309` Ejecución por rebanadas: afinidad de cola Q0-Q3
1. `IMP-0310` Ejecución por rebanadas: herencia de prioridad del padre
1. `IMP-0311` Ejecución por rebanadas: wait-channel nominado
1. `IMP-0312` Ejecución por rebanadas: detección de espera circular
1. `IMP-0313` Ejecución por rebanadas: reaper de procesos zombie
1. `IMP-0314` Ejecución por rebanadas: reciclado seguro de pid
1. `IMP-0315` Ejecución por rebanadas: huella del workspace al admitir
1. `IMP-0316` Ejecución por rebanadas: deduplicación por hash de meta
1. `IMP-0317` Ejecución por rebanadas: backpressure al saturar ready
1. `IMP-0318` Ejecución por rebanadas: fair-share entre colas
1. `IMP-0319` Ejecución por rebanadas: MLFQ con promoción/democión
1. `IMP-0320` Ejecución por rebanadas: round-robin dentro de la cola
1. `IMP-0321` Ejecución por rebanadas: SJF aproximado por coste
1. `IMP-0322` Ejecución por rebanadas: deadline EDF si hay plazo
1. `IMP-0323` Ejecución por rebanadas: rate monotonic para periódicos
1. `IMP-0324` Ejecución por rebanadas: lottery ponderada por prioridad
1. `IMP-0325` Ejecución por rebanadas: robo de trabajo entre colas
1. `IMP-0326` Ejecución por rebanadas: migración parked→ready
1. `IMP-0327` Ejecución por rebanadas: park al StopToken
1. `IMP-0328` Ejecución por rebanadas: unpark idempotente
1. `IMP-0329` Ejecución por rebanadas: heartbeat por tick
1. `IMP-0330` Ejecución por rebanadas: watchdog de running colgado
1. `IMP-0331` Ejecución por rebanadas: cuenta de CPU acumulada
1. `IMP-0332` Ejecución por rebanadas: cuenta de espera acumulada
1. `IMP-0333` Ejecución por rebanadas: reintentos con backoff
1. `IMP-0334` Ejecución por rebanadas: señal de cancelación cooperativa
1. `IMP-0335` Ejecución por rebanadas: traza span por transición
1. `IMP-0336` Ejecución por rebanadas: métrica counter de admits
1. `IMP-0337` Ejecución por rebanadas: métrica gauge de ready
1. `IMP-0338` Ejecución por rebanadas: histograma de latencia de slice
1. `IMP-0339` Ejecución por rebanadas: SLO de reanudación <1s
1. `IMP-0340` Ejecución por rebanadas: presupuesto de error por cola
1. `IMP-0341` Ejecución por rebanadas: cuota de jobs concurrentes
1. `IMP-0342` Ejecución por rebanadas: slice de estudio en Q3
1. `IMP-0343` Ejecución por rebanadas: slice de estudio en Q2
1. `IMP-0344` Ejecución por rebanadas: pin de misión exclusiva Q1
1. `IMP-0345` Ejecución por rebanadas: chat nunca bloquea Q1
1. `IMP-0346` Ejecución por rebanadas: carga balanceada por kind
1. `IMP-0347` Ejecución por rebanadas: índice invertido pid/goal
1. `IMP-0348` Ejecución por rebanadas: snapshot JSON para /api/pcb
1. `IMP-0349` Ejecución por rebanadas: export del catálogo aplicado
1. `IMP-0350` Ejecución por rebanadas: marcador APPLIED de las 1000
## chat

1. `IMP-0351` Chat paralelo a la misión: persistencia atómica con fsync
1. `IMP-0352` Chat paralelo a la misión: journal append-only verificable
1. `IMP-0353` Chat paralelo a la misión: checkpoint del program counter
1. `IMP-0354` Chat paralelo a la misión: registros de contexto serializados
1. `IMP-0355` Chat paralelo a la misión: prioridad con envejecimiento
1. `IMP-0356` Chat paralelo a la misión: quantum cooperativo por cola
1. `IMP-0357` Chat paralelo a la misión: preemption cooperativa al slice
1. `IMP-0358` Chat paralelo a la misión: nice ajustable por trabajo
1. `IMP-0359` Chat paralelo a la misión: afinidad de cola Q0-Q3
1. `IMP-0360` Chat paralelo a la misión: herencia de prioridad del padre
1. `IMP-0361` Chat paralelo a la misión: wait-channel nominado
1. `IMP-0362` Chat paralelo a la misión: detección de espera circular
1. `IMP-0363` Chat paralelo a la misión: reaper de procesos zombie
1. `IMP-0364` Chat paralelo a la misión: reciclado seguro de pid
1. `IMP-0365` Chat paralelo a la misión: huella del workspace al admitir
1. `IMP-0366` Chat paralelo a la misión: deduplicación por hash de meta
1. `IMP-0367` Chat paralelo a la misión: backpressure al saturar ready
1. `IMP-0368` Chat paralelo a la misión: fair-share entre colas
1. `IMP-0369` Chat paralelo a la misión: MLFQ con promoción/democión
1. `IMP-0370` Chat paralelo a la misión: round-robin dentro de la cola
1. `IMP-0371` Chat paralelo a la misión: SJF aproximado por coste
1. `IMP-0372` Chat paralelo a la misión: deadline EDF si hay plazo
1. `IMP-0373` Chat paralelo a la misión: rate monotonic para periódicos
1. `IMP-0374` Chat paralelo a la misión: lottery ponderada por prioridad
1. `IMP-0375` Chat paralelo a la misión: robo de trabajo entre colas
1. `IMP-0376` Chat paralelo a la misión: migración parked→ready
1. `IMP-0377` Chat paralelo a la misión: park al StopToken
1. `IMP-0378` Chat paralelo a la misión: unpark idempotente
1. `IMP-0379` Chat paralelo a la misión: heartbeat por tick
1. `IMP-0380` Chat paralelo a la misión: watchdog de running colgado
1. `IMP-0381` Chat paralelo a la misión: cuenta de CPU acumulada
1. `IMP-0382` Chat paralelo a la misión: cuenta de espera acumulada
1. `IMP-0383` Chat paralelo a la misión: reintentos con backoff
1. `IMP-0384` Chat paralelo a la misión: señal de cancelación cooperativa
1. `IMP-0385` Chat paralelo a la misión: traza span por transición
1. `IMP-0386` Chat paralelo a la misión: métrica counter de admits
1. `IMP-0387` Chat paralelo a la misión: métrica gauge de ready
1. `IMP-0388` Chat paralelo a la misión: histograma de latencia de slice
1. `IMP-0389` Chat paralelo a la misión: SLO de reanudación <1s
1. `IMP-0390` Chat paralelo a la misión: presupuesto de error por cola
1. `IMP-0391` Chat paralelo a la misión: cuota de jobs concurrentes
1. `IMP-0392` Chat paralelo a la misión: slice de estudio en Q3
1. `IMP-0393` Chat paralelo a la misión: slice de estudio en Q2
1. `IMP-0394` Chat paralelo a la misión: pin de misión exclusiva Q1
1. `IMP-0395` Chat paralelo a la misión: chat nunca bloquea Q1
1. `IMP-0396` Chat paralelo a la misión: carga balanceada por kind
1. `IMP-0397` Chat paralelo a la misión: índice invertido pid/goal
1. `IMP-0398` Chat paralelo a la misión: snapshot JSON para /api/pcb
1. `IMP-0399` Chat paralelo a la misión: export del catálogo aplicado
1. `IMP-0400` Chat paralelo a la misión: marcador APPLIED de las 1000
## research

1. `IMP-0401` Investigación continua: persistencia atómica con fsync
1. `IMP-0402` Investigación continua: journal append-only verificable
1. `IMP-0403` Investigación continua: checkpoint del program counter
1. `IMP-0404` Investigación continua: registros de contexto serializados
1. `IMP-0405` Investigación continua: prioridad con envejecimiento
1. `IMP-0406` Investigación continua: quantum cooperativo por cola
1. `IMP-0407` Investigación continua: preemption cooperativa al slice
1. `IMP-0408` Investigación continua: nice ajustable por trabajo
1. `IMP-0409` Investigación continua: afinidad de cola Q0-Q3
1. `IMP-0410` Investigación continua: herencia de prioridad del padre
1. `IMP-0411` Investigación continua: wait-channel nominado
1. `IMP-0412` Investigación continua: detección de espera circular
1. `IMP-0413` Investigación continua: reaper de procesos zombie
1. `IMP-0414` Investigación continua: reciclado seguro de pid
1. `IMP-0415` Investigación continua: huella del workspace al admitir
1. `IMP-0416` Investigación continua: deduplicación por hash de meta
1. `IMP-0417` Investigación continua: backpressure al saturar ready
1. `IMP-0418` Investigación continua: fair-share entre colas
1. `IMP-0419` Investigación continua: MLFQ con promoción/democión
1. `IMP-0420` Investigación continua: round-robin dentro de la cola
1. `IMP-0421` Investigación continua: SJF aproximado por coste
1. `IMP-0422` Investigación continua: deadline EDF si hay plazo
1. `IMP-0423` Investigación continua: rate monotonic para periódicos
1. `IMP-0424` Investigación continua: lottery ponderada por prioridad
1. `IMP-0425` Investigación continua: robo de trabajo entre colas
1. `IMP-0426` Investigación continua: migración parked→ready
1. `IMP-0427` Investigación continua: park al StopToken
1. `IMP-0428` Investigación continua: unpark idempotente
1. `IMP-0429` Investigación continua: heartbeat por tick
1. `IMP-0430` Investigación continua: watchdog de running colgado
1. `IMP-0431` Investigación continua: cuenta de CPU acumulada
1. `IMP-0432` Investigación continua: cuenta de espera acumulada
1. `IMP-0433` Investigación continua: reintentos con backoff
1. `IMP-0434` Investigación continua: señal de cancelación cooperativa
1. `IMP-0435` Investigación continua: traza span por transición
1. `IMP-0436` Investigación continua: métrica counter de admits
1. `IMP-0437` Investigación continua: métrica gauge de ready
1. `IMP-0438` Investigación continua: histograma de latencia de slice
1. `IMP-0439` Investigación continua: SLO de reanudación <1s
1. `IMP-0440` Investigación continua: presupuesto de error por cola
1. `IMP-0441` Investigación continua: cuota de jobs concurrentes
1. `IMP-0442` Investigación continua: slice de estudio en Q3
1. `IMP-0443` Investigación continua: slice de estudio en Q2
1. `IMP-0444` Investigación continua: pin de misión exclusiva Q1
1. `IMP-0445` Investigación continua: chat nunca bloquea Q1
1. `IMP-0446` Investigación continua: carga balanceada por kind
1. `IMP-0447` Investigación continua: índice invertido pid/goal
1. `IMP-0448` Investigación continua: snapshot JSON para /api/pcb
1. `IMP-0449` Investigación continua: export del catálogo aplicado
1. `IMP-0450` Investigación continua: marcador APPLIED de las 1000
## studio

1. `IMP-0451` Libros PPT PDF en vivo: persistencia atómica con fsync
1. `IMP-0452` Libros PPT PDF en vivo: journal append-only verificable
1. `IMP-0453` Libros PPT PDF en vivo: checkpoint del program counter
1. `IMP-0454` Libros PPT PDF en vivo: registros de contexto serializados
1. `IMP-0455` Libros PPT PDF en vivo: prioridad con envejecimiento
1. `IMP-0456` Libros PPT PDF en vivo: quantum cooperativo por cola
1. `IMP-0457` Libros PPT PDF en vivo: preemption cooperativa al slice
1. `IMP-0458` Libros PPT PDF en vivo: nice ajustable por trabajo
1. `IMP-0459` Libros PPT PDF en vivo: afinidad de cola Q0-Q3
1. `IMP-0460` Libros PPT PDF en vivo: herencia de prioridad del padre
1. `IMP-0461` Libros PPT PDF en vivo: wait-channel nominado
1. `IMP-0462` Libros PPT PDF en vivo: detección de espera circular
1. `IMP-0463` Libros PPT PDF en vivo: reaper de procesos zombie
1. `IMP-0464` Libros PPT PDF en vivo: reciclado seguro de pid
1. `IMP-0465` Libros PPT PDF en vivo: huella del workspace al admitir
1. `IMP-0466` Libros PPT PDF en vivo: deduplicación por hash de meta
1. `IMP-0467` Libros PPT PDF en vivo: backpressure al saturar ready
1. `IMP-0468` Libros PPT PDF en vivo: fair-share entre colas
1. `IMP-0469` Libros PPT PDF en vivo: MLFQ con promoción/democión
1. `IMP-0470` Libros PPT PDF en vivo: round-robin dentro de la cola
1. `IMP-0471` Libros PPT PDF en vivo: SJF aproximado por coste
1. `IMP-0472` Libros PPT PDF en vivo: deadline EDF si hay plazo
1. `IMP-0473` Libros PPT PDF en vivo: rate monotonic para periódicos
1. `IMP-0474` Libros PPT PDF en vivo: lottery ponderada por prioridad
1. `IMP-0475` Libros PPT PDF en vivo: robo de trabajo entre colas
1. `IMP-0476` Libros PPT PDF en vivo: migración parked→ready
1. `IMP-0477` Libros PPT PDF en vivo: park al StopToken
1. `IMP-0478` Libros PPT PDF en vivo: unpark idempotente
1. `IMP-0479` Libros PPT PDF en vivo: heartbeat por tick
1. `IMP-0480` Libros PPT PDF en vivo: watchdog de running colgado
1. `IMP-0481` Libros PPT PDF en vivo: cuenta de CPU acumulada
1. `IMP-0482` Libros PPT PDF en vivo: cuenta de espera acumulada
1. `IMP-0483` Libros PPT PDF en vivo: reintentos con backoff
1. `IMP-0484` Libros PPT PDF en vivo: señal de cancelación cooperativa
1. `IMP-0485` Libros PPT PDF en vivo: traza span por transición
1. `IMP-0486` Libros PPT PDF en vivo: métrica counter de admits
1. `IMP-0487` Libros PPT PDF en vivo: métrica gauge de ready
1. `IMP-0488` Libros PPT PDF en vivo: histograma de latencia de slice
1. `IMP-0489` Libros PPT PDF en vivo: SLO de reanudación <1s
1. `IMP-0490` Libros PPT PDF en vivo: presupuesto de error por cola
1. `IMP-0491` Libros PPT PDF en vivo: cuota de jobs concurrentes
1. `IMP-0492` Libros PPT PDF en vivo: slice de estudio en Q3
1. `IMP-0493` Libros PPT PDF en vivo: slice de estudio en Q2
1. `IMP-0494` Libros PPT PDF en vivo: pin de misión exclusiva Q1
1. `IMP-0495` Libros PPT PDF en vivo: chat nunca bloquea Q1
1. `IMP-0496` Libros PPT PDF en vivo: carga balanceada por kind
1. `IMP-0497` Libros PPT PDF en vivo: índice invertido pid/goal
1. `IMP-0498` Libros PPT PDF en vivo: snapshot JSON para /api/pcb
1. `IMP-0499` Libros PPT PDF en vivo: export del catálogo aplicado
1. `IMP-0500` Libros PPT PDF en vivo: marcador APPLIED de las 1000
## ui

1. `IMP-0501` Control plane: persistencia atómica con fsync
1. `IMP-0502` Control plane: journal append-only verificable
1. `IMP-0503` Control plane: checkpoint del program counter
1. `IMP-0504` Control plane: registros de contexto serializados
1. `IMP-0505` Control plane: prioridad con envejecimiento
1. `IMP-0506` Control plane: quantum cooperativo por cola
1. `IMP-0507` Control plane: preemption cooperativa al slice
1. `IMP-0508` Control plane: nice ajustable por trabajo
1. `IMP-0509` Control plane: afinidad de cola Q0-Q3
1. `IMP-0510` Control plane: herencia de prioridad del padre
1. `IMP-0511` Control plane: wait-channel nominado
1. `IMP-0512` Control plane: detección de espera circular
1. `IMP-0513` Control plane: reaper de procesos zombie
1. `IMP-0514` Control plane: reciclado seguro de pid
1. `IMP-0515` Control plane: huella del workspace al admitir
1. `IMP-0516` Control plane: deduplicación por hash de meta
1. `IMP-0517` Control plane: backpressure al saturar ready
1. `IMP-0518` Control plane: fair-share entre colas
1. `IMP-0519` Control plane: MLFQ con promoción/democión
1. `IMP-0520` Control plane: round-robin dentro de la cola
1. `IMP-0521` Control plane: SJF aproximado por coste
1. `IMP-0522` Control plane: deadline EDF si hay plazo
1. `IMP-0523` Control plane: rate monotonic para periódicos
1. `IMP-0524` Control plane: lottery ponderada por prioridad
1. `IMP-0525` Control plane: robo de trabajo entre colas
1. `IMP-0526` Control plane: migración parked→ready
1. `IMP-0527` Control plane: park al StopToken
1. `IMP-0528` Control plane: unpark idempotente
1. `IMP-0529` Control plane: heartbeat por tick
1. `IMP-0530` Control plane: watchdog de running colgado
1. `IMP-0531` Control plane: cuenta de CPU acumulada
1. `IMP-0532` Control plane: cuenta de espera acumulada
1. `IMP-0533` Control plane: reintentos con backoff
1. `IMP-0534` Control plane: señal de cancelación cooperativa
1. `IMP-0535` Control plane: traza span por transición
1. `IMP-0536` Control plane: métrica counter de admits
1. `IMP-0537` Control plane: métrica gauge de ready
1. `IMP-0538` Control plane: histograma de latencia de slice
1. `IMP-0539` Control plane: SLO de reanudación <1s
1. `IMP-0540` Control plane: presupuesto de error por cola
1. `IMP-0541` Control plane: cuota de jobs concurrentes
1. `IMP-0542` Control plane: slice de estudio en Q3
1. `IMP-0543` Control plane: slice de estudio en Q2
1. `IMP-0544` Control plane: pin de misión exclusiva Q1
1. `IMP-0545` Control plane: chat nunca bloquea Q1
1. `IMP-0546` Control plane: carga balanceada por kind
1. `IMP-0547` Control plane: índice invertido pid/goal
1. `IMP-0548` Control plane: snapshot JSON para /api/pcb
1. `IMP-0549` Control plane: export del catálogo aplicado
1. `IMP-0550` Control plane: marcador APPLIED de las 1000
## reliab

1. `IMP-0551` Watchdog y deadlock: persistencia atómica con fsync
1. `IMP-0552` Watchdog y deadlock: journal append-only verificable
1. `IMP-0553` Watchdog y deadlock: checkpoint del program counter
1. `IMP-0554` Watchdog y deadlock: registros de contexto serializados
1. `IMP-0555` Watchdog y deadlock: prioridad con envejecimiento
1. `IMP-0556` Watchdog y deadlock: quantum cooperativo por cola
1. `IMP-0557` Watchdog y deadlock: preemption cooperativa al slice
1. `IMP-0558` Watchdog y deadlock: nice ajustable por trabajo
1. `IMP-0559` Watchdog y deadlock: afinidad de cola Q0-Q3
1. `IMP-0560` Watchdog y deadlock: herencia de prioridad del padre
1. `IMP-0561` Watchdog y deadlock: wait-channel nominado
1. `IMP-0562` Watchdog y deadlock: detección de espera circular
1. `IMP-0563` Watchdog y deadlock: reaper de procesos zombie
1. `IMP-0564` Watchdog y deadlock: reciclado seguro de pid
1. `IMP-0565` Watchdog y deadlock: huella del workspace al admitir
1. `IMP-0566` Watchdog y deadlock: deduplicación por hash de meta
1. `IMP-0567` Watchdog y deadlock: backpressure al saturar ready
1. `IMP-0568` Watchdog y deadlock: fair-share entre colas
1. `IMP-0569` Watchdog y deadlock: MLFQ con promoción/democión
1. `IMP-0570` Watchdog y deadlock: round-robin dentro de la cola
1. `IMP-0571` Watchdog y deadlock: SJF aproximado por coste
1. `IMP-0572` Watchdog y deadlock: deadline EDF si hay plazo
1. `IMP-0573` Watchdog y deadlock: rate monotonic para periódicos
1. `IMP-0574` Watchdog y deadlock: lottery ponderada por prioridad
1. `IMP-0575` Watchdog y deadlock: robo de trabajo entre colas
1. `IMP-0576` Watchdog y deadlock: migración parked→ready
1. `IMP-0577` Watchdog y deadlock: park al StopToken
1. `IMP-0578` Watchdog y deadlock: unpark idempotente
1. `IMP-0579` Watchdog y deadlock: heartbeat por tick
1. `IMP-0580` Watchdog y deadlock: watchdog de running colgado
1. `IMP-0581` Watchdog y deadlock: cuenta de CPU acumulada
1. `IMP-0582` Watchdog y deadlock: cuenta de espera acumulada
1. `IMP-0583` Watchdog y deadlock: reintentos con backoff
1. `IMP-0584` Watchdog y deadlock: señal de cancelación cooperativa
1. `IMP-0585` Watchdog y deadlock: traza span por transición
1. `IMP-0586` Watchdog y deadlock: métrica counter de admits
1. `IMP-0587` Watchdog y deadlock: métrica gauge de ready
1. `IMP-0588` Watchdog y deadlock: histograma de latencia de slice
1. `IMP-0589` Watchdog y deadlock: SLO de reanudación <1s
1. `IMP-0590` Watchdog y deadlock: presupuesto de error por cola
1. `IMP-0591` Watchdog y deadlock: cuota de jobs concurrentes
1. `IMP-0592` Watchdog y deadlock: slice de estudio en Q3
1. `IMP-0593` Watchdog y deadlock: slice de estudio en Q2
1. `IMP-0594` Watchdog y deadlock: pin de misión exclusiva Q1
1. `IMP-0595` Watchdog y deadlock: chat nunca bloquea Q1
1. `IMP-0596` Watchdog y deadlock: carga balanceada por kind
1. `IMP-0597` Watchdog y deadlock: índice invertido pid/goal
1. `IMP-0598` Watchdog y deadlock: snapshot JSON para /api/pcb
1. `IMP-0599` Watchdog y deadlock: export del catálogo aplicado
1. `IMP-0600` Watchdog y deadlock: marcador APPLIED de las 1000
## perf

1. `IMP-0601` Rendimiento y backpressure: persistencia atómica con fsync
1. `IMP-0602` Rendimiento y backpressure: journal append-only verificable
1. `IMP-0603` Rendimiento y backpressure: checkpoint del program counter
1. `IMP-0604` Rendimiento y backpressure: registros de contexto serializados
1. `IMP-0605` Rendimiento y backpressure: prioridad con envejecimiento
1. `IMP-0606` Rendimiento y backpressure: quantum cooperativo por cola
1. `IMP-0607` Rendimiento y backpressure: preemption cooperativa al slice
1. `IMP-0608` Rendimiento y backpressure: nice ajustable por trabajo
1. `IMP-0609` Rendimiento y backpressure: afinidad de cola Q0-Q3
1. `IMP-0610` Rendimiento y backpressure: herencia de prioridad del padre
1. `IMP-0611` Rendimiento y backpressure: wait-channel nominado
1. `IMP-0612` Rendimiento y backpressure: detección de espera circular
1. `IMP-0613` Rendimiento y backpressure: reaper de procesos zombie
1. `IMP-0614` Rendimiento y backpressure: reciclado seguro de pid
1. `IMP-0615` Rendimiento y backpressure: huella del workspace al admitir
1. `IMP-0616` Rendimiento y backpressure: deduplicación por hash de meta
1. `IMP-0617` Rendimiento y backpressure: backpressure al saturar ready
1. `IMP-0618` Rendimiento y backpressure: fair-share entre colas
1. `IMP-0619` Rendimiento y backpressure: MLFQ con promoción/democión
1. `IMP-0620` Rendimiento y backpressure: round-robin dentro de la cola
1. `IMP-0621` Rendimiento y backpressure: SJF aproximado por coste
1. `IMP-0622` Rendimiento y backpressure: deadline EDF si hay plazo
1. `IMP-0623` Rendimiento y backpressure: rate monotonic para periódicos
1. `IMP-0624` Rendimiento y backpressure: lottery ponderada por prioridad
1. `IMP-0625` Rendimiento y backpressure: robo de trabajo entre colas
1. `IMP-0626` Rendimiento y backpressure: migración parked→ready
1. `IMP-0627` Rendimiento y backpressure: park al StopToken
1. `IMP-0628` Rendimiento y backpressure: unpark idempotente
1. `IMP-0629` Rendimiento y backpressure: heartbeat por tick
1. `IMP-0630` Rendimiento y backpressure: watchdog de running colgado
1. `IMP-0631` Rendimiento y backpressure: cuenta de CPU acumulada
1. `IMP-0632` Rendimiento y backpressure: cuenta de espera acumulada
1. `IMP-0633` Rendimiento y backpressure: reintentos con backoff
1. `IMP-0634` Rendimiento y backpressure: señal de cancelación cooperativa
1. `IMP-0635` Rendimiento y backpressure: traza span por transición
1. `IMP-0636` Rendimiento y backpressure: métrica counter de admits
1. `IMP-0637` Rendimiento y backpressure: métrica gauge de ready
1. `IMP-0638` Rendimiento y backpressure: histograma de latencia de slice
1. `IMP-0639` Rendimiento y backpressure: SLO de reanudación <1s
1. `IMP-0640` Rendimiento y backpressure: presupuesto de error por cola
1. `IMP-0641` Rendimiento y backpressure: cuota de jobs concurrentes
1. `IMP-0642` Rendimiento y backpressure: slice de estudio en Q3
1. `IMP-0643` Rendimiento y backpressure: slice de estudio en Q2
1. `IMP-0644` Rendimiento y backpressure: pin de misión exclusiva Q1
1. `IMP-0645` Rendimiento y backpressure: chat nunca bloquea Q1
1. `IMP-0646` Rendimiento y backpressure: carga balanceada por kind
1. `IMP-0647` Rendimiento y backpressure: índice invertido pid/goal
1. `IMP-0648` Rendimiento y backpressure: snapshot JSON para /api/pcb
1. `IMP-0649` Rendimiento y backpressure: export del catálogo aplicado
1. `IMP-0650` Rendimiento y backpressure: marcador APPLIED de las 1000
## i18n

1. `IMP-0651` Búsqueda multilingüe: persistencia atómica con fsync
1. `IMP-0652` Búsqueda multilingüe: journal append-only verificable
1. `IMP-0653` Búsqueda multilingüe: checkpoint del program counter
1. `IMP-0654` Búsqueda multilingüe: registros de contexto serializados
1. `IMP-0655` Búsqueda multilingüe: prioridad con envejecimiento
1. `IMP-0656` Búsqueda multilingüe: quantum cooperativo por cola
1. `IMP-0657` Búsqueda multilingüe: preemption cooperativa al slice
1. `IMP-0658` Búsqueda multilingüe: nice ajustable por trabajo
1. `IMP-0659` Búsqueda multilingüe: afinidad de cola Q0-Q3
1. `IMP-0660` Búsqueda multilingüe: herencia de prioridad del padre
1. `IMP-0661` Búsqueda multilingüe: wait-channel nominado
1. `IMP-0662` Búsqueda multilingüe: detección de espera circular
1. `IMP-0663` Búsqueda multilingüe: reaper de procesos zombie
1. `IMP-0664` Búsqueda multilingüe: reciclado seguro de pid
1. `IMP-0665` Búsqueda multilingüe: huella del workspace al admitir
1. `IMP-0666` Búsqueda multilingüe: deduplicación por hash de meta
1. `IMP-0667` Búsqueda multilingüe: backpressure al saturar ready
1. `IMP-0668` Búsqueda multilingüe: fair-share entre colas
1. `IMP-0669` Búsqueda multilingüe: MLFQ con promoción/democión
1. `IMP-0670` Búsqueda multilingüe: round-robin dentro de la cola
1. `IMP-0671` Búsqueda multilingüe: SJF aproximado por coste
1. `IMP-0672` Búsqueda multilingüe: deadline EDF si hay plazo
1. `IMP-0673` Búsqueda multilingüe: rate monotonic para periódicos
1. `IMP-0674` Búsqueda multilingüe: lottery ponderada por prioridad
1. `IMP-0675` Búsqueda multilingüe: robo de trabajo entre colas
1. `IMP-0676` Búsqueda multilingüe: migración parked→ready
1. `IMP-0677` Búsqueda multilingüe: park al StopToken
1. `IMP-0678` Búsqueda multilingüe: unpark idempotente
1. `IMP-0679` Búsqueda multilingüe: heartbeat por tick
1. `IMP-0680` Búsqueda multilingüe: watchdog de running colgado
1. `IMP-0681` Búsqueda multilingüe: cuenta de CPU acumulada
1. `IMP-0682` Búsqueda multilingüe: cuenta de espera acumulada
1. `IMP-0683` Búsqueda multilingüe: reintentos con backoff
1. `IMP-0684` Búsqueda multilingüe: señal de cancelación cooperativa
1. `IMP-0685` Búsqueda multilingüe: traza span por transición
1. `IMP-0686` Búsqueda multilingüe: métrica counter de admits
1. `IMP-0687` Búsqueda multilingüe: métrica gauge de ready
1. `IMP-0688` Búsqueda multilingüe: histograma de latencia de slice
1. `IMP-0689` Búsqueda multilingüe: SLO de reanudación <1s
1. `IMP-0690` Búsqueda multilingüe: presupuesto de error por cola
1. `IMP-0691` Búsqueda multilingüe: cuota de jobs concurrentes
1. `IMP-0692` Búsqueda multilingüe: slice de estudio en Q3
1. `IMP-0693` Búsqueda multilingüe: slice de estudio en Q2
1. `IMP-0694` Búsqueda multilingüe: pin de misión exclusiva Q1
1. `IMP-0695` Búsqueda multilingüe: chat nunca bloquea Q1
1. `IMP-0696` Búsqueda multilingüe: carga balanceada por kind
1. `IMP-0697` Búsqueda multilingüe: índice invertido pid/goal
1. `IMP-0698` Búsqueda multilingüe: snapshot JSON para /api/pcb
1. `IMP-0699` Búsqueda multilingüe: export del catálogo aplicado
1. `IMP-0700` Búsqueda multilingüe: marcador APPLIED de las 1000
## hw

1. `IMP-0701` Observación de hardware: persistencia atómica con fsync
1. `IMP-0702` Observación de hardware: journal append-only verificable
1. `IMP-0703` Observación de hardware: checkpoint del program counter
1. `IMP-0704` Observación de hardware: registros de contexto serializados
1. `IMP-0705` Observación de hardware: prioridad con envejecimiento
1. `IMP-0706` Observación de hardware: quantum cooperativo por cola
1. `IMP-0707` Observación de hardware: preemption cooperativa al slice
1. `IMP-0708` Observación de hardware: nice ajustable por trabajo
1. `IMP-0709` Observación de hardware: afinidad de cola Q0-Q3
1. `IMP-0710` Observación de hardware: herencia de prioridad del padre
1. `IMP-0711` Observación de hardware: wait-channel nominado
1. `IMP-0712` Observación de hardware: detección de espera circular
1. `IMP-0713` Observación de hardware: reaper de procesos zombie
1. `IMP-0714` Observación de hardware: reciclado seguro de pid
1. `IMP-0715` Observación de hardware: huella del workspace al admitir
1. `IMP-0716` Observación de hardware: deduplicación por hash de meta
1. `IMP-0717` Observación de hardware: backpressure al saturar ready
1. `IMP-0718` Observación de hardware: fair-share entre colas
1. `IMP-0719` Observación de hardware: MLFQ con promoción/democión
1. `IMP-0720` Observación de hardware: round-robin dentro de la cola
1. `IMP-0721` Observación de hardware: SJF aproximado por coste
1. `IMP-0722` Observación de hardware: deadline EDF si hay plazo
1. `IMP-0723` Observación de hardware: rate monotonic para periódicos
1. `IMP-0724` Observación de hardware: lottery ponderada por prioridad
1. `IMP-0725` Observación de hardware: robo de trabajo entre colas
1. `IMP-0726` Observación de hardware: migración parked→ready
1. `IMP-0727` Observación de hardware: park al StopToken
1. `IMP-0728` Observación de hardware: unpark idempotente
1. `IMP-0729` Observación de hardware: heartbeat por tick
1. `IMP-0730` Observación de hardware: watchdog de running colgado
1. `IMP-0731` Observación de hardware: cuenta de CPU acumulada
1. `IMP-0732` Observación de hardware: cuenta de espera acumulada
1. `IMP-0733` Observación de hardware: reintentos con backoff
1. `IMP-0734` Observación de hardware: señal de cancelación cooperativa
1. `IMP-0735` Observación de hardware: traza span por transición
1. `IMP-0736` Observación de hardware: métrica counter de admits
1. `IMP-0737` Observación de hardware: métrica gauge de ready
1. `IMP-0738` Observación de hardware: histograma de latencia de slice
1. `IMP-0739` Observación de hardware: SLO de reanudación <1s
1. `IMP-0740` Observación de hardware: presupuesto de error por cola
1. `IMP-0741` Observación de hardware: cuota de jobs concurrentes
1. `IMP-0742` Observación de hardware: slice de estudio en Q3
1. `IMP-0743` Observación de hardware: slice de estudio en Q2
1. `IMP-0744` Observación de hardware: pin de misión exclusiva Q1
1. `IMP-0745` Observación de hardware: chat nunca bloquea Q1
1. `IMP-0746` Observación de hardware: carga balanceada por kind
1. `IMP-0747` Observación de hardware: índice invertido pid/goal
1. `IMP-0748` Observación de hardware: snapshot JSON para /api/pcb
1. `IMP-0749` Observación de hardware: export del catálogo aplicado
1. `IMP-0750` Observación de hardware: marcador APPLIED de las 1000
## steward

1. `IMP-0751` Mayordomo de archivos: persistencia atómica con fsync
1. `IMP-0752` Mayordomo de archivos: journal append-only verificable
1. `IMP-0753` Mayordomo de archivos: checkpoint del program counter
1. `IMP-0754` Mayordomo de archivos: registros de contexto serializados
1. `IMP-0755` Mayordomo de archivos: prioridad con envejecimiento
1. `IMP-0756` Mayordomo de archivos: quantum cooperativo por cola
1. `IMP-0757` Mayordomo de archivos: preemption cooperativa al slice
1. `IMP-0758` Mayordomo de archivos: nice ajustable por trabajo
1. `IMP-0759` Mayordomo de archivos: afinidad de cola Q0-Q3
1. `IMP-0760` Mayordomo de archivos: herencia de prioridad del padre
1. `IMP-0761` Mayordomo de archivos: wait-channel nominado
1. `IMP-0762` Mayordomo de archivos: detección de espera circular
1. `IMP-0763` Mayordomo de archivos: reaper de procesos zombie
1. `IMP-0764` Mayordomo de archivos: reciclado seguro de pid
1. `IMP-0765` Mayordomo de archivos: huella del workspace al admitir
1. `IMP-0766` Mayordomo de archivos: deduplicación por hash de meta
1. `IMP-0767` Mayordomo de archivos: backpressure al saturar ready
1. `IMP-0768` Mayordomo de archivos: fair-share entre colas
1. `IMP-0769` Mayordomo de archivos: MLFQ con promoción/democión
1. `IMP-0770` Mayordomo de archivos: round-robin dentro de la cola
1. `IMP-0771` Mayordomo de archivos: SJF aproximado por coste
1. `IMP-0772` Mayordomo de archivos: deadline EDF si hay plazo
1. `IMP-0773` Mayordomo de archivos: rate monotonic para periódicos
1. `IMP-0774` Mayordomo de archivos: lottery ponderada por prioridad
1. `IMP-0775` Mayordomo de archivos: robo de trabajo entre colas
1. `IMP-0776` Mayordomo de archivos: migración parked→ready
1. `IMP-0777` Mayordomo de archivos: park al StopToken
1. `IMP-0778` Mayordomo de archivos: unpark idempotente
1. `IMP-0779` Mayordomo de archivos: heartbeat por tick
1. `IMP-0780` Mayordomo de archivos: watchdog de running colgado
1. `IMP-0781` Mayordomo de archivos: cuenta de CPU acumulada
1. `IMP-0782` Mayordomo de archivos: cuenta de espera acumulada
1. `IMP-0783` Mayordomo de archivos: reintentos con backoff
1. `IMP-0784` Mayordomo de archivos: señal de cancelación cooperativa
1. `IMP-0785` Mayordomo de archivos: traza span por transición
1. `IMP-0786` Mayordomo de archivos: métrica counter de admits
1. `IMP-0787` Mayordomo de archivos: métrica gauge de ready
1. `IMP-0788` Mayordomo de archivos: histograma de latencia de slice
1. `IMP-0789` Mayordomo de archivos: SLO de reanudación <1s
1. `IMP-0790` Mayordomo de archivos: presupuesto de error por cola
1. `IMP-0791` Mayordomo de archivos: cuota de jobs concurrentes
1. `IMP-0792` Mayordomo de archivos: slice de estudio en Q3
1. `IMP-0793` Mayordomo de archivos: slice de estudio en Q2
1. `IMP-0794` Mayordomo de archivos: pin de misión exclusiva Q1
1. `IMP-0795` Mayordomo de archivos: chat nunca bloquea Q1
1. `IMP-0796` Mayordomo de archivos: carga balanceada por kind
1. `IMP-0797` Mayordomo de archivos: índice invertido pid/goal
1. `IMP-0798` Mayordomo de archivos: snapshot JSON para /api/pcb
1. `IMP-0799` Mayordomo de archivos: export del catálogo aplicado
1. `IMP-0800` Mayordomo de archivos: marcador APPLIED de las 1000
## audit

1. `IMP-0801` Auditoría de colas: persistencia atómica con fsync
1. `IMP-0802` Auditoría de colas: journal append-only verificable
1. `IMP-0803` Auditoría de colas: checkpoint del program counter
1. `IMP-0804` Auditoría de colas: registros de contexto serializados
1. `IMP-0805` Auditoría de colas: prioridad con envejecimiento
1. `IMP-0806` Auditoría de colas: quantum cooperativo por cola
1. `IMP-0807` Auditoría de colas: preemption cooperativa al slice
1. `IMP-0808` Auditoría de colas: nice ajustable por trabajo
1. `IMP-0809` Auditoría de colas: afinidad de cola Q0-Q3
1. `IMP-0810` Auditoría de colas: herencia de prioridad del padre
1. `IMP-0811` Auditoría de colas: wait-channel nominado
1. `IMP-0812` Auditoría de colas: detección de espera circular
1. `IMP-0813` Auditoría de colas: reaper de procesos zombie
1. `IMP-0814` Auditoría de colas: reciclado seguro de pid
1. `IMP-0815` Auditoría de colas: huella del workspace al admitir
1. `IMP-0816` Auditoría de colas: deduplicación por hash de meta
1. `IMP-0817` Auditoría de colas: backpressure al saturar ready
1. `IMP-0818` Auditoría de colas: fair-share entre colas
1. `IMP-0819` Auditoría de colas: MLFQ con promoción/democión
1. `IMP-0820` Auditoría de colas: round-robin dentro de la cola
1. `IMP-0821` Auditoría de colas: SJF aproximado por coste
1. `IMP-0822` Auditoría de colas: deadline EDF si hay plazo
1. `IMP-0823` Auditoría de colas: rate monotonic para periódicos
1. `IMP-0824` Auditoría de colas: lottery ponderada por prioridad
1. `IMP-0825` Auditoría de colas: robo de trabajo entre colas
1. `IMP-0826` Auditoría de colas: migración parked→ready
1. `IMP-0827` Auditoría de colas: park al StopToken
1. `IMP-0828` Auditoría de colas: unpark idempotente
1. `IMP-0829` Auditoría de colas: heartbeat por tick
1. `IMP-0830` Auditoría de colas: watchdog de running colgado
1. `IMP-0831` Auditoría de colas: cuenta de CPU acumulada
1. `IMP-0832` Auditoría de colas: cuenta de espera acumulada
1. `IMP-0833` Auditoría de colas: reintentos con backoff
1. `IMP-0834` Auditoría de colas: señal de cancelación cooperativa
1. `IMP-0835` Auditoría de colas: traza span por transición
1. `IMP-0836` Auditoría de colas: métrica counter de admits
1. `IMP-0837` Auditoría de colas: métrica gauge de ready
1. `IMP-0838` Auditoría de colas: histograma de latencia de slice
1. `IMP-0839` Auditoría de colas: SLO de reanudación <1s
1. `IMP-0840` Auditoría de colas: presupuesto de error por cola
1. `IMP-0841` Auditoría de colas: cuota de jobs concurrentes
1. `IMP-0842` Auditoría de colas: slice de estudio en Q3
1. `IMP-0843` Auditoría de colas: slice de estudio en Q2
1. `IMP-0844` Auditoría de colas: pin de misión exclusiva Q1
1. `IMP-0845` Auditoría de colas: chat nunca bloquea Q1
1. `IMP-0846` Auditoría de colas: carga balanceada por kind
1. `IMP-0847` Auditoría de colas: índice invertido pid/goal
1. `IMP-0848` Auditoría de colas: snapshot JSON para /api/pcb
1. `IMP-0849` Auditoría de colas: export del catálogo aplicado
1. `IMP-0850` Auditoría de colas: marcador APPLIED de las 1000
## api

1. `IMP-0851` CLI y HTTP: persistencia atómica con fsync
1. `IMP-0852` CLI y HTTP: journal append-only verificable
1. `IMP-0853` CLI y HTTP: checkpoint del program counter
1. `IMP-0854` CLI y HTTP: registros de contexto serializados
1. `IMP-0855` CLI y HTTP: prioridad con envejecimiento
1. `IMP-0856` CLI y HTTP: quantum cooperativo por cola
1. `IMP-0857` CLI y HTTP: preemption cooperativa al slice
1. `IMP-0858` CLI y HTTP: nice ajustable por trabajo
1. `IMP-0859` CLI y HTTP: afinidad de cola Q0-Q3
1. `IMP-0860` CLI y HTTP: herencia de prioridad del padre
1. `IMP-0861` CLI y HTTP: wait-channel nominado
1. `IMP-0862` CLI y HTTP: detección de espera circular
1. `IMP-0863` CLI y HTTP: reaper de procesos zombie
1. `IMP-0864` CLI y HTTP: reciclado seguro de pid
1. `IMP-0865` CLI y HTTP: huella del workspace al admitir
1. `IMP-0866` CLI y HTTP: deduplicación por hash de meta
1. `IMP-0867` CLI y HTTP: backpressure al saturar ready
1. `IMP-0868` CLI y HTTP: fair-share entre colas
1. `IMP-0869` CLI y HTTP: MLFQ con promoción/democión
1. `IMP-0870` CLI y HTTP: round-robin dentro de la cola
1. `IMP-0871` CLI y HTTP: SJF aproximado por coste
1. `IMP-0872` CLI y HTTP: deadline EDF si hay plazo
1. `IMP-0873` CLI y HTTP: rate monotonic para periódicos
1. `IMP-0874` CLI y HTTP: lottery ponderada por prioridad
1. `IMP-0875` CLI y HTTP: robo de trabajo entre colas
1. `IMP-0876` CLI y HTTP: migración parked→ready
1. `IMP-0877` CLI y HTTP: park al StopToken
1. `IMP-0878` CLI y HTTP: unpark idempotente
1. `IMP-0879` CLI y HTTP: heartbeat por tick
1. `IMP-0880` CLI y HTTP: watchdog de running colgado
1. `IMP-0881` CLI y HTTP: cuenta de CPU acumulada
1. `IMP-0882` CLI y HTTP: cuenta de espera acumulada
1. `IMP-0883` CLI y HTTP: reintentos con backoff
1. `IMP-0884` CLI y HTTP: señal de cancelación cooperativa
1. `IMP-0885` CLI y HTTP: traza span por transición
1. `IMP-0886` CLI y HTTP: métrica counter de admits
1. `IMP-0887` CLI y HTTP: métrica gauge de ready
1. `IMP-0888` CLI y HTTP: histograma de latencia de slice
1. `IMP-0889` CLI y HTTP: SLO de reanudación <1s
1. `IMP-0890` CLI y HTTP: presupuesto de error por cola
1. `IMP-0891` CLI y HTTP: cuota de jobs concurrentes
1. `IMP-0892` CLI y HTTP: slice de estudio en Q3
1. `IMP-0893` CLI y HTTP: slice de estudio en Q2
1. `IMP-0894` CLI y HTTP: pin de misión exclusiva Q1
1. `IMP-0895` CLI y HTTP: chat nunca bloquea Q1
1. `IMP-0896` CLI y HTTP: carga balanceada por kind
1. `IMP-0897` CLI y HTTP: índice invertido pid/goal
1. `IMP-0898` CLI y HTTP: snapshot JSON para /api/pcb
1. `IMP-0899` CLI y HTTP: export del catálogo aplicado
1. `IMP-0900` CLI y HTTP: marcador APPLIED de las 1000
## horizon

1. `IMP-0901` Plazos y oportunidades: persistencia atómica con fsync
1. `IMP-0902` Plazos y oportunidades: journal append-only verificable
1. `IMP-0903` Plazos y oportunidades: checkpoint del program counter
1. `IMP-0904` Plazos y oportunidades: registros de contexto serializados
1. `IMP-0905` Plazos y oportunidades: prioridad con envejecimiento
1. `IMP-0906` Plazos y oportunidades: quantum cooperativo por cola
1. `IMP-0907` Plazos y oportunidades: preemption cooperativa al slice
1. `IMP-0908` Plazos y oportunidades: nice ajustable por trabajo
1. `IMP-0909` Plazos y oportunidades: afinidad de cola Q0-Q3
1. `IMP-0910` Plazos y oportunidades: herencia de prioridad del padre
1. `IMP-0911` Plazos y oportunidades: wait-channel nominado
1. `IMP-0912` Plazos y oportunidades: detección de espera circular
1. `IMP-0913` Plazos y oportunidades: reaper de procesos zombie
1. `IMP-0914` Plazos y oportunidades: reciclado seguro de pid
1. `IMP-0915` Plazos y oportunidades: huella del workspace al admitir
1. `IMP-0916` Plazos y oportunidades: deduplicación por hash de meta
1. `IMP-0917` Plazos y oportunidades: backpressure al saturar ready
1. `IMP-0918` Plazos y oportunidades: fair-share entre colas
1. `IMP-0919` Plazos y oportunidades: MLFQ con promoción/democión
1. `IMP-0920` Plazos y oportunidades: round-robin dentro de la cola
1. `IMP-0921` Plazos y oportunidades: SJF aproximado por coste
1. `IMP-0922` Plazos y oportunidades: deadline EDF si hay plazo
1. `IMP-0923` Plazos y oportunidades: rate monotonic para periódicos
1. `IMP-0924` Plazos y oportunidades: lottery ponderada por prioridad
1. `IMP-0925` Plazos y oportunidades: robo de trabajo entre colas
1. `IMP-0926` Plazos y oportunidades: migración parked→ready
1. `IMP-0927` Plazos y oportunidades: park al StopToken
1. `IMP-0928` Plazos y oportunidades: unpark idempotente
1. `IMP-0929` Plazos y oportunidades: heartbeat por tick
1. `IMP-0930` Plazos y oportunidades: watchdog de running colgado
1. `IMP-0931` Plazos y oportunidades: cuenta de CPU acumulada
1. `IMP-0932` Plazos y oportunidades: cuenta de espera acumulada
1. `IMP-0933` Plazos y oportunidades: reintentos con backoff
1. `IMP-0934` Plazos y oportunidades: señal de cancelación cooperativa
1. `IMP-0935` Plazos y oportunidades: traza span por transición
1. `IMP-0936` Plazos y oportunidades: métrica counter de admits
1. `IMP-0937` Plazos y oportunidades: métrica gauge de ready
1. `IMP-0938` Plazos y oportunidades: histograma de latencia de slice
1. `IMP-0939` Plazos y oportunidades: SLO de reanudación <1s
1. `IMP-0940` Plazos y oportunidades: presupuesto de error por cola
1. `IMP-0941` Plazos y oportunidades: cuota de jobs concurrentes
1. `IMP-0942` Plazos y oportunidades: slice de estudio en Q3
1. `IMP-0943` Plazos y oportunidades: slice de estudio en Q2
1. `IMP-0944` Plazos y oportunidades: pin de misión exclusiva Q1
1. `IMP-0945` Plazos y oportunidades: chat nunca bloquea Q1
1. `IMP-0946` Plazos y oportunidades: carga balanceada por kind
1. `IMP-0947` Plazos y oportunidades: índice invertido pid/goal
1. `IMP-0948` Plazos y oportunidades: snapshot JSON para /api/pcb
1. `IMP-0949` Plazos y oportunidades: export del catálogo aplicado
1. `IMP-0950` Plazos y oportunidades: marcador APPLIED de las 1000
## growth

1. `IMP-0951` Autoestudio: persistencia atómica con fsync
1. `IMP-0952` Autoestudio: journal append-only verificable
1. `IMP-0953` Autoestudio: checkpoint del program counter
1. `IMP-0954` Autoestudio: registros de contexto serializados
1. `IMP-0955` Autoestudio: prioridad con envejecimiento
1. `IMP-0956` Autoestudio: quantum cooperativo por cola
1. `IMP-0957` Autoestudio: preemption cooperativa al slice
1. `IMP-0958` Autoestudio: nice ajustable por trabajo
1. `IMP-0959` Autoestudio: afinidad de cola Q0-Q3
1. `IMP-0960` Autoestudio: herencia de prioridad del padre
1. `IMP-0961` Autoestudio: wait-channel nominado
1. `IMP-0962` Autoestudio: detección de espera circular
1. `IMP-0963` Autoestudio: reaper de procesos zombie
1. `IMP-0964` Autoestudio: reciclado seguro de pid
1. `IMP-0965` Autoestudio: huella del workspace al admitir
1. `IMP-0966` Autoestudio: deduplicación por hash de meta
1. `IMP-0967` Autoestudio: backpressure al saturar ready
1. `IMP-0968` Autoestudio: fair-share entre colas
1. `IMP-0969` Autoestudio: MLFQ con promoción/democión
1. `IMP-0970` Autoestudio: round-robin dentro de la cola
1. `IMP-0971` Autoestudio: SJF aproximado por coste
1. `IMP-0972` Autoestudio: deadline EDF si hay plazo
1. `IMP-0973` Autoestudio: rate monotonic para periódicos
1. `IMP-0974` Autoestudio: lottery ponderada por prioridad
1. `IMP-0975` Autoestudio: robo de trabajo entre colas
1. `IMP-0976` Autoestudio: migración parked→ready
1. `IMP-0977` Autoestudio: park al StopToken
1. `IMP-0978` Autoestudio: unpark idempotente
1. `IMP-0979` Autoestudio: heartbeat por tick
1. `IMP-0980` Autoestudio: watchdog de running colgado
1. `IMP-0981` Autoestudio: cuenta de CPU acumulada
1. `IMP-0982` Autoestudio: cuenta de espera acumulada
1. `IMP-0983` Autoestudio: reintentos con backoff
1. `IMP-0984` Autoestudio: señal de cancelación cooperativa
1. `IMP-0985` Autoestudio: traza span por transición
1. `IMP-0986` Autoestudio: métrica counter de admits
1. `IMP-0987` Autoestudio: métrica gauge de ready
1. `IMP-0988` Autoestudio: histograma de latencia de slice
1. `IMP-0989` Autoestudio: SLO de reanudación <1s
1. `IMP-0990` Autoestudio: presupuesto de error por cola
1. `IMP-0991` Autoestudio: cuota de jobs concurrentes
1. `IMP-0992` Autoestudio: slice de estudio en Q3
1. `IMP-0993` Autoestudio: slice de estudio en Q2
1. `IMP-0994` Autoestudio: pin de misión exclusiva Q1
1. `IMP-0995` Autoestudio: chat nunca bloquea Q1
1. `IMP-0996` Autoestudio: carga balanceada por kind
1. `IMP-0997` Autoestudio: índice invertido pid/goal
1. `IMP-0998` Autoestudio: snapshot JSON para /api/pcb
1. `IMP-0999` Autoestudio: export del catálogo aplicado
1. `IMP-1000` Autoestudio: marcador APPLIED de las 1000
