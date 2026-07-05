# FHA — Functional Hazard Assessment

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma de referencia:** EUROCAE ED-78A / ED-109A / ED-153; OACI Doc 9859 SMM; RAAC Parte 211.
**Versión:** 0.1 (borrador). **Fecha:** 2026-07-01.
**Estado:** PROPUESTO — requiere revisión con EANA/explotador y validación por ANAC.

> El FHA identifica las condiciones de peligro creíbles derivadas de fallos del software, evalúa su
> severidad en el contexto operacional y asigna el SWAL que confirma o corrige la estimación provisional
> de [02_clasificacion_SWAL.md](02_clasificacion_SWAL.md). No substituye la PSSA ni la SSA.

---

## 1. Alcance y límites del análisis

### 1.1 Sistema bajo análisis

| Componente | Módulos | Rol operacional |
|------------|---------|-----------------|
| Decodificador ASTERIX | `decoder/`, `native_asterix.py` | Convierte tráfico UDP/PCAP en plots estructurados |
| Motor de proyección | `utils/geo.py` (`StereographicLocal`) | Transforma posiciones radar → WGS-84 / cartesianas |
| Matching y reconciliación | `player/radar_widget.py` (pasos A–E) | Asocia plots a tracks vivos |
| Ciclo de vida de tracks | `player/tracking/lifecycle.py` | Crea, actualiza y elimina tracks por ToD |
| Presentación PPI / ODS | `radar_widget.py`, `player/ods/` | Renderiza tracks y etiquetas al controlador |
| STCA | `analysis/stca_analyzer.py` | Alerta de conflicto a corto plazo |
| APW | `player/areas/` | Alerta de penetración de área |
| MSAW | `player/msaw/` | Alerta de altitud mínima de seguridad |
| Fusión multi-radar | `fusion/` | Correlación de sensores (solo rol técnico) |
| Auditoría safety | `storage/duckdb_repo.py`, `analysis/exporters.py` | Registro y exportación de eventos |

### 1.2 Interfaz del sistema

```
Sensores radar (UDP/PCAP) ──► DataEngine ──► radar_widget ──► HMI (pantalla PPI)
                                                  │
                                                  ▼
                                        cadena safety (STCA/APW/MSAW)
                                                  │
                                                  ▼
                                        alarmas visuales en HMI
```

### 1.3 Supuestos del análisis (condiciones de validez)

| ID | Supuesto | Efecto si no se cumple |
|----|----------|------------------------|
| H-AS-1 | Existe un controlador ATC humano en el lazo en todo momento | Reclasificar separación HMI a SWAL 2 o superior |
| H-AS-2 | La separación primaria se realiza por procedimientos PANS-ATM (Doc 4444), no exclusivamente por este sistema | Reclasificar el sistema como medio primario; escalar SWAL |
| H-AS-3 | Las aeronaves en el sector disponen de ACAS/TCAS como salvaguarda autónoma | Atenúa severidad de FC-STCA-01 |
| H-AS-4 | El sistema no emite resoluciones de conflicto automáticas ni controla actuadores | Si se añade automatización → FHA completa nueva |
| H-AS-5 | Las aeronaves IFR en aproximación y crucero cuentan con GPWS/EGPWS | Atenúa severidad de FC-MSAW-01 |
| H-AS-6 | La organización explotadora define procedimientos para pérdida o degradación del sistema | Atenúa severidad de FC-HMI-01 y FC-DEC-01 |

---

## 2. Escala de severidad

Basada en OACI Doc 9859 / EUROCAE ED-78A (adaptada a software de tierra CNS/ATM):

| Nivel | Denominación | Descripción | Prob. máxima admisible | SWAL típico |
|-------|-------------|-------------|------------------------|-------------|
| 1 | **Catastrófico** | Accidente con pérdida de vidas | < 10⁻⁹/h | SWAL 1 |
| 2 | **Peligroso** | Gran reducción de márgenes; lesiones graves | < 10⁻⁷/h | SWAL 2 |
| 3 | **Mayor** | Reducción significativa de márgenes; aumento de carga ATC | < 10⁻⁵/h | SWAL 3 |
| 4 | **Menor** | Molestia operacional; sin degradación de seguridad | < 10⁻³/h | SWAL 4 |
| 5 | **Sin efecto** | No afecta la seguridad | Sin requisito | Fuera de SWAL |

