# Sistema de reservas de unidades de laboratorio

Challenge *Desarrollo de un sistema de reservas con agentes* — [docs/challenge-agents.pdf](docs/challenge-agents.pdf).

Aplicación local para consultar disponibilidad, reservar y cancelar unidades de
laboratorio sin perder el historial, con frontend HTML y persistencia en SQLite.

---

## 1. Especificación breve

### Problema

La coordinación de un laboratorio registra pedidos en mensajes y en una
planilla. Se confirma la misma unidad para horarios superpuestos y, a veces,
una cancelación sigue bloqueando el horario. Hace falta **consultar
disponibilidad, reservar y cancelar sin perder el historial**.

El inventario está definido y no se administra en esta solución: cada ID
identifica una unidad física distinta.

| ID de unidad | Equipo                 |
| ------------ | ---------------------- |
| MIC-01       | Microscopio digital    |
| MIC-02       | Microscopio digital    |
| OSC-01       | Osciloscopio           |
| MUL-01       | Multímetro             |
| FUE-01       | Fuente de alimentación |

### Alcance

**Incluye**

- Leer el inventario precargado (`inventario.json`) y consultar disponibilidad
  por unidad e intervalo.
- Crear una reserva identificable con unidad, solicitante ficticio no vacío,
  inicio y fin (una unidad por reserva).
- Cancelar una reserva conservando su identificador y sus datos, y liberando el
  intervalo.
- Persistir reservas y estados para recuperarlos al reiniciar la aplicación.
- API local JSON + página HTML de una sola vista (sin dependencias externas).

**Fuera de alcance** (según la consigna): autenticación y roles reales,
notificaciones, pagos, integraciones externas, despliegue obligatorio, frente
gráfico complejo, concurrencia distribuida y escalabilidad de producción.

### Reglas

| #  | Regla                                                                 |
| -- | --------------------------------------------------------------------- |
| 1  | Una reserva **activa** ocupa el intervalo; una **cancelada** no bloquea. |
| 2  | Validar: unidad conocida, solicitante no vacío ni solo espacios, fecha y hora válidas e **inicio estrictamente anterior al fin**. |
| 3  | Rechazar superposiciones de reservas **activas** de la **misma unidad**. |
| 4  | Permitir límites consecutivos (`fin(A) == inicio(B)`) y reservas simultáneas de unidades distintas. |
| 5  | La consulta de disponibilidad usa **exactamente estas mismas reglas**. |
| 6  | Cancelar conserva el registro (identificador y datos originales) y libera el intervalo. |

Ejemplo de la consigna: con MIC-01 reservado de 10:00 a 11:00 se rechaza
10:30–11:30 y se permite 11:00–12:00; MIC-02 puede reservarse de 10:00 a 11:00
aunque MIC-01 esté ocupado.

### Supuestos

| #  | Supuesto |
| -- | -------- |
| A1 | **Zona horaria:** `America/Argentina/Buenos_Aires` (UTC−3, sin horario de verano). Las entradas ISO sin offset se interpretan en esa zona; internamente se guarda el instante UTC y se responde con el offset `-03:00`. |
| A2 | **Formato:** ISO 8601 `AAAA-MM-DDTHH:MM` (con segundos opcionales). Una fecha sin hora se rechaza (`FECHA_INVALIDA`). |
| A3 | **Fechas pasadas:** no se puede *crear* una reserva cuyo inicio sea anterior al momento actual (comparación minuto a minuto). *Consultar* disponibilidad en el pasado sí está permitido: es informativa y no crea datos. |
| A4 | **Duración y anticipación:** no se aplican límites; sólo `inicio < fin`. |
| A5 | **Solicitante:** texto libre, se recorta y se almacena tal cual; siempre ficticio. |
| A6 | **Identificadores:** enteros autoincrementales, nunca se reutilizan ni se borran. |
| A7 | **Cancelación:** es única; volver a cancelar responde `YA_CANCELADA` (HTTP 409). |
| A8 | **Datos:** archivo `data/reservas.db` (SQLite). Reiniciar la aplicación **no** borra datos; **borrar ese archivo sí** (ver §2). |
| A9 | **Red:** el servidor escucha sólo en `127.0.0.1` por defecto; no hay autenticación porque no sale de la máquina local. |
| A10 | **Escrituras concurrentes:** el servidor atiende en varios hilos y las escrituras se serializan con un bloqueo y una transacción `BEGIN IMMEDIATE`; no se contempla concurrencia distribuida. |

