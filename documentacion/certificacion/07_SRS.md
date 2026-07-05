# SRS — Software Requirements Specification

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**Norma de referencia:** EUROCAE ED-109A / RTCA DO-278A; EUROCONTROL ASTERIX Specs Ed. 1.x por categoría.
**Versión:** 0.2 (borrador). **Fecha:** 2026-07-05.
**Estado:** PROPUESTO — requiere revisión técnica interna y aprobación de ANAC en SOI-2.

> Este SRS formaliza los **Requisitos de Alto Nivel (HLR)** del software. Los HLR se derivan de:  
> (a) los requisitos operacionales implícitos en PANS-ATM Doc 4444 y las specs ASTERIX,  
> (b) los requisitos de seguridad (SSR-01..11) del [FHA — 06_FHA.md](06_FHA.md),  
> (c) los requisitos derivados/informales (REQ-\*) preexistentes en la [04_matriz_trazabilidad.md](04_matriz_trazabilidad.md).  
> Los Requisitos de Bajo Nivel (LLR) se formalizarán en el SDD.

---

## 1. Documentos aplicables y referencias

| ID | Documento | Versión |
|----|-----------|---------|
| DA-1 | EUROCONTROL ASTERIX CAT 001 — Monoradar Target Reports | Ed. 1.1 |
| DA-2 | EUROCONTROL ASTERIX CAT 002 — Monoradar Service Messages | Ed. 1.0 |
| DA-3 | EUROCONTROL ASTERIX CAT 021 — ADS-B Messages | Ed. 2.4 / 0.26 |
| DA-4 | EUROCONTROL ASTERIX CAT 034 — Monoradar Service Messages | Ed. 1.27 |
| DA-5 | EUROCONTROL ASTERIX CAT 048 — Monoradar Target Reports | Ed. 1.15 |
| DA-6 | EUROCONTROL ASTERIX CAT 062 — SDPS Track Messages | Ed. 1.18 |
| DA-7 | OACI Doc 4444 — PANS-ATM (separación, HMI ATC) | Ed. 16 |
| DA-8 | EUROCONTROL ODS — Operational Display Specification | (ref. HMI) |
| DA-9 | EUROCAE ED-109A / RTCA DO-278A — Software Integrity Assurance | — |
| DA-10 | EUROCAE ED-153 — HMI for ATM Systems | — |
| DA-11 | OACI Doc 9859 — Safety Management Manual | Ed. 4 |
| DA-12 | PSAC — [01_PSAC.md](01_PSAC.md) | v0.1 |
| DA-13 | FHA — [06_FHA.md](06_FHA.md) | v0.1 |
| DA-14 | Clasificación SWAL — [02_clasificacion_SWAL.md](02_clasificacion_SWAL.md) | v0.2 |

---

## 2. Convenciones

- **DEBE / NO DEBE:** requisito obligatorio (shall / shall not).
- **DEBERÍA:** requisito recomendado; su omisión debe justificarse.
- **HLR-xxx-nn:** identificador único de requisito de alto nivel.
- **[SSR-nn]:** referencia al requisito de seguridad del FHA que este HLR satisface.
- **[REQ-xxx-n]:** referencia al requisito derivado informal que este HLR formaliza.
- **SWAL:** nivel de aseguramiento aplicable según DA-14.

---

## 3. Contexto del sistema

El sistema recibe tramas ASTERIX por UDP (modo vivo) o de archivo PCAP (modo reproducción), las decodifica, proyecta y presenta en un display PPI al controlador ATC. Una cadena de redes de seguridad (STCA/APW/MSAW) corre en segundo plano y genera alertas visuales. El sistema no emite comandos automáticos ni controla actuadores; el controlador humano es siempre responsable de la separación.

```
UDP/PCAP ──► DataEngine ──► radar_widget ──► PPI (HMI)
                                 │
                                 ▼
                        cadena safety (~1 Hz)
                                 │
                                 ▼
                        alertas visuales en HMI
```

---

## 4. Requisitos de decodificación ASTERIX (HLR-DEC)

> SWAL 2 para los HLR que afectan la corrección del dato presentado (HLR-DEC-01..06).  
> SWAL 3 para los HLR de robustez y registro.

### HLR-DEC-01 — Categorías soportadas `[REQ-DEC-1..4]` `SWAL 2`
El sistema **DEBE** decodificar mensajes ASTERIX de las categorías 001, 002, 021, 034, 048 y 062 de acuerdo a las especificaciones DA-1 a DA-6.

