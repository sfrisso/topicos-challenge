"""Capa de persistencia: todo acceso a SQLite pasa por aquí.

Reglas de la sección 2 de AGENTS.md:
  * un solo archivo de base de datos por aplicación;
  * cada escritura es una transacción con commit explícito;
  * el esquema se crea con `CREATE TABLE IF NOT EXISTS` => reiniciar nunca borra datos;
  * la creación hace el chequeo de superposición *dentro* de la misma transacción,
    usando el predicado único `dominio.hay_superposicion`.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime

from . import dominio
from .dominio import (
    ESTADO_ACTIVA,
    ESTADO_CANCELADA,
    ESTADOS,
    ErrorValidacion,
    Reserva,
    RESERVA_NO_ENCONTRADA,
    SUPERPOSICION,
    YA_CANCELADA,
)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS reservas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    unidad      TEXT    NOT NULL,
    solicitante TEXT    NOT NULL,
    inicio      INTEGER NOT NULL,   -- epoch segundos UTC
    fin         INTEGER NOT NULL,   -- epoch segundos UTC
    estado      TEXT    NOT NULL CHECK (estado IN ('activa', 'cancelada')),
    creada_en   INTEGER NOT NULL,   -- epoch segundos UTC
    cancelada_en INTEGER             -- epoch segundos UTC, NULL si está activa
);
CREATE INDEX IF NOT EXISTS idx_reservas_unidad_estado
    ON reservas (unidad, estado, inicio);
"""


def _fila_a_reserva(fila: sqlite3.Row) -> Reserva:
    return Reserva(
        id=fila["id"],
        unidad=fila["unidad"],
        solicitante=fila["solicitante"],
        inicio=dominio.desde_epoch(fila["inicio"]),
        fin=dominio.desde_epoch(fila["fin"]),
        estado=fila["estado"],
        creada_en=dominio.desde_epoch(fila["creada_en"]),
        cancelada_en=dominio.desde_epoch(fila["cancelada_en"])
        if fila["cancelada_en"] is not None
        else None,
    )


class Repositorio:
    """Repositorio de reservas sobre un archivo SQLite."""

    def __init__(self, ruta: str | Path):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        # El servidor HTTP atiende en varios hilos: serializamos las escrituras.
        self._bloqueo = threading.RLock()
        self.crear_esquema()

    # ---------------------------------------------------------- conexión --
    @contextmanager
    def _conexion(self):
        con = sqlite3.connect(self.ruta, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def crear_esquema(self) -> None:
        with self._bloqueo, self._conexion() as con:
            con.executescript(ESQUEMA)

    # --------------------------------------------------------- operación --
    def crear_reserva(
        self,
        *,
        unidad: str,
        solicitante: str,
        inicio: datetime,
        fin: datetime,
        creada_en: datetime,
    ) -> Reserva:
        """Inserta una reserva si ninguna activa de la misma unidad se superpone.

        El chequeo y el INSERT ocurren en una única transacción `BEGIN IMMEDIATE`,
        de modo que dos escrituras simultáneas no pueden pasar ambas el filtro.
        """
        with self._bloqueo, self._conexion() as con:
            con.execute("BEGIN IMMEDIATE")
            for existente in self._activas_de_unidad(con, unidad):
                if dominio.hay_superposicion(inicio, fin, existente.inicio, existente.fin):
                    raise ErrorValidacion(
                        SUPERPOSICION,
                        f"La unidad {unidad} ya está reservada de "
                        f"{dominio.formato_local(existente.inicio)} a "
                        f"{dominio.formato_local(existente.fin)} "
                        f"(reserva #{existente.id}, {existente.solicitante}).",
                    )
            cursor = con.execute(
                """
                INSERT INTO reservas (unidad, solicitante, inicio, fin, estado, creada_en, cancelada_en)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    unidad,
                    solicitante,
                    dominio.hasta_epoch(inicio),
                    dominio.hasta_epoch(fin),
                    ESTADO_ACTIVA,
                    dominio.hasta_epoch(creada_en),
                ),
            )
            return Reserva(
                id=int(cursor.lastrowid),
                unidad=unidad,
                solicitante=solicitante,
                inicio=inicio,
                fin=fin,
                estado=ESTADO_ACTIVA,
                creada_en=creada_en,
            )

    # ---------------------------------------------------------- lecturas --
    def _activas_de_unidad(self, con: sqlite3.Connection, unidad: str) -> list[Reserva]:
        filas = con.execute(
            "SELECT * FROM reservas WHERE unidad = ? AND estado = ? ORDER BY inicio, id",
            (unidad, ESTADO_ACTIVA),
        ).fetchall()
        return [_fila_a_reserva(f) for f in filas]

    def activas_de_unidad(self, unidad: str) -> list[Reserva]:
        with self._conexion() as con:
            return self._activas_de_unidad(con, unidad)

    def listar(self, incluir_canceladas: bool = True) -> list[Reserva]:
        with self._conexion() as con:
            if incluir_canceladas:
                filas = con.execute(
                    "SELECT * FROM reservas ORDER BY inicio, id"
                ).fetchall()
            else:
                filas = con.execute(
                    "SELECT * FROM reservas WHERE estado = ? ORDER BY inicio, id",
                    (ESTADO_ACTIVA,),
                ).fetchall()
        return [_fila_a_reserva(f) for f in filas]

    def obtener(self, id_reserva: int) -> Reserva | None:
        with self._conexion() as con:
            fila = con.execute(
                "SELECT * FROM reservas WHERE id = ?", (id_reserva,)
            ).fetchone()
        return _fila_a_reserva(fila) if fila else None

    # ------------------------------------------------------- cancelación --
    def cancelar(self, id_reserva: int, momento: datetime) -> Reserva:
        """Cancela conservando la fila: id, unidad, solicitante e intervalo quedan."""
        with self._bloqueo, self._conexion() as con:
            con.execute("BEGIN IMMEDIATE")
            fila = con.execute(
                "SELECT * FROM reservas WHERE id = ?", (id_reserva,)
            ).fetchone()
            if fila is None:
                raise ErrorValidacion(
                    RESERVA_NO_ENCONTRADA, f"No existe la reserva #{id_reserva}."
                )
            reserva = _fila_a_reserva(fila)
            if reserva.estado != ESTADO_ACTIVA:
                raise ErrorValidacion(
                    YA_CANCELADA,
                    f"La reserva #{id_reserva} ya estaba cancelada "
                    f"el {dominio.formato_local(reserva.cancelada_en)}.",
                )
            con.execute(
                "UPDATE reservas SET estado = ?, cancelada_en = ? WHERE id = ?",
                (ESTADO_CANCELADA, dominio.hasta_epoch(momento), id_reserva),
            )
        return reserva.con_estado(ESTADO_CANCELADA, momento)

    # ------------------------------------------------------------- varios --
    def conteo_por_estado(self) -> dict[str, int]:
        with self._conexion() as con:
            filas = con.execute(
                "SELECT estado, COUNT(*) AS n FROM reservas GROUP BY estado"
            ).fetchall()
        conteo = {e: 0 for e in ESTADOS}
        conteo.update({f["estado"]: f["n"] for f in filas})
        return conteo