---

## 3. Tabla de condiciones de peligro (Failure Conditions — FC)

> **Convención de severidad en tabla:** se indica la severidad **sin mitigaciones externas** y con
> mitigaciones aplicables (H-AS-x). El SWAL se asigna sobre la severidad resultante **con mitigaciones**.

### 3.1 Decodificación ASTERIX

| FC | Condición de peligro | Fase operacional | Efecto sobre la operación | Sev. bruta | Mitigaciones externas | Sev. neta | SWAL |
|----|---------------------|-----------------|---------------------------|-----------|----------------------|-----------|------|
| FC-DEC-01 | **Pérdida total de decodificación** (ningún track en pantalla) | Continua | Controlador sin imagen de tráfico; posible pérdida de conciencia situacional | Peligroso | H-AS-2, H-AS-6 (proc. de fallo de sistema); otros sensores/sistemas de respaldo | Mayor | **3** |
| FC-DEC-02 | **Posición silenciosamente errónea** de uno o más tracks (error sistemático no advertido) | Continua | Controlador evalúa separación sobre dato falso; podría aprobar mantenimiento de distancia cuando en realidad no existe | Peligroso | H-AS-3 (TCAS autónomo); H-AS-2 (procedimientos); plausibilidad cruzada con datos de vuelo | **Peligroso** | **2** |
| FC-DEC-03 | **Identidad confundida** (callsign o squawk intercambiado entre dos aeronaves) | Continua | Controlador puede dirigir instrucción al avión equivocado | Peligroso | Readout de piloto; coordinación R/T; procedimientos de verificación | **Peligroso** | **2** |
| FC-DEC-04 | **Altitud/FL erróneo** de un track (sin aviso) | Continua | Separación vertical mal evaluada; alerta STCA/MSAW no generada sobre dato correcto | Peligroso | H-AS-3; altímetro de a bordo; otros canales de vigilancia (ADS-B) | **Peligroso** | **2** |
| FC-DEC-05 | **Track espúreo persistente** (aeronave ficticia generada por ruido/multipath y no filtrada) | Continua | Controlador evita zona/nivel inexistente; aumento de carga; posible maniobra innecesaria | Mayor | Procedimientos; experiencia del controlador | Mayor | **3** |

### 3.2 Proyección polar → WGS-84

| FC | Condición de peligro | Fase operacional | Efecto | Sev. bruta | Mitigaciones | Sev. neta | SWAL |
|----|---------------------|-----------------|--------|-----------|-------------|-----------|------|
| FC-GEO-01 | **Desplazamiento sistemático** de todos los tracks de un sensor (error de calibración o de constantes) | Continua | Separación lateral evaluada incorrectamente de forma consistente; errores acumulativos si no hay sensor de referencia | Peligroso | Cruce con otros sensores; cotejo con posiciones ADS-B; inspección visual de aeronaves conocidas | **Peligroso** | **2** |
| FC-GEO-02 | **Pérdida de proyección** (proyección no inicializada o excepción no manejada) → tracks en (0,0) | Arranque / cambio de configuración | Tracks visiblemente erróneos → el controlador detectará la anomalía; sistema inutilizable | Peligroso | Detección visual inmediata; procedimientos de fallo | Mayor | **3** |

### 3.3 Presentación PPI / ODS (HMI)

| FC | Condición de peligro | Fase operacional | Efecto | Sev. bruta | Mitigaciones | Sev. neta | SWAL |
|----|---------------------|-----------------|--------|-----------|-------------|-----------|------|
| FC-HMI-01 | **Track presente pero no renderizado** (omisión silenciosa de un símbolo) | Continua | Controlador no ve aeronave presente; brecha en conciencia situacional | Peligroso | H-AS-3; procedimientos de check de tráfico; ATC secundario | **Peligroso** | **2** |
| FC-HMI-02 | **Etiqueta engañosa** (callsign, FL, velocidad incorrectos mostrados para track correcto) | Continua | Instrucciones dirigidas a aeronave equivocada o a nivel equivocado | Peligroso | Readout R/T; cotejo con plan de vuelo | **Peligroso** | **2** |
| FC-HMI-03 | **Latencia de repintado > umbral operacional** sin aviso de degradación | Continua | Controlador opera con imagen desactualizada sin saberlo | Mayor | Procedimientos de comprobación de tiempo; formación | Mayor | **3** |
| FC-HMI-04 | **Alarma de safety-net no visible** (UI congelada o alarm silenciada sin aviso) | Continua | Alerta generada internamente pero no presentada al controlador | Peligroso | Prueba de alarma periódica; procedimientos | **Peligroso** | **2** |