### HLR-DEC-02 — Fidelidad de la posición decodificada `[SSR-01]` `SWAL 2`
Para cada plot decodificado, la posición (rho/theta o WGS-84) presentada al módulo de proyección **NO DEBE** diferir del valor codificado en el mensaje ASTERIX en más del error de cuantificación definido por la especificación de la categoría correspondiente (e.g., 1/256 NM para rho en CAT048, 180/2²⁵ ° para lat/lon en CAT062).

### HLR-DEC-03 — Fidelidad de la identidad decodificada `[SSR-01]` `SWAL 2`
El callsign (ICAO 6-bit), el code Mode 3/A y el Mode S (24-bit) **DEBEN** reproducirse sin alteración desde el mensaje ASTERIX hasta el track visible en HMI. Cualquier transformación de codificación (p.ej. 6-bit → ASCII) **DEBE** ser conforme a la tabla OACI de caracteres ICAO.

### HLR-DEC-04 — Fidelidad del nivel de vuelo `[SSR-01]` `SWAL 2`
El Flight Level decodificado (FL en unidades de 0.25 FL para CAT048; ídem para CAT062) **DEBE** convertirse a FL entero con redondeo estándar y presentarse al HMI sin pérdida de signo (niveles negativos bajo el datum).

### HLR-DEC-05 — Registro de SAC/SIC de sensor `[REQ-DEC-5]` `SWAL 2`
El sistema **DEBE** identificar el sensor de origen de cada plot mediante el par SAC/SIC presente en el Data Source Identifier del mensaje ASTERIX, y asociarlo a los parámetros del sensor (coordenadas geográficas, nombre) cargados desde la configuración. `[REQ-DEC-5]`

### HLR-DEC-06 — Plot fuera de cobertura `[SSR-02]` `SWAL 2`
Cuando la posición polar de un plot (rho) exceda el rango máximo configurado para el sensor (`max_range_nm`), el sistema **DEBE** descartar el plot o marcarlo como cuestionable, y **NO DEBE** presentarlo al HMI como dato válido sin indicador diferenciado.

### HLR-DEC-07 — Robustez ante tramas malformadas `SWAL 3`
Ante un mensaje ASTERIX con longitud o estructura inconsistente (FSPEC truncado, longitud de data record incoherente), el sistema **DEBE** descartar el mensaje con registro de error y continuar procesando el siguiente mensaje sin excepción no manejada.

### HLR-DEC-08 — Soporte FDP/ADEXP `[REQ-FDP-1]` `SWAL 3`
El sistema **DEBE** recibir y parsear mensajes FDP en formato ADEXP, asociando datos de plan de vuelo (callsign, ruta, tipo de aeronave) al track radar correspondiente cuando el callsign coincide.

---

## 5. Requisitos de proyección geográfica (HLR-GEO)

> SWAL 2.

### HLR-GEO-01 — Proyección estereográfica local `[REQ-GEO-1]` `SWAL 2`
El sistema **DEBE** transformar posiciones polares (rho en NM, theta en grados desde el norte verdadero) a coordenadas cartesianas locales (metros) y a WGS-84 (lat/lon) mediante proyección estereográfica tangente al centro del radar, con error de posición < 10 m para distancias ≤ 200 NM del centro.

### HLR-GEO-02 — Roundtrip sin pérdida `SWAL 2`
La transformación inversa (cartesianas → WGS-84 → cartesianas) **DEBE** recuperar la posición original con error < 1 m a cualquier distancia dentro del rango de cobertura nominal (≤ 250 NM).

### HLR-GEO-03 — Detección de proyección no inicializada `[SSR-03]` `SWAL 2`
Cuando el centro del radar no haya sido configurado o los parámetros del elipsoide estén fuera de rango geográfico válido (lat ∈ [−90°, 90°]; lon ∈ [−180°, 180°]), el sistema **DEBE** reportar el error y **NO DEBE** presentar plots en el HMI usando valores por defecto silenciosos.

### HLR-GEO-04 — Declinación magnética `[REQ-GEO-2]` `SWAL 3`
El sistema **DEBE** calcular la declinación magnética para la posición del radar usando el modelo IGRF o equivalente offline, y aplicarla al track angle cuando el HMI lo requiera, sin acceso a red.

### HLR-GEO-05 — Multi-sensor: independencia de proyecciones `SWAL 2`
Cuando hay múltiples sensores activos, cada sensor **DEBE** tener su propia proyección estereográfica centrada en sus coordenadas. La fusión de posiciones en el espacio cartesiano compartido **DEBE** realizarse post-proyección.

