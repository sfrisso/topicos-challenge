# Preparación del agente

Registro de cómo se preparó y utilizó el agente de programación para esta
entrega. Todo lo afirmado aquí enlaza con un archivo, un commit o una salida de
comando versionada en el repositorio.

---

## 1. Entorno, versión e identificador del modelo

| Dato | Valor | Cómo se obtuvo |
| ---- | ----- | -------------- |
| Harness (entorno) | **OpenCode v2.1.4**, CLI en Linux | `opencode --version` → `opencode v2.1.4` |
| Modelo | `mimo-v2.6-flash-free`, proveedor `opencode` | Identificador visible en la configuración de la sesión |
| Rol del modelo | **Agente único** que lee, escribe y edita archivos, ejecuta comandos y verifica resultados sobre este repositorio | — |
| Motivo de la elección | Es el modelo disponible en el entorno del curso (sin costo adicional para el autor). El requisito era "un agente basta; no se exige MCP, memoria externa, multiagente ni servicios pagos". | — |
| Fecha de trabajo | 2026-10-25 | Reloj del entorno |
| Python | 3.14.8 | `python --version` |
| pytest | 9.1.1 | `python -m pytest --version` |
| SQLite | 3.54.0 (módulo stdlib `sqlite3`) | `python -c "import sqlite3; print(sqlite3.sqlite_version)"` |
| Git | 2.56.0 | `git --version` |

**Datos no visibles en esta sesión:** el texto completo del system prompt del
modelo, la fecha de lanzamiento del modelo y su costo por token. No se inventan.

El harness es el entorno que coordina modelo, herramientas, contexto y
ejecución: se utilizó uno existente (OpenCode) y **no se construyó ninguno**.

---

## 2. Instrucciones y configuraciones realmente usadas

### 2.1 Instrucciones del proyecto: [`AGENTS.md`](../AGENTS.md)

Creado en el commit inicial (`f267201`) y **cargado automáticamente por el
harness** como instrucciones de la sesión (aparece con el encabezado
`Instructions from: .../AGENTS.md`). Extracto saneado de lo que aporta:

| Sección | Contenido | Uso concreto |
| ------- | --------- | ------------ |
| §1 Reglas de dominio | límites consecutivos no son superposición; sólo las activas bloquean; **un único predicado** de superposición; orden de validaciones; una unidad por reserva | definió `dominio.hay_superposicion()` y el orden de `servicio.reservar()` |
| §2 Procedimiento de persistencia | una única capa de acceso a SQLite, transacción por escritura, esquema `IF NOT EXISTS`, verificación obligatoria con `tests/test_persistencia.py` | definió `persistencia.Repositorio` |
| §3 Verificación | `python -m pytest` en verde antes de dar un cambio por terminado | se corrió tras cada cambio (ver §5) |
| §4 Convenciones | español en dominio y documentación, sin dependencias nuevas sin justificar, sin secretos, ISO 8601 + zona declarada | respetado en todo el código |

### 2.2 Configuración externa al repositorio

`~/.config/opencode/` contiene **sólo** `service.json` (credencial del
proveedor del modelo): no se transcribe ni se copió al repositorio. **No hay**
`opencode.json`, ni claves, ni tokens en el proyecto. El proyecto no usa MCP,
memoria externa, ni servicios de pago.

No se definió una configuración de permisos personalizada: el harness operó
con su modo por defecto sobre el directorio de trabajo del repositorio.

---

## 3. Contexto suministrado y qué se excluyó

**Se suministró al agente**

1. `docs/challenge-agents.pdf` (estaba en la raíz al inicio del trabajo) →
   convertido a texto con `pdftotext -layout challenge-agents.pdf` (135 líneas).
   *El modelo no admite
   PDF como entrada, así que el texto extraído fue el contexto real que se usó;
   se declara en lugar de suponer su lectura.*
2. `AGENTS.md` (instrucciones del repositorio).
3. `inventario.json` (las 5 unidades físicas).
4. El contenido de los archivos que el propio agente fue creando, releído con
   las herramientas de lectura antes de modificarlos.

**Se excluyó**

- Conversaciones o sesiones previas: **no existían** (repositorio recién
  inicializado, sin commits).
- Credenciales del proveedor (`service.json`).
- Contenido ajeno al repositorio: nada del sistema fuera de
  `/home/sfr/dev/topicos-challenge`.
- No se pegó ninguna transcripción completa de la conversación en los archivos.

---

## 4. Herramientas, permisos y controles humanos

**Herramientas usadas por el agente**

| Tipo | Acciones |
| ---- | -------- |
| Archivos | leer, escribir y editar (búsqueda exacta) de `.py`, `.md`, `.json`, `.toml`, `.html`, `.css`, `.js` |
| Búsqueda | glob de patrones, grep de contenidos |
| Shell | `git` (add/commit/log/status), `python -m pytest`, `python -m py_compile`, `curl` contra el servidor local, `pdftotext`, `pkill`/`kill` de los procesos que el propio agente levantó |
| Sin uso | MCP, subagentes, servicios pagos, despliegue, autenticación |

**Controles y aprobaciones humanas**

| Control | Momento | Estado |
| ------- | ------- | ------ |
| Elección de stack (Python + pytest) | antes de escribir código | aplicado por el usuario |
| Elección de interfaz (frontend HTML en vez de la CLI recomendada) | antes de escribir la API | aplicado por el usuario |
| Elección de persistencia (SQLite) | antes de escribir código | aplicado por el usuario |
| Modo de trabajo ("el agente construye, el usuario revisa") | antes de escribir código | aplicado por el usuario |
| Revisión de la suite en verde | antes de cada commit | ejecutada por el agente, verificable con `docs/evidencia/pytest.txt` |
| Revisión humana de resultados | se registra en [`decisiones-y-delegacion.md`](decisiones-y-delegacion.md) | registrada allí, con enlace a la evidencia |

