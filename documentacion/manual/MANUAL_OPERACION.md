<div align="center">

# ASTERIX RADAR DECODER

## Sistema de Decodificación ASTERIX y Presentación Radar PPI

---

# MANUAL DE OPERACIÓN

---

| | |
|---|---|
| **Código de documento** | ARD-MO-001 |
| **Tipo de documento** | Manual de Operación |
| **Edición** | 1.0 |
| **Estado** | Aprobado para uso |
| **Fecha** | 2026-07-05 |
| **Clasificación** | Uso Interno |
| **Ámbito** | Operación del sistema (rol Controlador y rol Técnico) |

</div>

<div style="page-break-after: always;"></div>

## Hoja de control del documento

### Registro de ediciones

| Edición | Fecha | Motivo del cambio | Autor |
|---------|-------|-------------------|-------|
| 1.0 | 2026-07-05 | Emisión inicial del manual de usuario operativo. | Equipo de Ingeniería |

### Documentos aplicables y de referencia

| Ref. | Documento |
|------|-----------|
| [DA-1] | EUROCONTROL — ASTERIX (All Purpose Structured Eurocontrol Surveillance Information Exchange), especificaciones CAT 001/002/010/020/021/034/048/062. |
| [DA-2] | EUROCONTROL — Operational Display System (ODS), simbología y paleta operativa. |
| [DR-1] | Guía de funcionamiento en línea (`Ayuda → Guía de la aplicación`). |
| [DR-2] | Documentación de certificación DO-278A / ED-109A del sistema (`documentacion/certificacion/`). |

### Convenciones tipográficas

- Las **acciones de menú** se indican como `Menú → Opción → Subopción`.
- Las **teclas** se indican entre corchetes, p. ej. `[Ctrl]+[F]`.
- Los roles se marcan con la etiqueta **(Controlador)** o **(Técnico)** cuando una función es exclusiva.
- Los acrónimos se desarrollan en el **Anexo A**.

<div style="page-break-after: always;"></div>

## Índice