---

## 6. Requisitos de ciclo de vida y matching de tracks (HLR-TRK)

> SWAL 2 (ver FHA §4).

### HLR-TRK-01 — Gobernado por ToD ASTERIX `[REQ-TRK-1]` `SWAL 2`
El ciclo de vida de tracks (creación, actualización, timeout) **DEBE** regirse exclusivamente por el Time of Day (ToD) contenido en los mensajes ASTERIX. El reloj del sistema operativo (`time.time()`) **NO DEBE** usarse en la lógica de ciclo de vida para garantizar reproducibilidad en playback.

### HLR-TRK-02 — Timeout de track configurable `[SSR-04]` `SWAL 2`
Un track **DEBE** eliminarse de la presentación únicamente cuando el intervalo entre el último plot recibido y el ToD del plot actual supere el tiempo de vida configurado (`track_timeout_s`). Mientras esté dentro del timeout, el track **DEBE** permanecer visible.

### HLR-TRK-03 — Paso A: fusión por Mode S `[REQ-TRK-2]` `[SSR-06]` `SWAL 2`
Dos plots con el mismo Mode S de 24 bits válido (no nulo, no en la lista de Mode S mock/filtrados) **DEBEN** asociarse al mismo track, independientemente del sensor de origen. Dos plots con Mode S distintos y ambos válidos **NO DEBEN** fusionarse en el mismo track.

### HLR-TRK-04 — Paso B: fusión por squawk con gate de distancia `[REQ-TRK-2]` `SWAL 2`
Dos plots de sensores distintos con el mismo código Mode 3/A no genérico (distinto de 1200, 2000, 7000, 0000 y sus equivalentes octal) **DEBEN** fusionarse si su distancia euclidiana en el espacio cartesiano compartido es ≤ 30 NM. Para squawks genéricos, el gate se reduce a 10 NM.

### HLR-TRK-05 — Paso E: gate de proximidad 3D `[REQ-TRK-2]` `SWAL 2`
En modo integrado multi-sensor, dos plots sin identidad común **DEBEN** fusionarse si su distancia horizontal es ≤ 1 NM sin nivel de vuelo conocido, o ≤ 3 NM con diferencia de FL ≤ 15 (equivalente a 1500 ft).

### HLR-TRK-06 — No fusión de aeronaves distintas `[SSR-06]` `SWAL 2`
El módulo de matching **NO DEBE** asignar el mismo track ID a dos plots que tengan Mode S distintos y ambos validados como no espúreos.

### HLR-TRK-07 — Track CAT062 por número de track `SWAL 2`
Los plots de categoría CAT062 **DEBEN** asociarse al track correspondiente mediante la clave `TRK_{track_number}_{sensor_id}` como paso primario. El squawk y la proximidad actúan como respaldo ante renumeración de tracks.

### HLR-TRK-08 — Aislamiento entre sensores en modo no integrado `SWAL 2`
Cuando el modo integrado multi-sensor está desactivado, los tracks de sensores distintos **NO DEBEN** fusionarse bajo ningún criterio de matching.

---

## 7. Requisitos de presentación HMI / PPI (HLR-HMI)

> SWAL 2 para corrección y completitud de la presentación; SWAL 3 para prestaciones secundarias.

### HLR-HMI-01 — Presentación completa de tracks activos `[SSR-04]` `SWAL 2`
Todo track cuyo estado sea activo (dentro del timeout, sin acción explícita de ocultación por el operador) **DEBE** ser renderizado en el PPI con un símbolo visible acorde a su estado ODS. La omisión silenciosa de un track activo en la pantalla está prohibida.

### HLR-HMI-02 — Fidelidad de la etiqueta de datos `[SSR-01]` `SWAL 2`
La etiqueta asociada a cada track **DEBE** mostrar el callsign, Mode 3/A y FL exactamente tal como fueron decodificados y asociados al track. La modificación de estos campos sin reflejo en la fuente de datos está prohibida.

### HLR-HMI-03 — Simbología EUROCONTROL ODS `[REQ-HMI-1]` `SWAL 2`
El sistema **DEBE** representar los tracks usando la simbología definida en DA-8 (ODS): formas de símbolo, colores y niveles de información por categoría de calidad de track (primario, secundario, SSR, ADS-B, fusionado).

### HLR-HMI-04 — Estado de track por calidad `[REQ-HMI-3]` `SWAL 2`
El símbolo de track **DEBE** reflejar la calidad del dato: track en coasting (último plot > 1× timeout/2), track en modo degradado (solo radar primario), track con Mode S, track ADS-B. La diferenciación visual **DEBE** ser conforme a DA-8.

