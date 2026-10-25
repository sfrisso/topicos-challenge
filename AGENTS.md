# Instrucciones para el agente de programación

Este archivo es la configuración de contexto del repositorio. Se carga al inicio de cada
sesión del agente y debe respetarse en todos los cambios.

## 1. Reglas de dominio (no negociables)

1. **Límites consecutivos no son superposición.** Dos reservas activas de la *misma*
   unidad donde `fin(A) == inicio(B)` son ambas válidas y deben aceptarse.
   Ejemplo verificable: MIC-01 de 10:00 a 11:00 y de 11:00 a 12:00 conviven.
2. **Solo las reservas activas bloquean.** Una reserva cancelada conserva su fila,
   su identificador y sus datos originales, pero deja de ocupar el intervalo.
3. **La consulta de disponibilidad usa exactamente el mismo predicado que la
   creación.** Está prohibido duplicar la lógica de superposición en dos lugares:
   el predicado vive en `reservas.dominio.hay_superposicion()` y ambas rutas lo usan.
4. **Una unidad por reserva.** No agregar campos de múltiples unidades.
5. **Validaciones en este orden**, devolviendo el primer error: unidad conocida →
   solicitante no vacío (tampoco solo espacios) → fecha/hora válida →
   `inicio < fin` estricto → no en el pasado → sin superposición.

## 2. Procedimiento de persistencia

1. Toda escritura pasa por `reservas.persistencia.Repositorio`; ningún otro módulo
   abre `sqlite3` directamente.
2. Cada operación de escritura es una sola transacción con `commit` explícito
   (`INSERT` de reserva o `UPDATE` de cancelación). No hay escrituras parciales.
3. El esquema se crea con `CREATE TABLE IF NOT EXISTS` al abrir: reiniciar la
   aplicación **nunca** borra datos; solo borrar `data/reservas.db` lo hace.
4. Verificación obligatoria al terminar un cambio de persistencia: correr
   `python -m pytest tests/test_persistencia.py`, que cierra y reabre el archivo
   y verifica que activas *y* canceladas siguen presentes.

## 3. Cómo verificar antes de entregar

```bash
python -m pytest            # suite completa, debe quedar en verde
python -m py_compile src/reservas/*.py
```

Ningún cambio se considera terminado sin la suite en verde. Si una prueba falla,
se corrige el código o se documenta el motivo en `docs/decisiones.md`; nunca se
"arregla" desactivando la prueba sin dejar registro.

## 4. Convenciones

- Español en nombres de dominio, mensajes de error, README y documentación.
- Sin dependencias nuevas sin justificarlo en `docs/decisiones.md`.
- Secretos, tokens y datos reales: prohibidos. Solicitantes siempre ficticios.
- Fechas en entrada/salida ISO 8601 (`AAAA-MM-DDTHH:MM`), zona horaria declarada
  en el README.
