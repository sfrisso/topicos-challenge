"""Comunes a toda la suite: inventario real del repositorio y reloj fijo."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from reservas.dominio import ZONA_HORARIA
from reservas.servicio import ServicioReservas

RAIZ = Path(__file__).resolve().parents[1]
INVENTARIO = RAIZ / "inventario.json"

# Reloj fijo para tests determinísticos: 2030-06-10 07:00 en la zona declarada.
# Queda antes del ejemplo del enunciado (10:00–11:00), así los tests pueden
# reproducirlo tal cual.
RELOJ = datetime(2030, 6, 10, 7, 0, tzinfo=ZoneInfo(ZONA_HORARIA))
DIA = "2030-06-10"  # todos los horarios de prueba ocurren después del reloj


def hhmm(hora: int, minuto: int = 0) -> str:
    """'10:30' -> '2030-06-10T10:30' (texto ISO sin offset)."""
    return f"{DIA}T{hora:02d}:{minuto:02d}"


@pytest.fixture
def ruta_db(tmp_path) -> Path:
    return tmp_path / "reservas.db"


@pytest.fixture
def reabrir(ruta_db):
    """Fábrica que 'reinicia' la aplicación contra el mismo archivo de datos."""

    def _crear() -> ServicioReservas:
        return ServicioReservas.crear(ruta_db, INVENTARIO, ahora=lambda: RELOJ)

    return _crear


@pytest.fixture
def servicio(reabrir) -> ServicioReservas:
    return reabrir()