### 3.4 Matching y reconciliación de tracks

| FC | Condición de peligro | Fase operacional | Efecto | Sev. bruta | Mitigaciones | Sev. neta | SWAL |
|----|---------------------|-----------------|--------|-----------|-------------|-----------|------|
| FC-TRK-01 | **Fusión errónea** de dos aeronaves distintas en un solo track | Continua | Una aeronave desaparece de pantalla; posición presentada es mezcla de dos aviones | Peligroso | TCAS; procedimientos; H-AS-2 | **Peligroso** | **2** |
| FC-TRK-02 | **Split** de un avión en dos tracks con identidades diferentes | Continua | Duplicación confusa; controlador puede dar instrucción a track incorrecto | Mayor | Experiencia del controlador; verificación R/T | Mayor | **3** |
| FC-TRK-03 | **Track caído prematuramente** (timeout erróneo con aeronave aún activa) | Continua | Equivalente a FC-HMI-01: avión desaparece de pantalla | Peligroso | H-AS-3; H-AS-2 | **Peligroso** | **2** |

### 3.5 Ciclo de vida de tracks

| FC | Condición de peligro | Fase operacional | Efecto | Sev. bruta | Mitigaciones | Sev. neta | SWAL |
|----|---------------------|-----------------|--------|-----------|-------------|-----------|------|
| FC-LIF-01 | **Track zombie** (persiste en pantalla después de que la aeronave salió del sector) | Salida/transferencia | Controlador intenta contactar o coordinar separación con aeronave ya fuera del sector | Mayor | Coordinación entre sectores; plan de vuelo | Mayor | **3** |
| FC-LIF-02 | **Caída prematura de track activo** por error en lógica de ToD | Continua | Ver FC-TRK-03; aeronave desaparece | Peligroso | H-AS-3; H-AS-2 | **Peligroso** | **2** |

### 3.6 STCA — Short Term Conflict Alert

| FC | Condición de peligro | Fase operacional | Efecto | Sev. bruta | Mitigaciones | Sev. neta | SWAL |
|----|---------------------|-----------------|--------|-----------|-------------|-----------|------|
| FC-STCA-01 | **Falso negativo**: conflicto real no alertado (función de red de respaldo fallada) | Continua | Controlador no recibe aviso de última barrera; depende de separación propia y TCAS de a bordo | Peligroso | H-AS-3 (TCAS); H-AS-2 (separación procedural es la primaria; STCA es *respaldo*) | **Mayor** | **3** |
| FC-STCA-02 | **Falso positivo**: alerta generada sin conflicto real | Continua | Distracción del controlador; maniobra innecesaria; efecto *alarm fatigue* si persistente | Mayor | Reconocimiento del controlador; criterios de aceptación de alerta | Menor | **4** |
| FC-STCA-03 | **STCA activo cuando debería estar inhibido** (o inhibido cuando debería estar activo) | Configuración | Desorientación sobre el estado de la herramienta | Mayor | Indicador de estado en HMI; check pre-operacional | Mayor | **3** |

### 3.7 APW — Area Proximity Warning

| FC | Condición de peligro | Fase operacional | Efecto | Sev. bruta | Mitigaciones | Sev. neta | SWAL |
|----|---------------------|-----------------|--------|-----------|-------------|-----------|------|
| FC-APW-01 | **Falso negativo**: penetración real de área restringida no alertada | Continua | Infracción de espacio aéreo; potencial incidente con operaciones militares o parapúblicas | Mayor | Coordinación ATC-civil/militar; procedimientos de notificación | Mayor | **3** |
| FC-APW-02 | **Falso positivo**: alerta de área sin penetración real | Continua | Distracción; maniobra evasiva innecesaria | Menor | Juicio del controlador | Menor | **4** |
| FC-APW-03 | **Geometría de área cargada incorrectamente** (coordenadas corruptas) | Configuración | APW referenciada a polígono equivocado → FC-APW-01 o FC-APW-02 sistemáticos | Mayor | Validación de datos en carga; auditoría pre-operacional | Mayor | **3** |

