# Sistema de reservas de unidades de laboratorio

Challenge *Desarrollo de un sistema de reservas con agentes* — [challenge-agents.pdf](challenge-agents.pdf).

> **Estado:** este README arranca con la sección de especificación (v0.1). Las
> secciones de solución, preparación del agente y decisiones se agregan en
> commits posteriores.

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
(recreación válida, rechazo de superposición, límites consecutivos, unidades
distintas simultáneas, entradas inválidas, cancelación que conserva y libera).

### Historial de cambios significativos

| Versión | Fecha       | Cambio                                             |
| ------- | ----------- | -------------------------------------------------- |
| v0.1    | 2026-10-25  | Especificación inicial: reglas, supuestos y criterios. |

---

*Las secciones 2 (Solución), 3 (Preparación del agente) y 4 (Registro de
decisiones y delegación) se incorporan en los commits siguientes.*
