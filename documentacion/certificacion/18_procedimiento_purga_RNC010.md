# Procedimiento de Purga de Binarios del Histórico — RNC-010

**Sistema:** Decodificador ASTERIX + Display PPI ATC.
**RNC:** [RNC-010](11_SQAP.md) (clase C) — integridad del árbol de fuentes (gap **C-3**).
**Versión:** 0.1. **Fecha:** 2026-07-05. **Estado:** PROCEDIMIENTO PROPUESTO — **NO EJECUTADO**.

> ⚠️ **Este procedimiento reescribe el histórico git (destructivo e irreversible sobre el remoto).**
> No debe ejecutarse sin: (a) decisión explícita del responsable del repositorio, (b) respaldo
> completo verificado, (c) coordinación con cualquier clon existente. Este documento deja el
> procedimiento **listo para ejecutar**, con el inventario real medido el 2026-07-05.

---

## 1. Estado medido (evidencia de la auditoría AUD-C-01)

- Tamaño de `.git`: **1.1 GB** (el árbol de trabajo fuente es una fracción de eso).
- El problema tiene **dos partes**, no una:

### 1.1 Binarios operativos AÚN TRACKEADOS en HEAD (además de en el histórico)

| Archivo | Tipo | Nota |
|---------|------|------|
| `baires.pcap` (27 MB) | Captura operativa | Usado por stress test local; checksum en `tests/data/checksums.txt` |
| `captura_260130.pcap` (51 MB) | Captura operativa | — |
| `Martescordoba_radar2.pcap` (38 MB) | Captura operativa | — |
| `MTR_2026_04_16…/17….pcap` (15/17 MB) | Capturas operativas | — |
| `260429.pcap`, `CBA_2026-05-04…pcap`, `UIS.pcap`, `cba_010626.pcap`, `fds260429.pcap` | Capturas operativas | — |

### 1.2 Blobs pesados SOLO en el histórico (ya no trackeados)

| Blob | Tamaño |
|------|--------|
| `20260601222026060123` (artefacto sin extensión) | 74.8 MB |
| `martescordoba_radar2.S4RD` / `mtr_…S4RD` | 26 / 14.5 MB |
| `node_modules/**` (esbuild.exe, lightningcss…) | ~19 MB |
| `radar_quality.log` (múltiples versiones) | ~13 MB |
| `20251111112025111112` | 13.6 MB |

### 1.3 Binarios que SÍ deben conservarse (vendorizados, parte del producto)

- `asterix_decoder-0.7.4/**/sample_data/*.pcap` — fixtures pequeños de la extensión C,
  usados por `tests/integration/test_pcap_e2e.py`. **No purgar.**
- `data/atm/atm.duckdb` — base ATM operativa (semilla SQL versionada aparte). **No purgar.**

---

## 2. Fase A — Destrackear de HEAD (NO destructiva, commit normal) — ✅ EJECUTADA 2026-07-05

Quita las capturas operativas del índice sin borrarlas del disco. Reversible; no reescribe historia.

> **Ejecutada el 2026-07-05:** se destrackearon 10 `.pcap` + 3 `.S4RD` de la raíz (`git rm --cached`);
> los archivos locales quedaron intactos y `baires.pcap` sigue disponible para el stress test. Los
> fixtures vendorizados (`asterix_decoder-0.7.4/**`) se conservan, con excepción explícita en
> `.gitignore`. Los clones nuevos ya no descargan ~250 MB de capturas en el checkout de HEAD.
> **La Fase B (purga del histórico) sigue pendiente de decisión.**

```bash
git rm --cached baires.pcap captura_260130.pcap Martescordoba_radar2.pcap \
    MTR_2026_04_16_16-28-16.pcap MTR_2026_04_17_17-28-16.pcap \
    260429.pcap CBA_2026-05-04_00-16-12.pcap UIS.pcap cba_010626.pcap fds260429.pcap

# Asegurar exclusión futura (verificar que .gitignore ya cubre *.pcap en raíz):
#   /*.pcap            ← capturas en la raíz
#   !asterix_decoder-0.7.4/**/*.pcap   ← fixtures vendorizados exceptuados

git commit -m "chore(scm): destrackea capturas operativas del árbol (RNC-010 fase A)"
```