### 3.8 MSAW — Minimum Safe Altitude Warning

| FC | Condición de peligro | Fase operacional | Efecto | Sev. bruta | Mitigaciones | Sev. neta | SWAL |
|----|---------------------|-----------------|--------|-----------|-------------|-----------|------|
| FC-MSAW-01 | **Falso negativo**: aproximación al terreno real no alertada (CFIT potencial) | Aproximación / baja altitud | Aeronave aproxima terreno sin aviso ATC; última oportunidad de intervención perdida | Peligroso | H-AS-5 (GPWS/EGPWS autónomo); procedimientos de altitud mínima; visibilidad del tripulante | **Mayor** (con H-AS-5); Peligroso sin GPWS | **3** (con H-AS-5) |
| FC-MSAW-02 | **Falso positivo MSAW** | Continua | Distracción; maniobra innecesaria | Menor | Juicio del controlador | Menor | **4** |
| FC-MSAW-03 | **MSAW suprimido en aproximación cuando no corresponde** (lógica de supresión errónea) | Aproximación | Equivalente a FC-MSAW-01 en la fase más crítica | Peligroso | GPWS; procedimientos | Mayor | **3** |
| FC-MSAW-04 | **Altitudes MSAW de referencia (mínimas) incorrectas** (datos de terreno corruptos) | Continua | FC-MSAW-01 o FC-MSAW-02 sistemáticos | Peligroso | Validación de datos en carga; auditoría pre-operacional | Mayor | **3** |

### 3.9 Fusión multi-radar (solo rol técnico)

| FC | Condición de peligro | Fase operacional | Efecto | Sev. bruta | Mitigaciones | Sev. neta | SWAL |
|----|---------------------|-----------------|--------|-----------|-------------|-----------|------|
| FC-FUS-01 | **Correlación incorrecta**: dos aeronaves distintas fusionadas | Análisis offline | Si se aplica en tiempo real: equivalente a FC-TRK-01. Offline: informe erróneo. | Mayor (online) / Menor (offline) | Exclusivo de rol técnico; no operacional en tiempo real | Mayor | **3** |
| FC-FUS-02 | **Calibración errónea** → sesgo sistemático en posición de sensor | Mantenimiento | Todos los tracks del sensor afectado desplazados; puede no detectarse si se acepta ciegamente | Mayor | Validación cruzada; análisis de estadísticas post-calibración | Mayor | **3** |

### 3.10 Auditoría y persistencia safety

| FC | Condición de peligro | Fase operacional | Efecto | Sev. bruta | Mitigaciones | Sev. neta | SWAL |
|----|---------------------|-----------------|--------|-----------|-------------|-----------|------|
| FC-AUD-01 | **Pérdida de eventos safety** (fallo de escritura en BD asíncrona) | Continua | Informe de auditoría OACI incompleto; sin efecto en tiempo real | Menor | No afecta operación; detectable por inspección | Menor | **4** |
| FC-AUD-02 | **Exportación CSV con datos incorrectos** (duraciones o aeronaves equivocadas) | Post-operación | Informe enviado a autoridad con datos erróneos | Menor | Revisión humana del informe antes de envío | Menor | **4** |

---

## 4. Resumen de asignaciones SWAL

| SWAL | Funciones / FC | Fundamento |
|------|----------------|------------|
| **2** | Decodificación (FC-DEC-02/03/04), Proyección (FC-GEO-01), HMI (FC-HMI-01/02/04), Matching (FC-TRK-01/03), Ciclo de vida (FC-LIF-02) | Fallo silencioso que afecta directamente la imagen de tráfico usada para separación; efecto Peligroso incluso con mitigaciones |
| **3** | Pérdida total (FC-DEC-01), Track espúreo (FC-DEC-05), Proyección caída (FC-GEO-02), Latencia HMI (FC-HMI-03), Split (FC-TRK-02), Zombie (FC-LIF-01), STCA/APW/MSAW falso negativo, Fusión | Efecto Mayor con mitigaciones vigentes; detectables o con redundancia operacional |
| **4** | Falsos positivos (STCA/APW/MSAW), Auditoría | Molestia o sin efecto en seguridad tiempo real |