### HLR-HMI-05 — Indicador de estado de safety-nets `[SSR-10]` `SWAL 2`
El estado habilitado/inhibido de cada función de red de seguridad (STCA, APW, MSAW) **DEBE** ser visible de forma inequívoca en la HMI en todo momento de la sesión operacional, sin requerir acción del operador para consultarlo.

### HLR-HMI-06 — Heartbeat de cadena de alarmas `[SSR-05]` `SWAL 2`
La cadena de procesamiento de safety-nets **DEBE** incluir un mecanismo de detección de bloqueo (watchdog o latido temporal). Si la cadena no produce salida en un intervalo > 5 s, el sistema **DEBE** notificar visualmente al operador que la función de alerta está degradada.

### HLR-HMI-07 — Declutter y niveles de información `[REQ-HMI-2]` `SWAL 3`
El operador **DEBE** poder seleccionar el nivel de información mostrado (mínimo: símbolo + Mode 3/A; completo: etiqueta con callsign, FL, velocidad, vector velocidad). El cambio de nivel **NO DEBE** provocar la desaparición de tracks activos.

### HLR-HMI-08 — Vista FIR satelital `[REQ-HMI-4]` `SWAL 4`
El sistema **DEBE** ofrecer una vista alternativa con cartografía satelital/vectorial del FIR, superponible con los tracks activos.

---

## 8. Requisitos STCA (HLR-STCA)

> SWAL 3. La función es red de respaldo, no medio primario de separación.

### HLR-STCA-01 — Detección de conflicto CPA `[REQ-SN-1]` `[SSR-07]` `SWAL 3`
Cuando STCA esté habilitada, el sistema **DEBE** calcular el Closest Point of Approach (CPA) para todos los pares de tracks activos con velocidad conocida y generar una alerta cuando la distancia horizontal proyectada en el CPA sea < `stca_horizontal_nm` (configurable, por defecto 3 NM) y el tiempo al CPA sea < `stca_lookahead_s` (por defecto 120 s).

### HLR-STCA-02 — Separación vertical en STCA `SWAL 3`
Cuando ambos tracks tengan FL conocido, el sistema **NO DEBE** generar alerta STCA si la diferencia de FL es ≥ `stca_vertical_fl` (configurable, por defecto 10 FL = 1000 ft).

### HLR-STCA-03 — Inhibición explícita de pares `SWAL 3`
El operador o la configuración **DEBE** poder definir pares de tracks inhibidos para STCA (p.ej. formaciones). Un par inhibido **NO DEBE** generar alerta.

### HLR-STCA-04 — Estado visible `[SSR-10]` `SWAL 3`
Ver HLR-HMI-05.

### HLR-STCA-05 — Ausencia de alerta fuera del umbral `SWAL 3`
El sistema **NO DEBE** generar alertas STCA para pares de tracks cuya distancia horizontal en CPA sea ≥ `stca_horizontal_nm` + margen de histéresis (`stca_hysteresis_nm`, por defecto 0.5 NM) para evitar alarm flicker.

### HLR-STCA-06 — Marco de posición único y consistente `[SSR-07]` `SWAL 3`
El origen de datos del motor STCA (el caller) **DEBE** suministrar a ambas fases —separación actual (VIOLATION) y predicción de CPA (PREDICTION)— la **misma posición de la aeronave expresada en marcos consistentes**: las coordenadas cartesianas `x/y` (metros) **DEBEN** ser la proyección local de las coordenadas `lat_render/lon_render` (grados) usadas por la fase de violación. El motor **NO DEBE** mezclar dos linajes de posición distintos (p. ej. posición cruda para la violación y posición suavizada para la predicción) sin garantizar esa consistencia. En todo caso, la fase de VIOLATION **DEBE** decidirse sobre la posición cruda reportada, de modo que un `x/y` inconsistente **NO PUEDA** ocultar una violación de separación real. *(Cierra el hallazgo de verificación STCA-1.)*

---

## 9. Requisitos APW (HLR-APW)

> SWAL 3.

### HLR-APW-01 — Detección de penetración de área `[REQ-SN-2]` `SWAL 3`
Cuando APW esté habilitada, el sistema **DEBE** generar una alerta cuando el punto medio de la posición proyectada de un track activo esté dentro de un polígono de área restringida (tipo R, P o D) cargado en la base de datos ATM.