### Requisitos verificables y criterios de aceptación

| ID  | Requisito | Verificado por |
| --- | --------- | -------------- |
| R1  | Lee el inventario precargado y lo valida | `test_inventario_precargado`, `test_inventario_rechaza_ids_repetidos` |
| R2  | Consulta disponibilidad por unidad e intervalo | `test_disponibilidad_devuelve_el_conflicto`, `test_disponibilidad_sobre_el_servidor` |
| R3  | Crea una reserva identificable con unidad, solicitante, inicio y fin | `test_creacion_valida`, `test_cada_creacion_recibe_identificador_propio`, `test_crear_reserva_por_http` |
| R4  | Rechaza superposiciones de activas de la misma unidad | `test_rechaza_superposicion_de_reservas_activas` (5 variantes), `test_superposicion_responde_409` |
| R5  | Admite límites consecutivos | `test_acepta_limite_consecutivo_posterior`, `test_acepta_limite_consecutivo_anterior`, `test_tres_turnos_consecutivos_en_la_misma_unidad` |
| R6  | Admite unidades distintas en el mismo intervalo | `test_unidades_distintas_pueden_reservar_el_mismo_intervalo` |
| R7  | Rechaza entradas inválidas (unidad, solicitante, fechas, intervalo, pasado) | `test_entradas_invalidas` (10 variantes) y `test_orden_de_validaciones_*` |
| R8  | Cancela conservando el registro y liberando el horario | `test_cancelacion_conserva_el_registro_y_libera_el_horario`, `test_cancelada_no_bloquea_pero_activa_si`, `test_cancelar_por_http_libera_el_horario` |
| R9  | Persiste activas y canceladas al reiniciar sin borrar datos | `test_reinicio_conserva_activas_y_canceladas`, `test_persistencia_entre_procesos_distintos`, `test_reabrir_recrea_el_esquema_sin_borrar_filas` |
| R10 | La consulta usa las mismas reglas que la creación | `test_disponibilidad_valida_como_la_creacion`, `test_el_predicado_vive_en_un_solo_lugar` |

**Criterio de aceptación general:** `python -m pytest` en verde y los seis
puntos de "Verificaciones requeridas" cubiertos por pruebas automatizadas
(creación válida, rechazo de superposición, límites consecutivos, unidades
distintas simultáneas, entradas inválidas, cancelación que conserva y libera).

### Historial de cambios significativos

| Versión | Fecha       | Cambio                                                                 | Commit |
| ------- | ----------- | ---------------------------------------------------------------------- | ------ |
| v0.1    | 2026-10-25  | Especificación inicial: problema, alcance, reglas, supuestos y R1–R10. Motivo: fijar criterios antes de escribir código. | `76523c5` |
| v0.2    | 2026-10-25  | Sin cambios de especificación; se implementó el núcleo que la cumple (dominio, persistencia, servicio y sus pruebas). | `21823aa` → `ed6bf10` |
| v0.3    | 2026-10-25  | Se amplía la interfaz prevista: de API/consola a **frontend HTML** a pedido del usuario. | `812c377` |
| v0.4    | 2026-10-25  | Documentación de solución, preparación del agente, decisiones y evidencias. | `ea98641` → `871c2af` |

---

## 2. Solución

### Estructura