### Resultado vs. clasificación provisional

| Función | SWAL provisional (02) | SWAL FHA (este doc.) | Delta |
|---------|----------------------|---------------------|-------|
| Decodificación ASTERIX | 2 | 2 | = |
| Proyección polar→WGS-84 | 2 | 2 | = |
| Presentación PPI / ODS | 2 | 2 | = |
| Matching/reconciliación | — | **2** | ↑ (nuevo) |
| Ciclo de vida de tracks | 3 | **2** | ↑ (caída prematura) |
| STCA | 3 | 3 | = |
| APW | 3 | 3 | = |
| MSAW | 3 | 3 | = |
| Fusión multi-radar | 3 | 3 | = |
| Auditoría / exportación | 4 | 4 | = |

> **Cambio más relevante:** el matching/reconciliación (`radar_widget._process_plot_data`) y la caída
> prematura de tracks (`lifecycle.py`) escalan a **SWAL 2**, ya que un error silencioso en esas
> funciones es equivalente a no mostrar una aeronave (FC-HMI-01), que ya era SWAL 2.

---

## 5. Requisitos de seguridad derivados

Los siguientes requisitos de seguridad de software (SSR) se derivan directamente de este FHA. Deben
formalizarse en el SRS.

| SSR | FC que cierra | Texto del requisito | SWAL |
|-----|--------------|---------------------|------|
| SSR-01 | FC-DEC-02/03/04 | El sistema **no debe** presentar una posición, identidad o altitud de track que difiera del mensaje ASTERIX recibido en más del error de cuantificación definido por la especificación EUROCONTROL de la categoría correspondiente, sin generar un indicador de dato no válido. | 2 |
| SSR-02 | FC-DEC-02 | Cuando una posición decodificada esté fuera del área de cobertura configurada del sensor, el sistema **debe** marcar el plot como cuestionable y no presentarlo sin aviso visual diferenciado. | 2 |
| SSR-03 | FC-GEO-01 | El sistema **debe** detectar y notificar al operador cuando los parámetros de proyección (centro, elipsoide) no estén inicializados o presenten valores fuera de rango geográfico plausible. | 2 |
| SSR-04 | FC-HMI-01 / FC-TRK-03 / FC-LIF-02 | Un track con plots recientes (dentro del tiempo de vida configurado) **no debe** desaparecer de la presentación sin que el operador haya realizado una acción explícita o se haya superado el timeout configurado de forma trazable. | 2 |
| SSR-05 | FC-HMI-04 | La cadena de alarma visual de safety-nets (STCA/APW/MSAW) **debe** incluir un mecanismo de autodiagnóstico o *heartbeat* que detecte bloqueos en la UI y los comunique al operador. | 2 |
| SSR-06 | FC-TRK-01 | El módulo de matching **no debe** fusionar dos tracks con Mode S distintos y no nulos. | 2 |
| SSR-07 | FC-STCA-01 | Cuando la función STCA esté habilitada, **debe** generar una alerta para todo par de tracks cuya distancia horizontal proyectada descienda por debajo del umbral configurado dentro del tiempo de look-ahead, salvo que ambos tracks estén en la lista de inhibiciones explícitas. | 3 |
| SSR-08 | FC-MSAW-01 | Cuando la función MSAW esté habilitada, **debe** generar una alerta cuando la altitud de un track activo sea inferior a la altitud mínima de seguridad definida para su posición horizontal, salvo supresión activa por aproximación dentro de parámetros documentados. | 3 |
| SSR-09 | FC-APW-03 / FC-MSAW-04 | Los datos de geometría (áreas APW, altitudes MSAW) **deben** ser validados en carga contra un esquema de tipos y rangos, y rechazados con log de error si no son válidos. | 3 |
| SSR-10 | FC-STCA-03 | El estado habilitado/inhibido de cada función safety-net **debe** ser visible de forma inequívoca en la HMI en todo momento de la sesión. | 3 |
| SSR-11 | FC-AUD-01 | La cola de persistencia asíncrona de eventos safety **debe** garantizar que ningún evento encolado se pierda por cierre normal de la aplicación (flush en shutdown). | 4 |