### HLR-APW-02 — Validación de geometría en carga `[SSR-09]` `SWAL 3`
Las geometrías de áreas APW **DEBEN** ser validadas en el momento de carga: cada vértice **DEBE** tener lat ∈ [−90°, 90°] y lon ∈ [−180°, 180°]; el polígono **DEBE** tener al menos 3 vértices y ser cerrable. Geometrías inválidas **DEBEN** rechazarse con log de error y **NO DEBEN** cargarse parcialmente.

### HLR-APW-03 — Filtro de altitud APW `SWAL 3`
Cuando un área tenga límites verticales definidos (FL inferior / FL superior), el sistema **DEBE** generar la alerta APW solo cuando el FL del track esté dentro de esos límites. Sin FL conocido, la alerta **DEBE** generarse igualmente.

### HLR-APW-04 — Estado visible `[SSR-10]` `SWAL 3`
Ver HLR-HMI-05.

---

## 10. Requisitos MSAW (HLR-MSAW)

> SWAL 3. Depende de supuesto H-AS-5 (GPWS/EGPWS en aeronaves) del FHA.

### HLR-MSAW-01 — Detección de altitud mínima insegura `[REQ-SN-3]` `[SSR-08]` `SWAL 3`
Cuando MSAW esté habilitada, el sistema **DEBE** generar una alerta cuando la altitud de un track activo (FL × 100 ft o altitud geométrica si disponible) sea inferior al valor de altitud mínima de seguridad definido para la celda del terreno correspondiente a la posición horizontal del track.

### HLR-MSAW-02 — Validación de datos de terreno `[SSR-09]` `SWAL 3`
Los datos de altitud mínima MSAW **DEBEN** ser validados en carga: cada celda **DEBE** tener una altitud en pies dentro del rango [−2000, 60000]. Celdas con valores fuera de rango **DEBEN** rechazarse con log de error.

### HLR-MSAW-03 — Supresión en aproximación `[REQ-SN-4]` `SWAL 3`
El sistema **DEBE** suprimir la alerta MSAW para tracks en aproximación final (identificados por procedimiento configurable: área de supresión poligonal o track_angle convergente con pista) dentro de los parámetros de supresión documentados.

### HLR-MSAW-04 — Lógica de supresión auditable `SWAL 3`
Cuando la supresión MSAW esté activa para un track, el sistema **DEBE** registrar en log el motivo (área de supresión activa, track_id, ToD) para permitir auditoría post-operación.

### HLR-MSAW-05 — Estado visible `[SSR-10]` `SWAL 3`
Ver HLR-HMI-05.

---

## 11. Requisitos de fusión multi-radar (HLR-FUS)

> SWAL 3. Función exclusiva del rol técnico; no operacional en tiempo real.

### HLR-FUS-01 — Correlación por identidad `[REQ-FUS-1]` `SWAL 3`
El correlador **DEBE** usar Mode S como clave de identidad primaria (si presente y no vacío). El squawk no genérico actúa como clave secundaria. Dos tracks con Mode S distintos y ambos válidos **NO DEBEN** correlacionarse.

### HLR-FUS-02 — Gate de posición para correlación sin identidad `SWAL 3`
Sin identidad común, dos tracks **DEBEN** correlacionarse solo si su distancia euclidiana (con extrapolación temporal) es ≤ 0.7 NM (gate estricto) o ≤ 5 NM si existe una asociación aprendida previa.

### HLR-FUS-03 — Extrapolación temporal `[REQ-FUS-2]` `SWAL 3`
Para comparar posiciones de tracks con diferente ToD, el correlador **DEBE** extrapolar la posición del track más antiguo usando su velocidad (vx, vy en m/s) hasta el tiempo del track más reciente, con un límite máximo de extrapolación de 30 s.

### HLR-FUS-04 — Gate vertical para correlación `SWAL 3`
Cuando ambos tracks tengan FL conocido, el correlador **NO DEBE** correlacionarlos si la diferencia de FL es ≥ 15 (1500 ft).

---

## 12. Requisitos de auditoría y persistencia (HLR-AUD)

> SWAL 4.

### HLR-AUD-01 — Registro asíncrono de eventos safety `[REQ-AUD-1]` `[SSR-11]` `SWAL 4`
Cada evento de red de seguridad (ONSET / CLEAR de STCA, APW o MSAW) **DEBE** encolarse para persistencia en la base de datos analítica dentro del ciclo de procesamiento en que ocurre. El encolado **NO DEBE** bloquear el hilo principal de procesamiento.