```
.
├── AGENTS.md                       instrucciones del agente (el harness las inyecta)
├── README.md                       este archivo
├── inventario.json                 inventario precargado (5 unidades)
├── pyproject.toml                  metadatos del paquete + configuración de pytest
├── src/reservas/
│   ├── dominio.py                  reglas puras: fechas, validaciones, superposición
│   ├── persistencia.py             SQLite: única capa de acceso a datos
│   ├── servicio.py                 orquestación y orden de validaciones
│   ├── api.py                      servidor HTTP (stdlib) + API JSON
│   └── __main__.py                 punto de entrada: python -m reservas
├── static/
│   ├── index.html                  página de una sola vista
│   ├── styles.css                  estilos (sin CDN)
│   └── app.js                      lógica de consulta, alta y cancelación
├── tests/
│   ├── conftest.py                 reloj fijo y fixtures
│   ├── test_dominio.py             31 pruebas de reglas puras
│   ├── test_reglas.py              32 pruebas: creación, superposición, límites, cancelación
│   ├── test_persistencia.py         5 pruebas de reinicio (una entre dos procesos)
│   └── test_api.py                 14 pruebas de punta a punta por HTTP
├── docs/
│   ├── preparacion-del-agente.md   entorno, modelo, instrucciones, permisos, adaptación
│   ├── decisiones-y-delegacion.md  decisiones técnicas + los 3 episodios de delegación
│   └── evidencia/                  salidas reproducibles de pruebas y recorrido HTTP
└── data/                           reservas.db — ignorado por Git
```

### Decisiones técnicas

- **Tres capas con una regla por lugar:** `dominio.py` no toca archivos ni base
  de datos y concentra el **único** predicado de superposición;
  `persistencia.py` es el único que abre SQLite; `servicio.py` aplica las
  validaciones en orden y `api.py` sólo traduce HTTP ⇄ servicio.
- **Transacción atómica al crear:** el chequeo de superposición y el `INSERT`
  ocurren dentro de una misma transacción `BEGIN IMMEDIATE`, con un bloqueo por
  proceso, de modo que dos altas simultáneas no pueden colarse.
- **Fechas:** se reciben como texto ISO sin offset (zona declarada), se guardan
  como instante UTC en epoch y se devuelven con offset `-03:00`.
- **Reloj inyectable:** `ServicioReservas(ahora=…)` permite probar la regla de
  "no en el pasado" de forma determinística.
- **Servidor stdlib:** `ThreadingHTTPServer` + `json` + `pathlib`; cero
  dependencias de runtime. Los archivos estáticos se resuelven con verificación
  de ruta para impedir salir de `static/`.
- **Frontend sin build:** HTML + CSS + JS puro, sin CDN, para que funcione
  igual con o sin conexión.

### Requisitos previos y versiones

| Requisito | Versión probada |
| --------- | --------------- |
| Python | **3.14.8** (requiere ≥ 3.11 por `zoneinfo` y `fromisoformat`) |
| pytest | **9.1.1** (única dependencia, sólo de desarrollo) |
| SQLite | 3.54.0, vía módulo stdlib `sqlite3` (no requiere instalar nada) |
| Navegador | cualquiera con soporte de `fetch` y `datetime-local` |
| Red | no hace falta en tiempo de ejecución; sí para instalar pytest |

