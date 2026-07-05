# Paquete de Certificación — Decodificador ASTERIX + Display PPI

**Sistema:** Decodificador ASTERIX (EUROCONTROL) y display radar PPI en tiempo real para ATC.
**Marco regulatorio:** RAAC Parte 211, PROGEN-ATM, OACI Doc 4444, EUROCAE ED-109A / RTCA DO-278A.
**Autoridad:** ANAC — Dirección de Control de Sistemas de Navegación Aérea.
**Estado del paquete:** BORRADOR INICIAL (v0.1) — base para análisis de viabilidad de certificación.
**Fecha:** 2026-06-28.

> ⚠️ **Aviso de honestidad técnica.** Este paquete documenta el *estado actual real* del proyecto frente
> a la normativa. La mayoría de los objetivos figuran como **POR DESARROLLAR**: el sistema es hoy un
> prototipo/herramienta funcional, no un producto con evidencia de aseguramiento de software demostrable.
> Estos documentos sirven para **medir la brecha y planificar**, no para afirmar conformidad.

---

## 1. Propósito de este paquete

Reunir los artefactos mínimos que la ANAC espera para *iniciar* la evaluación de un sistema de software
de tierra CNS/ATM, y exponer con claridad qué existe, qué falta y qué esfuerzo implica cerrar la brecha.

## 2. Documentos del paquete

| # | Documento | Rol normativo | Estado |
|---|-----------|---------------|--------|
| 01 | [PSAC](01_PSAC.md) — Plan for Software Aspects of Certification | Documento de entrada DO-278A | Borrador |
| 02 | [Clasificación SWAL](02_clasificacion_SWAL.md) | Asignación de nivel de aseguramiento (1–4) | Borrador (pendiente revisión post-FHA) |
| 03 | [Gap Analysis DO-278A](03_gap_analysis_DO-278A.md) | Estado objetivo-por-objetivo | Borrador |
| 04 | [Matriz de Trazabilidad](04_matriz_trazabilidad.md) | Requisitos ↔ diseño ↔ código ↔ test | Inicial/parcial |
| 05 | [Hoja de Ruta de Certificación](05_hoja_de_ruta.md) | Planificación de cierre de brecha | Borrador |
| 06 | [FHA — Functional Hazard Assessment](06_FHA.md) | Análisis de peligros; confirma SWAL; deriva SSR | Borrador v0.1 |
| 07 | [SRS — Software Requirements Specification](07_SRS.md) | 57 HLR formalizados (incl. HLR-STCA-06); 11 HLR-SSR del FHA; trazabilidad HLR↔test | Borrador v0.2 |
| 08 | [SDP — Software Development Plan](08_SDP.md) | Entorno, estándares de codificación, proceso de desarrollo, SOUP | Borrador v0.1 |
| 09 | [SVP — Software Verification Plan](09_SVP.md) | Métodos, niveles de prueba, cobertura, trazabilidad HLR↔test | Borrador v0.1 |
| 10 | [SCMP — Software Configuration Management Plan](10_SCMP.md) | Git como SCM, SCI, baseline, lockfile, archivo de resultados | Borrador v0.1 |
| 11 | [SQAP — Software Quality Assurance Plan](11_SQAP.md) | Auditorías, no conformidades, métricas, coordinación ANAC/SOI | Borrador v0.2 |
| 12 | [Registros de Revisión de Código](12_registros_revision_codigo.md) | Revisión por inspección de los 5 módulos SWAL 2 (RR-01..05) | Borrador v0.1 |
| 13 | [Estándar de Codificación y Diseño](13_estandar_codificacion.md) | Reglas EC/ED verificables + linter en CI (cierra D-4); base de la revisión de código | Borrador v0.2 |
| 14 | [Estándar de Requisitos](14_estandar_requisitos.md) | Reglas ER/RR/CJ/VF/LR + checklist QR (cierra P-5) | Borrador v0.1 |
| 15 | [SDD — Software Design Description](15_SDD.md) | Arquitectura (capas/flujo/secuencia/decisiones) + LLR de todas las capas — todo HLR con LLR (cierra D-2) | Borrador v0.3 |

## 3. Cómo leer el paquete

1. Empezar por la **clasificación SWAL (02)**: define el rigor exigible. Todo lo demás depende de ella.
2. El **PSAC (01)** declara el alcance, la organización y los planes de cómo se alcanzará ese rigor.
3. El **gap analysis (03)** es el termómetro: objetivos cumplidos / parciales / ausentes.
4. La **matriz (04)** es el primer eslabón de evidencia de verificación.
5. La **hoja de ruta (05)** ordena el trabajo restante por fases y esfuerzo.

## 4. Documentos normativos de referencia (a obtener)

- RTCA DO-278A / EUROCAE ED-109A — *Software Integrity Assurance Considerations for CNS/ATM Systems*.
- EUROCAE ED-153 — *Guidelines for ANS Software Safety Assurance* (complementario).
- RAAC Parte 211 — Gestión del Tránsito Aéreo (Argentina).
- PROGEN-ATM — Procedimientos Generales ATM.
- OACI Doc 4444 (PANS-ATM) — presentación de datos en HMI y separación.
- OACI Doc 9859 — *Safety Management Manual* (contexto de gestión de seguridad operacional).
- Specs ASTERIX EUROCONTROL por categoría (ya en [../](../) ).

## 5. Limitaciones declaradas del estado actual

- Sin plan de aseguramiento aprobado, sin baseline de configuración controlada.
- `requirements.txt` incompleto; sin lockfile de dependencias.
- Sin pipeline de Integración Continua ni cobertura de código medida.
- Sin SRS (Software Requirements Specification) formal ni análisis de seguridad (FHA/PSSA/SSA).
- Conviven scripts de prueba ad-hoc en la raíz con la suite estructurada `tests/`.
- El `.venv` versionado y artefactos binarios (`.pcap`, `.duckdb`) en el árbol de fuentes.