**Qué se revisó antes de aceptar resultados**

1. Las 82 pruebas automatizadas en verde (`docs/evidencia/pytest.txt`).
2. Las 14 etapas del recorrido HTTP, con los códigos esperados
   (`docs/evidencia/smoke-http.txt`).
3. La persistencia real entre **dos procesos distintos**: kill + arranque nuevo
   con el mismo archivo (etapas 12–14 del mismo archivo, más
   `tests/test_persistencia.py::test_persistencia_entre_procesos_distintos`).
4. El diagnóstico de la única corrección ocurrida
   (`docs/evidencia/diagnostico-correccion.txt`).

---

## 5. Adaptación específica comprobable

Dos instrucciones propias de este proyecto, escritas *antes* de la
implementación y con evidencia de que se aplicaron:

### 5.1 Instrucción sobre turnos consecutivos — `AGENTS.md` §1.1

> *"Límites consecutivos no son superposición: dos reservas activas de la misma
> unidad donde `fin(A) == inicio(B)` son ambas válidas."*

**Evidencia de uso**

- `tests/test_reglas.py::test_acepta_limite_consecutivo_posterior` — reproduce
  el ejemplo del enunciado (10:00–11:00 y luego 11:00–12:00).
- `tests/test_reglas.py::test_acepta_limite_consecutivo_anterior` y
  `test_tres_turnos_consecutivos_en_la_misma_unidad`.
- `tests/test_dominio.py::test_predicado_de_superposicion` — 8 casos límite,
  incluidos `fin == inicio` en ambos sentidos.
- **Además**, `test_el_predicado_vive_en_un_solo_lugar` falla si alguien vuelve
  a implementar la comparación de intervalos en dos lugares: es la guarda de la
  propia instrucción.
- Verificación en vivo: etapa 6 de `docs/evidencia/smoke-http.txt`
  (HTTP 201 para el límite consecutivo).
- Commits: `21823aa` (predicado en el dominio), `06e9408` y `f720791`
  (pruebas de dominio y de reglas).

### 5.2 Procedimiento de persistencia — `AGENTS.md` §2

> *"Cada escritura es una sola transacción con commit explícito… el esquema se
> crea con `CREATE TABLE IF NOT EXISTS`… verificar con
> `python -m pytest tests/test_persistencia.py`."*

**Evidencia de uso**

- `src/reservas/persistencia.py`: una única clase `Repositorio`, transacciones
  `BEGIN IMMEDIATE`, esquema `IF NOT EXISTS`.
- `tests/test_persistencia.py` (5 pruebas), entre ellas
  `test_persistencia_entre_procesos_distintos`, que lanza **dos procesos de
  Python distintos** sobre el mismo archivo.
- Corrida registrada en `docs/evidencia/pytest.txt` y verificación manual en
  vivo en las etapas 12–14 de `docs/evidencia/smoke-http.txt`.
- Commits: `a4de22d` (repositorio) y `ed6bf10` (pruebas de persistencia).

---

## 6. Retención del progreso y de las decisiones

- Todo el progreso quedó en **Git** (commits con mensajes explicativos; la
  versión inicial de la especificación sigue recuperable en `76523c5`) y en
  [`decisiones-y-delegacion.md`](decisiones-y-delegacion.md).
- El README conserva el historial de versiones de la especificación (§1) y la
  evolución de la solución (§2).
- **No** se reiniciaron sesiones ni se provocaron fallas a propósito; la única
  falla real ocurrida está documentada en el episodio 3 de decisiones.

---

## 7. Reproducibilidad sin la cuenta del modelo del autor

La aplicación y sus pruebas no hacen ninguna llamada al modelo ni a servicios
externos en tiempo de ejecución: sólo `sqlite3`, `http.server` y `json` de la
biblioteca estándar, más `pytest` para las pruebas.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"     # sólo pytest como dependencia de desarrollo
.venv/bin/python -m pytest            # 82 pruebas
PYTHONPATH=src .venv/bin/python -m reservas --puerto 8000
bash docs/evidencia/smoke.sh          # recorrido HTTP + reinicio, con salidas esperadas
```

| Comando | Versión | Resultado registrado |
| ------- | ------- | -------------------- |
| `python -m pytest` | Python 3.14.8 / pytest 9.1.1 | `82 passed` → `docs/evidencia/pytest.txt` |
| `bash docs/evidencia/smoke.sh` | curl + Python 3.14.8 | 14 etapas con los códigos esperados → `docs/evidencia/smoke-http.txt` |
| `PYTHONPATH=src … diagnostico_correccion.py` | Python 3.14.8 | diagnóstico de la corrección → `docs/evidencia/diagnostico-correccion.txt` |

No hay pasos de la consigna pendientes ni sin ejecutar. Fuera de la corrección
documentada en el episodio 3, los intentos fallidos durante el desarrollo fueron
operativos y sin efecto sobre el entregable, y se declaran por honestidad:

- la **lectura directa del PDF** con la herramienta de archivos falló (el modelo
  no admite PDF como entrada): se usó `pdftotext -layout` y ese texto fue el
  contexto real;
- una llamada a `pkill` con un patrón demasiado amplio **terminó con la propia
  terminal** del agente; no afectó datos ni código y se repitió con `kill` por
  PID;
- una invocación incorrecta de `python -c` al regenerar un archivo de evidencia
  (`NameError: __file__`): se corrió el comando documentado en su lugar;
- un intento de edición de texto que no encontró la cadena buscada (se repitió
  con el contexto exacto).