### Instalación

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"      # instala el paquete + pytest
```

Alternativa sin instalar el paquete (sólo instala pytest):

```bash
python3 -m venv .venv
.venv/bin/pip install pytest
PYTHONPATH=src .venv/bin/python -m pytest
```

### Carga inicial y reinicio de datos

- **Inventario:** no hay carga manual. Se lee `inventario.json` en cada
  arranque; si se edita el archivo, el cambio se refleja al reiniciar. La
  aplicación no administra inventario (regla de la consigna).
- **Base de datos:** se crea sola en `data/reservas.db` en el primer arranque.
- **Reiniciar la aplicación NO borra reservas** (el esquema usa
  `CREATE TABLE IF NOT EXISTS` y ningún comando borra filas).
- **⚠ Borrar datos SÍ los borra:**

  ```bash
  rm -f data/reservas.db     # elimina TODAS las reservas, activas y canceladas
  ```

  Al volver a arrancar, la aplicación recrea el archivo vacío. No hay comando
  de "restaurar inventario" porque el inventario no se modifica nunca.

### Comandos

| Acción | Comando |
| ------ | ------- |
| Arrancar la aplicación | `PYTHONPATH=src .venv/bin/python -m reservas --puerto 8000` |
| …con el paquete instalado | `.venv/bin/reservas --puerto 8000` |
| Opciones | `--host`, `--puerto`, `--db <ruta>`, `--inventario <ruta>` |
| Pruebas | `.venv/bin/python -m pytest` (o `-vv` para el detalle de cada una) |
| Pruebas de persistencia | `.venv/bin/python -m pytest tests/test_persistencia.py` |
| Recorrido HTTP + reinicio (evidencia) | `bash docs/evidencia/smoke.sh` |
| Detener | `Ctrl+C` en la terminal donde corre |

### Interfaz

Con la aplicación corriendo, abre <http://127.0.0.1:8000>:

![Aplicación de reservas en el navegador: inventario precargado, formulario para crear una reserva, resultado de la consulta de disponibilidad y listado de reservas con su estado](docs/frontend-view.png)

*Captura real de la página (`docs/frontend-view.png`): arriba el inventario
precargado, en el medio el formulario con horarios sugeridos y el resultado de
la consulta de disponibilidad, y abajo el listado con el estado de cada reserva
y su botón de cancelar.*

### API local

| Método | Ruta | Descripción | Errores |
| ------ | ---- | ----------- | ------- |
| `GET` | `/` | página HTML de la aplicación | — |
| `GET` | `/static/<archivo>` | CSS/JS | 404 |
| `GET` | `/api/inventario` | unidades precargadas + zona horaria | 404 |
| `GET` | `/api/disponibilidad?unidad=&inicio=&fin=` | ¿libre el intervalo? | 400 |
| `GET` | `/api/reservas` | todas (activas y canceladas) | — |
| `POST` | `/api/reservas` | crea `{unidad, solicitante, inicio, fin}` | 400, 409 |
| `POST` | `/api/reservas/<id>/cancelar` | cancela conservando la fila | 404, 409 |

Códigos de error de negocio: `UNIDAD_DESCONOCIDA`, `SOLICITANTE_VACIO`,
`FECHA_INVALIDA`, `INTERVALO_INVALIDO`, `RESERVA_EN_PASADO` (400);
`SUPERPOSICION`, `YA_CANCELADA` (409); `RESERVA_NO_ENCONTRADA` (404).

### Ejemplo de entrada y salida

Con la aplicación corriendo, en el navegador (`http://127.0.0.1:8000`) se
selecciona **MIC-01**, se escribe un solicitante y los horarios, y se pulsa
*Consultar disponibilidad* o *Reservar*. Equivalente por terminal:

```console
$ curl -X POST http://127.0.0.1:8000/api/reservas \
    -H 'Content-Type: application/json' \
    -d '{"unidad":"MIC-01","solicitante":"Ana Díaz",
         "inicio":"2030-06-10T10:00","fin":"2030-06-10T11:00"}'
{
  "reserva": {
    "id": 1,
    "unidad": "MIC-01",
    "solicitante": "Ana Díaz",
    "inicio": "2030-06-10T10:00:00-03:00",
    "fin": "2030-06-10T11:00:00-03:00",
    "estado": "activa",
    "creada_en": "2026-10-25T16:56:05-03:00",
    "cancelada_en": null
  }
}
[HTTP 201]

$ curl -X POST http://127.0.0.1:8000/api/reservas \
    -H 'Content-Type: application/json' \
    -d '{"unidad":"MIC-01","solicitante":"Carla Nuñez",
         "inicio":"2030-06-10T10:30","fin":"2030-06-10T11:30"}'
{
  "error": {
    "codigo": "SUPERPOSICION",
    "mensaje": "La unidad MIC-01 ya está reservada de 2030-06-10T10:00:00-03:00 a 2030-06-10T11:00:00-03:00 (reserva #1, Ana Díaz)."
  }
}
[HTTP 409]
```

La salida completa de un recorrido de 14 pasos (crear, rechazar, límite
consecutivo, unidad distinta, entrada inválida, cancelar, consultar, **detener
y reiniciar**) está en
[`docs/evidencia/smoke-http.txt`](docs/evidencia/smoke-http.txt) y se regenera
con `bash docs/evidencia/smoke.sh`.