### HLR-AUD-02 — Flush en cierre normal `[SSR-11]` `SWAL 4`
Al cierre normal de la aplicación, el sistema **DEBE** vaciar (`flush`) la cola de persistencia antes de terminar el proceso, garantizando que ningún evento encolado se pierda.

### HLR-AUD-03 — Exportación CSV de auditoría `[REQ-AUD-2]` `SWAL 4`
El sistema **DEBE** proveer una función de exportación de eventos safety a CSV con las columnas: `fecha_hora_utc`, `ts_epoch`, `subsistema`, `transicion`, `nivel`, `aeronave_1`, `aeronave_2`, `descripcion`, `duracion_s`, `sesion_id`. La duración **DEBE** calcularse pareando cada ONSET con su primer CLEAR de la misma clave.

### HLR-AUD-04 — Consulta con filtros `SWAL 4`
La API de consulta de eventos **DEBE** soportar filtros por subsistema, sesión, y rango de timestamp (ts_wall), y devolver los resultados ordenados por timestamp ascendente.

---

## 13. Requisitos de roles y perfiles (HLR-ROL)

> SWAL 3.

### HLR-ROL-01 — Roles operativos diferenciados `[REQ-ROL-1]` `SWAL 3`
El sistema **DEBE** soportar dos roles: `controlador` y `tecnico`. El rol activo **DEBE** determinarse en el inicio de sesión y permanecer constante durante la sesión.

### HLR-ROL-02 — Restricciones por rol `SWAL 3`
Las funciones de playback PCAP, calibración/fusión, exportación de análisis y acceso al Centro Técnico ATSEP **DEBEN** estar disponibles únicamente para el rol `tecnico`. El rol `controlador` **DEBE** operar solo en modo de recepción en vivo (UDP).

### HLR-ROL-03 — Persistencia de perfiles `SWAL 3`
Los perfiles de usuario (parámetros de vista, configuración de safety-nets, rol) **DEBEN** persistir entre sesiones en archivos JSON con validación de esquema en carga. Un perfil con datos inválidos **DEBE** rechazarse con mensaje de error, no cargarse parcialmente.

---

## 14. Requisitos de rendimiento (HLR-PERF)

> SWAL 3 para los que afectan la oportunidad de alarmas; SWAL 4 para los de eficiencia.

### HLR-PERF-01 — Latencia de procesamiento de plot `SWAL 3`
El tiempo entre la recepción de un datagram UDP y la actualización del track correspondiente en el modelo interno **DEBE** ser ≤ 200 ms en condiciones nominales (≤ 200 plots/s por sensor).

### HLR-PERF-02 — Cadencia de cadena safety `SWAL 3`
La cadena STCA/APW/MSAW **DEBE** ejecutarse con una cadencia ≥ 1 Hz (período ≤ 1 s) mientras haya tracks activos. La cadencia **DEBE** ser configurable entre 0.5 Hz y 2 Hz.

### HLR-PERF-03 — Capacidad de tracks simultáneos `SWAL 3`
El sistema **DEBE** soportar ≥ 500 tracks activos simultáneos sin degradar la cadencia de safety-nets (HLR-PERF-02) ni el repintado del PPI (HLR-PERF-04).

### HLR-PERF-04 — Repintado del PPI `SWAL 4`
La tasa de refresco del PPI **DEBE** ser ≥ 1 Hz con hasta 500 tracks activos en el área de cobertura. La tasa objetivo es ≥ 10 Hz (fluida para el operador).

### HLR-PERF-05 — Stress: 5000 PPS sin pérdida de datos `SWAL 3`
El sistema **DEBE** procesar ≥ 5000 plots por segundo (multi-sensor agregado) sin pérdida de mensajes en la cola de recepción UDP. Este requisito corresponde al límite del stress test con `baires.pcap`.

---

## 15. Requisitos de interfaz (HLR-INTF)

### HLR-INTF-01 — Entrada UDP ASTERIX `SWAL 2`
El sistema **DEBE** escuchar en uno o más puertos UDP configurables (por defecto 20000) para recibir tramas ASTERIX. Cada puerto **DEBE** corresponder a un único sensor (SAC/SIC). El cierre de un puerto **NO DEBE** afectar a los demás.

### HLR-INTF-02 — Entrada PCAP (modo técnico) `SWAL 3`
El sistema **DEBE** procesar archivos PCAP que contengan tramas UDP con datos ASTERIX, respetando los timestamps del archivo para el ciclo de vida de tracks (ToD de playback). Esta función es exclusiva del rol `tecnico`.