---

## 6. Cobertura del FHA por los tests existentes

| FC | Test(s) que proveen evidencia | Cobertura | Brecha |
|----|------------------------------|-----------|--------|
| FC-DEC-02/03/04 | `tests/decoders/test_cat048_062.py` | Parsing unitario correcto | Sin test de propagación de error al display |
| FC-GEO-01 | `tests/geo/test_stereographic.py` | Roundtrip y signos | Sin test de detección de parámetros fuera de rango |
| FC-HMI-01/02 | `tests/tracking/test_hmi.py`, `test_plot_descarte.py` | ⚠️ Parcial: ningún track activo omitido (completitud), fidelidad de etiqueta (callsign/Mode3A/FL) y observabilidad de descartes (ROB-1) | Falta test de regresión **visual** del render (pixel/simbología ODS pintada) |
| FC-TRK-01/02/03 | `tests/tracking/test_matching.py` | Pasos A–E (31 casos) | Sin test de ML con Mode S ambiguo bajo carga |
| FC-LIF-02 | `tests/tracking/test_lifecycle.py` | Timeout por ToD | Parcial: sin test de excepción en parser de ToD |
| FC-STCA-01 | `tests/stca/test_stca_engine.py` + `test_stca_scenarios.py` | 27 unitarios (geometría CPA) + 7 escenarios end-to-end por el pipeline | Sin escenario con tráfico denso a partir de PCAP real (recomendado para SOI-3) |
| FC-APW-01 | `tests/areas/test_apw.py` | Penetración básica | Sin test de carga corrupta de geometría |
| FC-MSAW-01 | `tests/msaw/test_engine.py`, `test_suppression.py` | Lógica de alerta y supresión | Sin test con datos de terreno límite |
| FC-AUD-01 | `tests/storage_tests/test_safety_audit.py` | Flush + query | ✅ Cubierto |
| FC-FUS-01 | `tests/fusion_tests/test_correlator.py` | son_misma_aeronave | Parcial: sin test multisensor de extremo a extremo |

---

## 7. Acciones requeridas antes de SOI-1

| # | Acción | Responsable | Prioridad |
|---|--------|-------------|-----------|
| FHA-A1 | Validar supuestos H-AS-1 a H-AS-6 con EANA/explotador y documentar en acta | EANA + proyecto | Alta |
| FHA-A2 | Confirmar que GPWS/EGPWS está presente en aeronaves del sector afectado (valida SWAL 3 para MSAW) | EANA | Alta |
| FHA-A3 | Actualizar [02_clasificacion_SWAL.md](02_clasificacion_SWAL.md) con resultado del FHA (matching/lifecycle → SWAL 2) | Proyecto | Alta |
| FHA-A4 | ⚠️ En progreso — el [SRS](07_SRS.md) ya existe (56 HLR) y anota SSR-xx en los HLR; falta verificar que SSR-01 a SSR-11 estén completos y trazados en la [matriz](04_matriz_trazabilidad.md) | Proyecto | Alta |
| FHA-A5 | ⚠️ En progreso — FC-HMI-01/02/04 cubiertos a nivel widget (`test_hmi.py`, `test_track_state.py`, `test_plot_descarte.py`); falta test de regresión **visual** del render | Proyecto | Media |
| FHA-A6 | ⚠️ En progreso — PSSA/SSA redactada en [16_PSSA_SSA.md](16_PSSA_SSA.md) (estrategia de arquitectura, FC→SSR→diseño→SWAL, verificación de 11 SSR, argumento de seguridad); resta validar supuestos con EANA y cerrar SSA-A1..4 | Proyecto + EANA | Media |
| FHA-A7 | Revisar este documento con la autoridad en SOI-1 | ANAC + proyecto | Alta |

---

## 8. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-01 | Redacción inicial. 37 FC identificadas; 11 SSR derivados. Matching y lifecycle escalados a SWAL 2. |