### Dónde persisten los datos

En `data/reservas.db` (SQLite; cambiable con `--db`). Tabla `reservas`:
`id`, `unidad`, `solicitante`, `inicio`, `fin` (epoch UTC), `estado`
(`activa`/`cancelada`), `creada_en`, `cancelada_en`. El directorio `data/` está
en `.gitignore`.

### Pendientes y limitaciones

1. Sin prueba automatizada del clic en navegador; la API sí está cubierta de
   punta a punta (`tests/test_api.py`, 14 pruebas).
2. Sin límites de duración ni de anticipación (supuesto A4).
3. Sin autenticación, notificaciones ni despliegue (fuera de alcance).
4. Un solo proceso: no hay concurrencia distribuida (supuesto A10).
5. El inventario no se administra desde la aplicación; sólo se edita el JSON.

---

## 3. Preparación del agente

Resumen; el registro completo con comandos y enlaces está en
[`docs/preparacion-del-agente.md`](docs/preparacion-del-agente.md).

| Tema | Registro |
| ---- | -------- |
| **Entorno y modelo** | Harness **OpenCode v2.1.4** (`opencode --version`), modelo `mimo-v2.6-flash-free` del proveedor `opencode`, usado como agente único sobre el repositorio con herramientas reales de archivo y shell. Motivo: es el modelo disponible en el entorno del curso. **No visibles:** textos del system prompt, fecha de lanzamiento y costo del modelo; se declara en lugar de inventarlos. |
| **Instrucciones** | [`AGENTS.md`](AGENTS.md) en la raíz, creado en el commit inicial y **cargado automáticamente por el harness** como instrucciones de la sesión: reglas de dominio (límites consecutivos, un solo predicado, orden de validaciones), procedimiento de persistencia, verificación obligatoria y convenciones. |
| **Configuración externa** | Sólo `~/.config/opencode/service.json` (credencial del proveedor): **no se transcribe ni se copió al repo**. No hay `opencode.json`, claves ni tokens en el proyecto. |
| **Contexto suministrado** | Texto del PDF extraído con `pdftotext -layout` (135 líneas; el modelo no admite PDF como entrada), `AGENTS.md`, `inventario.json` y los propios archivos del repo antes de modificarlos. **Excluido:** sesiones previas (no las hubo: repo sin commits), credenciales y todo lo ajeno al repositorio. Sin transcripciones completas de la conversación. |
| **Herramientas y permisos** | Lectura/edición de archivos, búsqueda, `git`, `python`, `pytest`, `curl` local y `kill` de los procesos que el agente levantó. Sin MCP, sin memoria externa, sin subagentes, sin servicios pagos. Sin configuración de permisos personalizada: modo por defecto del harness. |
| **Controles humanos** | Cuatro decisiones tomadas antes de escribir código (stack Python+pytest, persistencia SQLite, frontend HTML, modo "el agente construye y el usuario revisa") y la revisión de resultados documentada en §4. |
| **Adaptación específica** | (a) instrucción sobre **turnos consecutivos** — `AGENTS.md` §1.1, evidencia: `test_acepta_limite_consecutivo_posterior`, `test_predicado_de_superposicion` (8 casos límite) y `test_el_predicado_vive_en_un_solo_lugar`, que **falla si se duplica la regla**; (b) **procedimiento de persistencia** — `AGENTS.md` §2, evidencia: `tests/test_persistencia.py` (5 pruebas) y las etapas 12–14 del recorrido HTTP. |
| **Retención del progreso** | Todo versionado en Git (commits con mensajes explicativos y una versión inicial de la especificación recuperable) y en [`docs/decisiones-y-delegacion.md`](docs/decisiones-y-delegacion.md). No se reiniciaron sesiones ni se provocaron fallas. |
| **Ejecuciones reales** | [`docs/evidencia/pytest.txt`](docs/evidencia/pytest.txt) (82 pruebas, `-vv`), [`docs/evidencia/smoke-http.txt`](docs/evidencia/smoke-http.txt) (14 etapas con códigos HTTP), [`docs/evidencia/diagnostico-correccion.txt`](docs/evidencia/diagnostico-correccion.txt) (única corrección). |