**Efecto:** los clones nuevos ya no descargan ~200 MB de capturas; `baires.pcap` sigue disponible
localmente para el stress test (integridad por checksum, SCMP).

## 3. Fase B — Purga del histórico (DESTRUCTIVA — requiere OK explícito)

### 3.1 Precondiciones (checklist de ejecución)

- [ ] Respaldo completo: `git clone --mirror <repo> respaldo-pre-purga.git` + copia del árbol.
- [ ] Verificar el respaldo (clonar de él y correr `pytest tests/`).
- [ ] Congelar el trabajo: no hay ramas sin mergear ni PRs abiertos que importen.
- [ ] Confirmar que ningún otro clon activo necesita el histórico viejo (equipo unipersonal → bajo riesgo).
- [ ] `pip install git-filter-repo` (herramienta recomendada por git sobre filter-branch).

### 3.2 Ejecución

```bash
# Sobre un clon FRESCO en espejo (nunca sobre el working repo):
git clone --mirror https://github.com/jmatiasbro/decoderAsterix.git purga.git
cd purga.git

git filter-repo \
  --path baires.pcap --path captura_260130.pcap --path Martescordoba_radar2.pcap \
  --path MTR_2026_04_16_16-28-16.pcap --path MTR_2026_04_17_17-28-16.pcap \
  --path 260429.pcap --path CBA_2026-05-04_00-16-12.pcap --path UIS.pcap \
  --path cba_010626.pcap --path fds260429.pcap \
  --path martescordoba_radar2.S4RD --path mtr_2026_04_17_17-28-16.S4RD \
  --path 20260601222026060123 --path 20251111112025111112 \
  --path radar_quality.log \
  --path node_modules --path .venv \
  --path pass_analytics.duckdb --path-glob '*_fallback_*.duckdb' --path-glob 'test_*.duckdb' \
  --invert-paths

# Publicar el histórico reescrito (fuerza TODAS las refs):
git push --force --all
git push --force --tags
```

> `--invert-paths` = "eliminar estos paths, conservar el resto". Los fixtures de
> `asterix_decoder-0.7.4/**` y `data/atm/atm.duckdb` NO están listados → se conservan.

### 3.3 Post-ejecución

- [ ] Re-clonar el repo limpio y verificar: `du -sh .git` (esperado ≪ 1.1 GB), `pytest tests/` verde.
- [ ] Los **tags de baseline** (`v0.1.0-soi1`…`v0.4.0`) cambian de hash: registrar la tabla de
  equivalencia hash-viejo → hash-nuevo en el SCMP (trazabilidad de baselines, C-1).
- [ ] Todos los clones existentes deben **re-clonarse** (no `git pull` — divergencia total).
- [ ] Cerrar RNC-010 en [SQAP §5.3](11_SQAP.md) con referencia a este procedimiento y al push.

## 4. Riesgos y mitigación

| Riesgo | Mitigación |
|--------|------------|
| Pérdida de evidencia de baseline (hashes cambian) | Tabla de equivalencia de tags + respaldo espejo conservado como evidencia histórica |
| Clon desactualizado hace push del histórico viejo | Coordinar re-clonado; proteger la rama en GitHub tras la purga |
| Purga accidental de un fixture necesario | La lista §3.2 es explícita (no usa globs anchos para pcap); `pytest tests/` como verificación |
| CI referencia un blob purgado | El CI descarga por checkout del HEAD nuevo; no depende del histórico |

## 5. Registro de cambios

| Ver | Fecha | Cambio |
|-----|-------|--------|
| 0.1 | 2026-07-05 | Procedimiento inicial con inventario real medido (HEAD + histórico, 1.1 GB). Fases A (destrackeo, no destructiva) y B (filter-repo, destructiva). **No ejecutado.** |