### HLR-INTF-03 — Base de datos ATM read-only `[REQ-ATM-1]` `SWAL 3`
El sistema **DEBE** consultar la base de datos ATM (DuckDB) en modo solo lectura para obtener parámetros de aeropuertos, aerovías, fixes, áreas restringidas y altitudes MSAW. La base de datos **NO DEBE** ser modificable desde la interfaz de usuario en ningún rol.

### HLR-INTF-04 — Configuración de sensores `[REQ-DEC-5]` `SWAL 2`
Los parámetros de cada sensor (SAC, SIC, lat, lon, nombre, rango máximo) **DEBEN** cargarse desde archivos JSON en el directorio de configuración al inicio. La ausencia de un archivo de sensor **DEBE** tratarse como sensor no configurado; el sistema **DEBE** continuar operando con los sensores que sí tengan configuración.

---

## 16. Requisitos de seguridad software derivados del FHA (HLR-SSR)

> Estos HLR formalizan directamente los SSR del FHA (DA-13). SWAL según DA-14.

| HLR | SSR origen | Enunciado formal | SWAL |
|-----|-----------|-----------------|------|
| HLR-SSR-01 | SSR-01 | Ídem HLR-DEC-02/03/04: posición, identidad y FL presentados sin alteración fuera del error de cuantificación. | 2 |
| HLR-SSR-02 | SSR-02 | Ídem HLR-DEC-06: plot fuera de cobertura marcado o descartado, nunca presentado como válido. | 2 |
| HLR-SSR-03 | SSR-03 | Ídem HLR-GEO-03: proyección no inicializada bloqueada con notificación al operador. | 2 |
| HLR-SSR-04 | SSR-04 | Ídem HLR-TRK-02 + HLR-HMI-01: track dentro de timeout nunca omitido de pantalla. | 2 |
| HLR-SSR-05 | SSR-05 | Ídem HLR-HMI-06: watchdog de cadena de alarmas con notificación al operador si > 5 s sin salida. | 2 |
| HLR-SSR-06 | SSR-06 | Ídem HLR-TRK-03 + HLR-TRK-06: Mode S distintos → nunca mismo track. | 2 |
| HLR-SSR-07 | SSR-07 | Ídem HLR-STCA-01: STCA genera alerta para todo par bajo umbral dentro del look-ahead. | 3 |
| HLR-SSR-08 | SSR-08 | Ídem HLR-MSAW-01: MSAW genera alerta cuando altitud < mínima de seguridad de la celda. | 3 |
| HLR-SSR-09 | SSR-09 | Ídem HLR-APW-02 + HLR-MSAW-02: geometrías y altitudes validadas en carga; inválidas rechazadas. | 3 |
| HLR-SSR-10 | SSR-10 | Ídem HLR-HMI-05: estado de cada safety-net siempre visible en HMI. | 3 |
| HLR-SSR-11 | SSR-11 | Ídem HLR-AUD-02: flush garantizado en cierre normal. | 4 |

---

## 17. Matriz de trazabilidad HLR → REQ / SSR