---

## 4. Registro de decisiones y delegación

Registro completo en
[`docs/decisiones-y-delegacion.md`](docs/decisiones-y-delegacion.md) (11
decisiones técnicas con alternativa descartada, motivo y consecuencia, más el
detalle de cada episodio).

### Episodio 1 — De la consigna al núcleo de reglas

- **Objetivo:** convertir las reglas de la consigna en código con pruebas.
- **Contexto e instrucción:** texto del PDF (extraído con `pdftotext`), más
  `AGENTS.md` §1.1 (*los límites consecutivos no son superposición*) y §1.3
  (*un único predicado, usado por creación y consulta*).
- **Acción:** `dominio.py`, `persistencia.py`, `servicio.py` y 68 pruebas de
  dominio/reglas/persistencia.
- **Decisión humana: aceptar**, tras elegir el usuario **Python + pytest** y
  **SQLite** antes de empezar (motivo: reproducibilidad sin la cuenta del
  modelo).
- **Evidencia:** commit `76523c5` (especificación) y el bloque de `21823aa` a
  `ed6bf10` (dominio, persistencia, servicio y sus 68 pruebas);
  [`docs/evidencia/pytest.txt`](docs/evidencia/pytest.txt).

### Episodio 2 — De la CLI recomendada a un frontend HTML

- **Objetivo:** elegir la interfaz (la consigna admite consola o API local).
- **Contexto e instrucción:** pregunta con tres opciones; el agente recomendó
  CLI.
- **Acción:** servidor HTTP stdlib con API JSON + página HTML/CSS/JS sin CDN.
- **Decisión humana: aceptar la opción contraria a la recomendación** — el
  usuario respondió *"make a simple frontend using html"*. Consecuencia: más
  código y 14 pruebas de API adicionales.
- **Evidencia:** commits `812c377` (frontend) y `61ebcaa` (pruebas HTTP),
  `tests/test_api.py`,
  [`docs/evidencia/smoke-http.txt`](docs/evidencia/smoke-http.txt).

### Episodio 3 — Corrección de una prueba incorrecta

- **Objetivo:** dejar la suite en verde antes de commitear (`AGENTS.md` §3).
- **Contexto e instrucción:** primera corrida `81 passed, 1 failed` en
  `test_unidades_distintas_pueden_reservar_el_mismo_intervalo`.
- **Acción:** diagnóstico — **el código estaba bien y la afirmación no**: la
  prueba reservaba MIC-02 de 10:00 a 11:00 y después afirmaba que esa misma
  ventana seguía libre. Se corrigió la prueba, no la implementación.
- **Decisión humana:** el usuario fue consultado e interrumpió la consulta
  respondiendo *«continue where i accidentaly interrupted»*, delegando la
  continuación; la corrección quedó aceptada tácitamente y verificada con la
  suite en verde. **No hubo ninguna otra corrección ni rechazo.**
- **Evidencia:** [`docs/evidencia/diagnostico-correccion.txt`](docs/evidencia/diagnostico-correccion.txt)
  con su script reproducible `diagnostico_correccion.py`; commit `f720791`.
  *La salida de la corrida que falló ocurrió antes de ese commit y no quedó
  versionada: se conserva el diagnóstico reproducible en su lugar.*

### Informado vs. ejecutado

Lo que el agente afirmó y lo que realmente se ejecutó está tabulado en
[`docs/decisiones-y-delegacion.md`](docs/decisiones-y-delegacion.md) §3, con
enlace a la salida correspondiente. Punto declarado como **no ejecutado**: la
prueba manual con clics en el navegador (la API y los assets sí están cubiertos
por pruebas automatizadas).

---

## Entrega

Repositorio en la rama `main`; el historial completo se consulta con
`git log --oneline`. Cada versión de la especificación queda asociada a su
commit en la tabla del §1.
