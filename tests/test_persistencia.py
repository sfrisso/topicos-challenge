"""Persistencia: las reservas sobreviven a detener y reiniciar la aplicación.

Corre `tests/test_persistencia.py` tal como exige AGENTS.md §2.4.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import INVENTARIO, RAIZ, hhmm


def test_reinicio_conserva_activas_y_canceladas(ruta_db, reabrir):
    primera = reabrir()
    activa = primera.reservar("MIC-01", "Ana Díaz", hhmm(10), hhmm(11))
    a_cancelar = primera.reservar("OSC-01", "Bruno Sáez", hhmm(9), hhmm(10))
    primera.cancelar(a_cancelar.id)

    # "Reinicio": una instancia nueva, sobre el mismo archivo, sin borrar nada.
    segunda = reabrir()
    historial = segunda.listar()

    assert len(historial) == 2
    por_id = {r.id: r for r in historial}

    recuperada = por_id[activa.id]
    assert recuperada.estado == "activa"
    assert (recuperada.unidad, recuperada.solicitante) == ("MIC-01", "Ana Díaz")
    assert recuperada.inicio == activa.inicio and recuperada.fin == activa.fin

    recuperada_cancelada = por_id[a_cancelar.id]
    assert recuperada_cancelada.estado == "cancelada"
    assert recuperada_cancelada.cancelada_en is not None
    assert recuperada_cancelada.solicitante == "Bruno Sáez"


def test_reabrir_recrea_el_esquema_sin_borrar_filas(ruta_db, reabrir):
    """`CREATE TABLE IF NOT EXISTS` en cada arranque: reiniciar nunca borra."""
    primera = reabrir()
    reserva = primera.reservar("MUL-01", "Carla Nuñez", hhmm(13), hhmm(14))

    for _ in range(3):
        reabrir()  # tres "arranques" consecutivos

    posterior = reabrir()
    assert [r.id for r in posterior.listar()] == [reserva.id]


def test_el_cancelado_sigue_liberando_el_intervalo_tras_el_reinicio(ruta_db, reabrir):
    primera = reabrir()
    creada = primera.reservar("FUE-01", "Ana Díaz", hhmm(16), hhmm(17))
    primera.cancelar(creada.id)

    segunda = reabrir()
    assert segunda.disponibilidad("FUE-01", hhmm(16), hhmm(17))["disponible"] is True
    assert segunda.listar()[0].estado == "cancelada"


def test_el_archivo_de_datos_se_crea_en_la_ruta_indicada(ruta_db, reabrir):
    assert not ruta_db.exists()
    reabrir()
    assert ruta_db.exists() and ruta_db.stat().st_size > 0


# ------------------------------------------------ verificación con procesos reales
# Dos procesos distintos: el primero crea datos y termina; el segundo, sin ningún
# estado en memoria, los recupera del archivo. Es el equivalente automático de
# "detener y reiniciar la aplicación sin borrar datos".
_SCRIPT = """
import json, sys
from reservas.servicio import ServicioReservas
servicio = ServicioReservas.crear(sys.argv[1], sys.argv[2])
accion = sys.argv[3]
if accion == "crear":
    r1 = servicio.reservar("MIC-01", "Ana Díaz", "2030-06-10T10:00", "2030-06-10T11:00")
    r2 = servicio.reservar("MIC-02", "Bruno Sáez", "2030-06-10T10:00", "2030-06-10T11:00")
    servicio.cancelar(r2.id)
    print(json.dumps({"creadas": [r1.id, r2.id]}))
else:
    print(json.dumps({"reservas": [r.a_dict() for r in servicio.listar()]}))
"""


def _ejecutar(ruta_db: Path, accion: str) -> dict:
    entorno = dict(os.environ)
    entorno["PYTHONPATH"] = str(RAIZ / "src")
    proceso = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(ruta_db), str(INVENTARIO), accion],
        cwd=RAIZ,
        env=entorno,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proceso.returncode == 0, f"falló: {proceso.stderr}"
    return json.loads(proceso.stdout)


def test_persistencia_entre_procesos_distintos(ruta_db):
    primero = _ejecutar(ruta_db, "crear")
    segundo = _ejecutar(ruta_db, "leer")

    assert len(primero["creadas"]) == 2
    recuperadas = {r["id"]: r for r in segundo["reservas"]}
    assert len(recuperadas) == 2

    activa = recuperadas[primero["creadas"][0]]
    assert activa["estado"] == "activa"
    assert activa["solicitante"] == "Ana Díaz"
    assert activa["inicio"].startswith("2030-06-10T10:00")

    cancelada = recuperadas[primero["creadas"][1]]
    assert cancelada["estado"] == "cancelada"
    assert cancelada["cancelada_en"] is not None