1. [Introducción](#1-introducción)
2. [Descripción general del sistema](#2-descripción-general-del-sistema)
3. [Procedimientos de operación](#3-procedimientos-de-operación)
4. [Descripción de la interfaz de usuario](#4-descripción-de-la-interfaz-de-usuario)
5. [Operación con fuentes de datos](#5-operación-con-fuentes-de-datos)
6. [Navegación y presentación](#6-navegación-y-presentación)
7. [Filtrado de datos](#7-filtrado-de-datos)
8. [Cartografía, mapas y áreas](#8-cartografía-mapas-y-áreas)
9. [Redes de seguridad (Safety Nets)](#9-redes-de-seguridad-safety-nets)
10. [Simbología y etiquetas](#10-simbología-y-etiquetas)
11. [Funciones del rol técnico](#11-funciones-del-rol-técnico)
12. [Resolución de problemas](#12-resolución-de-problemas)
- [Anexo A. Acrónimos y abreviaturas](#anexo-a-acrónimos-y-abreviaturas)
- [Anexo B. Atajos de teclado](#anexo-b-atajos-de-teclado)
- [Anexo C. Referencia rápida de simbología](#anexo-c-referencia-rápida-de-simbología)

<div style="page-break-after: always;"></div>

## 1. Introducción

### 1.1 Objeto

El presente documento constituye el **Manual de Operación** del sistema **ASTERIX Radar Decoder**. Su objeto es establecer los **procedimientos de operación** del sistema y describir las funciones necesarias para su explotación en servicio, en sus dos roles de usuario: **Controlador** y **Técnico (ATSEP)**.

### 1.2 Alcance

El manual cubre la operación del sistema: acceso, interfaz de usuario, fuentes de datos, presentación radar, filtrado, cartografía, redes de seguridad y funciones técnicas de análisis. **No** incluye aspectos de instalación, arquitectura interna de software ni desarrollo, tratados en la documentación de ingeniería [DR-2].

### 1.3 Audiencia

- **Controlador de tránsito aéreo:** explotación operativa en vivo, presentación ODS y redes de seguridad.
- **Personal técnico ATSEP:** análisis de desempeño de la vigilancia, calibración, diagnóstico y explotación de capturas.

### 1.4 Visión general de las funciones

El sistema decodifica mensajes de vigilancia **ASTERIX** de EUROCONTROL, convierte las coordenadas polares del radar a coordenadas geográficas **WGS-84** y presenta los blancos sobre una pantalla panorámica **PPI**, con cartografía, redes de seguridad y fusión multi-radar.

<div style="page-break-after: always;"></div>

## 2. Descripción general del sistema

### 2.1 Visión general

ASTERIX Radar Decoder es un decodificador ASTERIX y display radar PPI en tiempo real para control de tránsito aéreo. Sus capacidades principales son:

- **Decodificación ASTERIX** de las categorías CAT 001/002/010/020/021/034/048/062 (radar primario, secundario, ADS-B, MLAT y system tracks).
- **Proyección geográfica** polar → WGS-84 y presentación sobre PPI.
- **Fusión multi-radar** (modo integrado): un único track por aeronave a partir de varios sensores.
- **Redes de seguridad** STCA, APW y MSAW evaluadas de forma continua.
- **Presentación EUROCONTROL ODS** para el puesto de control.
- **Herramientas técnicas** de análisis de desempeño de la vigilancia (PASS/SASS-C), calibración y diagnóstico.

### 2.2 Roles operativos

El sistema opera bajo dos roles, seleccionables en el perfil de usuario:

| Rol | Perfil de trabajo |
|-----|-------------------|
| **Controlador** | Operación en vivo (UDP), presentación ODS limpia, QNH editable, interfaz reducida. Sin acceso a playback, exportación ni herramientas técnicas. |
| **Técnico (ATSEP)** | Acceso completo: reproducción de capturas PCAP, Centro Técnico ATSEP, calibración/fusión, exportación de datos y panel lateral completo. |

> El rol se selecciona en `Configuración → Rol Operativo`. Al cambiar de rol, la interfaz aplica automáticamente los valores por defecto correspondientes.

### 2.3 Flujo operativo

```
   Fuente de datos                Procesamiento                 Presentación
 ┌────────────────┐        ┌───────────────────────┐        ┌──────────────┐
 │  PCAP (Técnico)│        │  Decodificación ASTERIX│        │   PPI (tracks│
 │       ó        │ ─────► │  Proyección → WGS-84   │ ─────► │   + mapas +  │
 │  UDP en vivo   │        │  Matching / Fusión     │        │  safety-nets)│
 │  (Consola)     │        │  STCA → APW → MSAW      │        │              │
 └────────────────┘        └───────────────────────┘        └──────────────┘
```

<div style="page-break-after: always;"></div>

## 3. Procedimientos de operación

Esta sección establece los procedimientos operativos del sistema. Los pasos se numeran para su ejecución secuencial.

### 3.1 Puesta en operación (arranque)

1. Inicie la aplicación. Se presenta la pantalla principal: barra superior (HUD), lienzo PPI y, según el rol, el panel lateral.
2. Verifique en el HUD el **operador**, el **rol activo** y el **aeropuerto (APT)** de referencia.
3. Confirme el **reloj UTC** y el **QNH** vigentes.

### 3.2 Selección de perfil y rol

1. Acceda a `Configuración → Perfil Operativo / Jurisdicción` y seleccione el aeropuerto/FIR de trabajo.
2. Acceda a `Configuración → Rol Operativo` y elija **Controlador** o **Técnico**.
3. El sistema aplica los defaults del rol (vista, fuentes de datos y controles disponibles).

El perfil determina el **aeropuerto de referencia**, el **radio de jurisdicción**, la **Altitud de Transición (TA)** y las redes de seguridad habilitadas.

### 3.3 Procedimiento de operación normal en vivo (Controlador)

1. Seleccione el rol **Controlador** y el perfil de la dependencia.
2. Establezca la conexión de datos en vivo: `Modo → Modo Consola`, e introduzca **IP** y **puerto** (por defecto `20000`).
3. Confirme la recepción: el contador **MSG** del HUD debe incrementarse y aparecer tráfico en el PPI.
4. Ajuste el **QNH** vigente en el HUD; verifique el **TL** derivado.
5. Verifique que las **redes de seguridad** (STCA/APW/MSAW) estén habilitadas según el perfil.
6. Opere la presentación (zoom, Finder, intensidad) según la sección 6.

### 3.4 Procedimiento de operación con capturas (Técnico)

1. Seleccione el rol **Técnico**.
2. Abra la captura: `Modo → Modo Playback` y seleccione el archivo `.pcap`.
3. Utilice los controles del reproductor (play/pausa, velocidad, seek, recorte de tramo).
4. Para análisis, importe los datos técnicos al **Centro Técnico ATSEP** (sección 11).

### 3.5 Procedimientos de contingencia

| Condición | Indicación | Acción del operador |
|-----------|-----------|---------------------|
| Cadena de alertas sin respuesta | Aviso «función de alerta degradada» (>5 s) | Considerar las redes de seguridad como **no fiables**; aplicar separación por procedimiento y notificar a mantenimiento. |
| Pérdida del feed en vivo | El contador MSG deja de incrementarse | Verificar la fuente/red UDP; conmutar a fuente alternativa si está disponible. |
| Sensor en OFFLINE | Monitor ATSEP marca OFFLINE *(Técnico)* | Notificar a mantenimiento; continuar con los sensores operativos. |
| Semáforo FDP en ámbar/apagado | Conexión al plan de vuelo perdida | Operar con datos de vigilancia; las etiquetas pueden carecer de callsign del plan. |

### 3.6 Cese de operación

1. Detenga la fuente de datos (desconectar UDP o detener el playback).
2. Exporte/archive los registros necesarios *(Técnico)* si la operación lo requiere.
3. Cierre la aplicación desde `Archivo → Salir`.

<div style="page-break-after: always;"></div>

## 4. Descripción de la interfaz de usuario

### 4.1 Barra superior (HUD)

Presenta la información de contexto operativo:

| Elemento | Descripción |
|----------|-------------|
| **OP / Rol** | Operador y rol activo (Controlador/Técnico). |
| **APT** | Aeropuerto de referencia del perfil. |
| **TWR/GND/APP** | Estado de las dependencias de control. |
| **QNH** | Reglaje altimétrico. **(Controlador)** editable; **(Técnico)** solo lectura. |
| **TL** | Nivel de Transición, derivado dinámicamente de la TA y el QNH. |
| **MSG** | Contador de mensajes ASTERIX recibidos/seleccionados. |
| **UTC** | Reloj de tiempo universal coordinado. |
| **Semáforo FDP** | Estado de la conexión al sistema de plan de vuelo (verde: conectado; ámbar: conectando/reconectando). |

### 4.2 Lienzo PPI

Es la pantalla panorámica central donde se presentan los tracks sobre la cartografía. Incluye:

- **Anillos de rango** sensor-céntricos (50/100/200 NM).
- **Barrido radar** (opcional, según toggle).
- **Botones de zoom + / −** flotantes en la esquina inferior derecha (ver sección 6.1).
- **Símbolos de track y etiquetas** con leader line arrastrable (ver sección 10).

### 4.3 Panel lateral (Controles y Filtros) — (Técnico)

Panel acoplable a la derecha, se muestra/oculta desde `Ver → Panel Lateral de Controles`. Contiene:

- **Carga rápida:** apertura de captura PCAP (Modo Playback) y botón *Centrar Mapa*.
- **Proyección:** sensor sobre el que se centra/proyecta la vista (autocentrado por defecto).
- **Históricos / Estela:** cantidad de posiciones previas a mostrar por track.
- **Toggles tácticos:** Barrido Radar, Cono de Silencio, Modo Integrado (MRT), Obstáculos MTR, Ver Plots Crudos y Ocultar Parrot (Sqwk 0000).
- **Filtros avanzados:** Filtro Datos, Filtro Etiquetas y Filtros de Calidad (DQF).

### 4.4 Menús

| Menú | Contenido principal |
|------|---------------------|
| **Archivo** | Log de Alertas STCA, Log de Eventos, Salir. |
| **Exportar** *(Técnico)* | Google Earth (KMZ), cobertura real (KMZ), heatmap QGIS (CSV), datos Power BI (Parquet). |
| **Ver** | Panel lateral, vector velocidad, reloj UTC flotante, panel de sensores, diagnóstico ATSEP, Analizador de Paquetes y Finder Táctico (`[Ctrl]+[F]`). |
| **Configuración** | Perfil Operativo, Cambiar Perfil, Rol Operativo, Centro Técnico ATSEP *(Técnico)*. |
| **Mapas** | Aerovías, procedimientos, fixes, VFR, sectores VFR y mapas personalizados. |
| **Áreas** | Espacios restringidos y capas de referencia. |
| **Modo** | Modo Playback, Modo Consola, Vista ODS, Intensidad Visual, Vista FIR. |
| **Ayuda** | Guía de funcionamiento en línea. |

<div style="page-break-after: always;"></div>

## 5. Operación con fuentes de datos

### 5.1 Reproducción de capturas — Modo Playback (Técnico)

Permite cargar y reproducir una captura `.pcap`:

1. Acceda a `Modo → Modo Playback` (o botón *Modo Playback* del panel lateral).
2. Seleccione el archivo `.pcap`.
3. Utilice los controles del reproductor: **play/pausa**, **stop**, **velocidad**, **búsqueda (seek)** y **recorte de tramo horario**.

> El Modo Playback está vedado al rol Controlador.

### 5.2 Datos en vivo — Modo Consola

Recepción de ASTERIX en tiempo real por **UDP**:

1. Acceda a `Modo → Modo Consola`.
2. Introduzca **IP** y **puerto** de escucha (por defecto `20000`).
3. El sistema recibe y presenta los reportes de los sensores en tiempo real.

> **Nota de capacidad:** la operación en vivo está verificada para carga multi-sensor a tiempo real. Bajo inyección sintética de un único flujo a tasas muy elevadas la presentación puede degradarse; consúltese la documentación de verificación [DR-2].

<div style="page-break-after: always;"></div>

## 6. Navegación y presentación

### 6.1 Zoom y paneo del PPI

El sistema ofrece tres formas de hacer zoom, todas con **anclado de foco** (el punto de referencia permanece fijo en pantalla al ampliar/reducir):

| Acción | Método | Ancla |
|--------|--------|-------|
| **Botones + / −** | Esquina inferior derecha del PPI | Track seleccionado, o centro de vista |
| **Teclado** | `[+]` / `[−]` (también `[=]` / `[_]`) | Track seleccionado, o centro de vista |
| **Rueda del ratón** | Girar arriba/abajo | Posición del cursor |

- Si hay un **track seleccionado** (resaltado en dorado), el zoom se ancla en él y lo mantiene fijo.
- Si no hay selección, se mantiene fijo el **centro de la vista**.
- El **paneo** se realiza arrastrando con el ratón o con las **flechas del teclado**.

> El anclado de foco evita que el elemento observado "se escape" del campo de visión al hacer zoom.

### 6.2 Finder Táctico

Ventana flotante para **localizar y centrar** un elemento. Se abre desde `Ver → Finder Táctico…` o con `[Ctrl]+[F]`. Discrimina automáticamente el tipo de entrada:

| Entrada | Busca | Ejemplo |
|---------|-------|---------|
| **Callsign** | Pista viva por identificación. | `ARG1340` |
| **Código SSR (Modo 3/A)** | Pista viva por squawk. | `4321` |
| **Aeropuerto / Waypoint** | Punto fijo de la base ATM. | `SACO`, `DILOM` |
| **Coordenadas** | Posición geográfica (decimal o DMS). | `-31.41,-64.18` |

Al encontrarlo, la vista se centra **sin perder las pistas vivas** y aparece un anillo de mira cian parpadeante; el resaltado se apaga solo a los 15 s.

### 6.3 Modos de presentación

| Modo | Uso |
|------|-----|
| **Vista ODS** | Simbología y paleta EUROCONTROL ODS (vista operativa del controlador): símbolos por estado de track, etiquetas FDB, barrido apagado. |
| **Intensidad Visual** | Sliders 0–100 % por capa (mapa, etiquetas, anillos, estela, símbolos, compás, herramientas). |
| **Vista FIR (satélite)** | Cartografía satelital de la FIR bajo los tracks, centrada en el aeropuerto del perfil. |

<div style="page-break-after: always;"></div>

## 7. Filtrado de datos

En el panel lateral, grupo **Filtros Avanzados**. El toggle *Ver Plots Crudos (Sin Filtros)* desactiva temporalmente todo el filtrado.

### 7.1 Filtro Datos

Decide **qué plots se procesan/muestran**:

- **Códigos (Squawk):** filtro de códigos Modo A/C, incluidos códigos especiales.
- **Rangos:** distancia, acimut, altura, cantidad de mensajes e ID de CAT 21 (límite inferior/superior).
- **Tipos de informe:** plots/pistas secundarios y primarios, servicio, meteos, ADS-B.
- **Sensores (SAC/SIC):** activación individual de cada sensor cargado.

Un contador indica «Seleccionados: N de M mensajes ASTERIX».

### 7.2 Filtro Etiquetas

Controla **qué campos aparecen en la etiqueta** del track y el criterio de selección (por Código A o por Posición). Campos: Código A, Nº de Mensaje, Código C, Dirección Aeronave, Nº de Respuestas, Velocidad, Hora UTC, Nº de Pista, Identificación, Altitud ADS-B, Categoría Emisor ADS-B, Velocidad Vertical ADS-B, RHO/THETA, Rumbo Verdadero (°V) y Magnético (°M).

### 7.3 Filtros de Calidad (DQF)

Activan/desactivan en tiempo real la marcación de datos degradados. El símbolo cambia de color al degradar:

| Filtro | Qué descarta | Color |
|--------|--------------|-------|
| **Garbling** | Solapamiento de respuestas SSR. | Magenta |
| **FRUIT / Ruido** | Ploteo huérfano aislado (interferencia). | Naranja |
| **Pistas Inmaduras** | Pistas con menos de ~2 vueltas de radar. | Dorado |

<div style="page-break-after: always;"></div>

## 8. Cartografía, mapas y áreas

### 8.1 Mapas (menú Mapas)

- **Aerovías:** superiores (nombre con `U`) e inferiores.
- **Procedimientos por aeropuerto:** SID / STAR / IAP.
- **Puntos y fixes:** VOR, NDB, DME, ruta y terminal.
- **VFR:** ATZs, corredores VFR, pistas y nombres.
- **Sectores de Vuelo VFR.**
- **Cargar mapa personalizado:** archivos GeoJSON (`LineString` y `Point`).

### 8.2 Áreas y referencias (menú Áreas)

- **Restringidas (R) / Prohibidas (P) / Peligrosas (D):** espacios aéreos, activables individualmente.
- **Sectores y zonas MSA:** altitud mínima de sector.
- **Corredores APM** y por waypoints: perfiles de aproximación.
- **Isógonas:** líneas de declinación magnética.

<div style="page-break-after: always;"></div>

## 9. Redes de seguridad (Safety Nets)

Las redes se evalúan de forma **continua (~1 Hz)** en la cadena **STCA → APW → MSAW** y resaltan la aeronave afectada en el PPI.

| Red | Detecta |
|-----|---------|
| **STCA** | Pérdida de separación entre dos aeronaves (conflicto de tránsito a corto plazo). |
| **APW** | Proximidad o penetración de un área (Area Proximity Warning). |
| **MSAW** | Descenso por debajo de la altitud mínima de seguridad del sector. |

### 9.1 Presentación de la alarma

El recuadro sobre el símbolo del track indica la severidad:

| Estado | Color | Comportamiento |
|--------|-------|----------------|
| **VIOLATION** | Rojo | Parpadea — alerta activa. |
| **PREDICTED** | Ámbar | Fijo — alerta predicha. |
| Normal | — | Sin recuadro. |

> Las redes se habilitan/inhiben desde el perfil (STCA y APW) y operan tanto en modo integrado como crudo, siempre que existan tracks vivos.

### 9.2 Supervisión de la cadena de alarmas

El sistema incorpora un **watchdog** de la cadena de safety-nets: si la cadena de procesamiento no produce salida durante más de 5 s, se notifica al operador que la función de alerta está **degradada**. Ante esta indicación, aplique los procedimientos de contingencia de la dependencia.

<div style="page-break-after: always;"></div>

## 10. Simbología y etiquetas

### 10.1 Etiqueta (Full Data Block, FDB)

Muestra identificación, nivel y código del track, con **leader line arrastrable**. A intensidad máxima de capa se presenta en negrita para mayor legibilidad.

### 10.2 Estado y calidad del track

- **Tráfico fuera de jurisdicción:** símbolo y etiqueta **atenuados** (fuera del radio operativo o por encima del techo FL del perfil).
- **Coasting:** track vivo sin actualización reciente; se diferencia visualmente.
- **Nivel A/F:** según la TA del perfil y el QNH, la altitud se muestra como `Axxx` (altitud, bajo la TA) o `Fxxx` (nivel de vuelo, sobre la TA).

### 10.3 Símbolo por origen del dato (ODS)

| Origen | Símbolo |
|--------|---------|
| Primario (PSR) | Cruz |
| Secundario / Mode-S (SSR) | Cuadrado |
| Combinado (PSR+SSR) | Cuadrado relleno |
| ADS-B (CAT 021) | Rombo |
| System Track (CAT 062) | Símbolo de track |
| Coasting | Cuadrado punteado |

<div style="page-break-after: always;"></div>

## 11. Funciones del rol técnico

Las funciones de esta sección son **exclusivas del rol Técnico (ATSEP)** y quedan vedadas al controlador.

### 11.1 Centro Técnico ATSEP

Se abre desde `Configuración → Centro Técnico ATSEP…`. Es el hub de herramientas técnicas, con las siguientes pestañas:

| Pestaña | Función |
|---------|---------|
| **Estadísticas** | Constructor de gráficos radar: cobertura PPI, cobertura geográfica, Pd vs azimut, rosa de azimut, cobertura vertical, histograma de rango; modos avanzados métrica×dimensión y dispersión X/Y. |
| **PASS / SASS-C** | Análisis de desempeño de la vigilancia estilo EUROCONTROL SASS-C: Pd global, Pd Modo A/C, sesgos y jitter de rango/acimut, split plots, RPM, y diagramas de cobertura polar/vertical. |
| **Monitor ATSEP** | Tablero de salud de cada sensor en tiempo real (CAT 034/023): ONLINE/OFFLINE, posición de antena, canal, alarmas, FRUIT. |
| **Inspector** | Desglose de bajo nivel de un registro ASTERIX (FSPEC, ítems y campos byte a byte). |
| **Cobertura** | Contorno real de cobertura por banda de FL (percentil de alcance por azimut). |
| **Calibración** | Registración multi-radar: estima y aplica correcciones de sesgo de distancia y acimut entre sensores. |

### 11.2 Exportación (menú Exportar)

Disponible una vez procesada una captura:

| Opción | Formato | Uso |
|--------|---------|-----|
| Trayectorias a Google Earth | KMZ | Trayectorias de los vuelos. |
| Reproducción de Vuelo Animado | KMZ | Animación temporal de un vuelo. |
| Mapa de Cobertura Real | KMZ | Envolvente de cobertura por banda de FL. |
| Heatmap a QGIS | CSV | Densidad/posiciones para SIG. |
| Datos a Power BI | Parquet | Dataset analítico columnar. |

<div style="page-break-after: always;"></div>

## 12. Resolución de problemas

| Síntoma | Causa probable | Acción |
|---------|----------------|--------|
| No se ve la barra lateral. | Rol Controlador (oculta por defecto). | `Ver → Panel Lateral de Controles`, o cambiar a rol Técnico. |
| No se puede modificar el QNH. | En rol Técnico es de solo lectura. | Editar el QNH solo desde el rol Controlador. |
| El menú Exportar está deshabilitado. | Función exclusiva del rol Técnico. | Cambiar a rol Técnico. |
| No se marca el avión en alarma. | Red inhibida o sin tracks vivos. | Verificar que la red esté habilitada en el perfil y que haya tráfico. |
| Aviso «función de alerta degradada». | La cadena de safety-nets no responde (>5 s). | Aplicar procedimientos de contingencia; ver sección 9.2. |
| El elemento buscado no aparece. | Fuera de cobertura o inexistente. | El Finder lo informa; verificar el criterio de búsqueda. |

<div style="page-break-after: always;"></div>

## Anexo A. Acrónimos y abreviaturas

| Sigla | Significado |
|-------|-------------|
| ADS-B | Automatic Dependent Surveillance – Broadcast |
| APM | Approach Path Monitoring |
| APP | Approach (control de aproximación) |
| APW | Area Proximity Warning |
| ASTERIX | All Purpose Structured Eurocontrol Surveillance Information Exchange |
| ATSEP | Air Traffic Safety Electronics Personnel |
| ATZ | Aerodrome Traffic Zone |
| CAT | Category (categoría de mensaje ASTERIX) |
| DQF | Data Quality Filter |
| FDB | Full Data Block |
| FIR | Flight Information Region |
| FL | Flight Level |
| FRUIT | False Replies Unsynchronized In Time |
| GND | Ground (control de superficie) |
| HMI | Human–Machine Interface |
| IAP | Instrument Approach Procedure |
| LDB | Limited Data Block |
| MLAT | Multilateration |
| MRT | Multi-Radar Tracking (modo integrado) |
| MSA | Minimum Sector Altitude |
| MSAW | Minimum Safe Altitude Warning |
| MTR | Capa de obstáculos/referencias en el PPI |
| ODS | Operational Display System |
| PASS | Performance Analysis Surveillance System |
| PCAP | Packet Capture |
| Pd | Probability of Detection |
| PPI | Plan Position Indicator |
| PSR | Primary Surveillance Radar |
| QNH | Reglaje altimétrico (elevación sobre el nivel del mar) |
| RNAV | Area Navigation |
| RPM | Revoluciones por minuto (rotación de antena) |
| SAC/SIC | System Area Code / System Identification Code |
| SASS-C | Surveillance Analysis Support System for ATC-Centre |
| SID | Standard Instrument Departure |
| SSR | Secondary Surveillance Radar |
| STAR | Standard Terminal Arrival Route |
| STCA | Short Term Conflict Alert |
| TA | Transition Altitude |
| TL | Transition Level |
| TMA | Terminal Control Area |
| ToD | Time of Day (marca temporal ASTERIX) |
| TWR | Tower (torre de control) |
| UDP | User Datagram Protocol |
| UTC | Coordinated Universal Time |
| VFR | Visual Flight Rules |
| WGS-84 | World Geodetic System 1984 |

<div style="page-break-after: always;"></div>

## Anexo B. Atajos de teclado

| Atajo | Acción |
|-------|--------|
| `[+]` / `[=]` | Acercar (zoom in), anclado al foco/centro. |
| `[−]` / `[_]` | Alejar (zoom out), anclado al foco/centro. |
| Rueda del ratón | Zoom anclado en el cursor. |
| `[←] [→] [↑] [↓]` | Desplazar la vista (paneo). |
| `[Ctrl]+[F]` | Abrir el Finder Táctico. |
| Arrastre del ratón | Paneo de la vista / arrastre de etiquetas. |

## Anexo C. Referencia rápida de simbología

| Elemento | Presentación |
|----------|--------------|
| Track en jurisdicción | Símbolo y etiqueta a brillo pleno. |
| Track fuera de jurisdicción | Símbolo y etiqueta atenuados. |
| Alarma VIOLATION | Recuadro rojo parpadeante. |
| Alarma PREDICTED | Recuadro ámbar fijo. |
| Track seleccionado | Recuadro fino de selección; se usa como ancla del zoom. |
| Coasting | Símbolo diferenciado (cuadrado punteado en ODS). |
| Dato degradado (DQF) | Color según filtro (magenta/naranja/dorado). |

---

<div align="center">

*ASTERIX Radar Decoder — Manual de Usuario · Edición 1.0 · Uso Interno*

</div>