| HLR | Formaliza REQ | Satisface SSR | FC cubierto | Test |
|-----|--------------|--------------|-------------|------|
| HLR-DEC-01 | REQ-DEC-1..4 | — | FC-DEC-01 | `test_cat048_062.py`, `test_decoders_asterix.py` |
| HLR-DEC-02 | — | SSR-01 | FC-DEC-02 | `test_cat048_062.py` (parsing unitario) |
| HLR-DEC-03 | — | SSR-01 | FC-DEC-03 | `test_cat048_062.py` (callsign/squawk) |
| HLR-DEC-04 | — | SSR-01 | FC-DEC-04 | `test_cat048_062.py` (FL) |
| HLR-DEC-05 | REQ-DEC-5 | — | — | `test_sensor_registry.py` |
| HLR-DEC-06 | — | SSR-02 | FC-DEC-02 | ❌ pendiente |
| HLR-DEC-07 | — | — | FC-DEC-01 | Parcial (`test_cat048_062.py` robustez) |
| HLR-DEC-08 | REQ-FDP-1 | — | — | `tests/fdp/` |
| HLR-GEO-01 | REQ-GEO-1 | — | FC-GEO-01 | `test_stereographic.py` |
| HLR-GEO-02 | — | — | FC-GEO-01 | `test_stereographic.py` (roundtrip) |
| HLR-GEO-03 | — | SSR-03 | FC-GEO-02 | ❌ pendiente |
| HLR-GEO-04 | REQ-GEO-2 | — | — | `test_isogonic*.py` |
| HLR-GEO-05 | — | — | FC-GEO-01 | ❌ pendiente |
| HLR-TRK-01 | REQ-TRK-1 | — | FC-LIF-02 | `test_lifecycle.py` |
| HLR-TRK-02 | — | SSR-04 | FC-TRK-03/FC-LIF-02 | `test_lifecycle.py` (parcial) |
| HLR-TRK-03 | REQ-TRK-2 | SSR-06 | FC-TRK-01 | `test_matching.py` (paso A) |
| HLR-TRK-04 | REQ-TRK-2 | — | FC-TRK-02 | `test_matching.py` (paso B) |
| HLR-TRK-05 | REQ-TRK-2 | — | — | `test_matching.py` (paso E) |
| HLR-TRK-06 | — | SSR-06 | FC-TRK-01 | `test_matching.py` |
| HLR-TRK-07 | REQ-TRK-2 | — | — | `test_matching.py` (CAT62) |
| HLR-TRK-08 | — | — | — | ❌ pendiente |
| HLR-HMI-01 | REQ-HMI-1 | SSR-04 | FC-HMI-01 | ❌ sin test HMI |
| HLR-HMI-02 | — | SSR-01 | FC-HMI-02 | ❌ sin test HMI |
| HLR-HMI-03 | REQ-HMI-1 | — | — | `test_symbology.py` |
| HLR-HMI-04 | REQ-HMI-3 | — | — | `test_track_state.py` |
| HLR-HMI-05 | — | SSR-10 | FC-STCA-03 | ❌ pendiente |
| HLR-HMI-06 | — | SSR-05 | FC-HMI-04 | ❌ pendiente |
| HLR-HMI-07 | REQ-HMI-2 | — | — | `test_declutter.py` |
| HLR-HMI-08 | REQ-HMI-4 | — | — | `tests/firmap/` |
| HLR-STCA-01 | REQ-SN-1 | SSR-07 | FC-STCA-01 | `test_stca_engine.py` |
| HLR-STCA-02..05 | REQ-SN-1 | — | FC-STCA-02/03 | `test_stca_engine.py` (parcial) |
| HLR-STCA-06 | REQ-SN-1 | SSR-07 | FC-STCA-01 | `test_stca_engine.py::test_contrato_*` (marco único + residual acotado) |
| HLR-APW-01..04 | REQ-SN-2 | SSR-09 | FC-APW-01/03 | `test_apw.py` |
| HLR-MSAW-01..05 | REQ-SN-3/4 | SSR-08/09 | FC-MSAW-01..04 | `test_engine.py`, `test_suppression.py` |
| HLR-FUS-01..04 | REQ-FUS-1/2 | — | FC-FUS-01/02 | `test_correlator.py` |
| HLR-AUD-01..04 | REQ-AUD-1/2 | SSR-11 | FC-AUD-01/02 | `test_safety_audit.py` |
| HLR-ROL-01..03 | REQ-ROL-1 | — | — | `test_profile_manager.py` |
| HLR-PERF-01..05 | — | — | — | ❌ pendiente (stress test manual) |
| HLR-INTF-01..04 | REQ-DEC-5/ATM-1 | SSR-02/03 | FC-DEC-01/06 | Parcial |

---

## 18. Brechas de verificación críticas

| HLR sin test | Riesgo | Acción propuesta |
|-------------|--------|-----------------|
| HLR-DEC-06 | Plot fuera de rango presentado como válido | Test unitario: plot con rho > max_range → descartado |
| HLR-GEO-03 | Proyección sin inicializar usada silenciosamente | Test unitario: crear widget sin centro → assert error notificado |
| HLR-HMI-01/02/05/06 | Track omitido o etiqueta errónea sin detección | Test integración HMI offscreen; regresión visual |
| HLR-PERF-01..05 | Degradación en condiciones de carga | Benchmark automatizado con `baires.pcap` |
| HLR-TRK-08 | Cross-sensor merge en modo no-integrado | Test unitario: modo_integrado=False + 2 sensores |

---

## 19. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-01 | Primera edición. 56 HLR formalizados sobre 12 subsistemas. 11 HLR-SSR derivados del FHA. Matriz de trazabilidad HLR↔REQ↔SSR↔test. 5 brechas críticas identificadas. |
| 0.2 | 2026-07-05 | Añadido **HLR-STCA-06** (marco de posición único y consistente) que formaliza el contrato del motor STCA y **cierra el hallazgo STCA-1**; trazado a `test_stca_engine.py::test_contrato_*`. |
