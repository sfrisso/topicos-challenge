"""Servicio de reservas: orquesta validación de dominio y persistencia.

El servicio es la única puerta de entrada de la aplicación (API HTTP, CLI o
pruebas). Aplica las validaciones en el orden definido en AGENTS.md §1.5 y
usa el mismo predicado de superposición para crear y para consultar.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import dominio
from .dominio import (
    ErrorValidacion,
    Reserva,
    Unidad,
    SOLICITUD_INVALIDA,
)
from .persistencia import Repositorio


def cargar_inventario(ruta: str | Path) -> dict[str, Unidad]:
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorValidacion(
            dominio.INVENTARIO_INVALIDO, f"No se encontró el inventario en {ruta}."
        )
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ErrorValidacion(
            dominio.INVENTARIO_INVALIDO,
            f"El inventario {ruta} no es JSON válido: {exc}",
        ) from None
    return dominio.validar_inventario(datos)


class ServicioReservas:
    """Aplicación de reservas sobre un repositorio SQLite."""

    def __init__(
        self,
        repositorio: Repositorio,
        inventario: dict[str, Unidad],
        ahora=None,
    ):
        self.repositorio = repositorio
        self.inventario = inventario
        # Reloj inyectable: permite tests determinísticos de "no en el pasado".
        self.ahora = ahora or dominio.ahora_utc

    # ------------------------------------------------------------ fábrica --
    @classmethod
    def crear(
        cls,
        ruta_db: str | Path = "data/reservas.db",
        ruta_inventario: str | Path = "inventario.json",
        ahora=None,
    ) -> "ServicioReservas":
        return cls(Repositorio(ruta_db), cargar_inventario(ruta_inventario), ahora=ahora)

    # --------------------------------------------------------- inventario --
    def unidades(self) -> list[Unidad]:
        return list(self.inventario.values())

    # ------------------------------------------------------- disponibilidad --
    def disponibilidad(self, unidad, inicio, fin) -> dict:
        """Consulta con las mismas reglas que la creación.

        No aplica la restricción de "no en el pasado": consultar un intervalo
        histórico es informativo y no crea datos.
        """
        u = dominio.validar_unidad(unidad, self.inventario)
        i, f = self._interpretar_intervalo(inicio, fin)
        existentes = self.repositorio.activas_de_unidad(u.id)
        conflictos = dominio.conflictos_activos(existentes, i, f)
        return {
            "unidad": u.a_dict(),
            "inicio": dominio.formato_local(i),
            "fin": dominio.formato_local(f),
            "disponible": not conflictos,
            "conflictos": [r.a_dict() for r in conflictos],
        }

    # ------------------------------------------------------------- crear --
    def reservar(self, unidad, solicitante, inicio, fin) -> Reserva:
        u = dominio.validar_unidad(unidad, self.inventario)          # 1
        s = dominio.validar_solicitante(solicitante)                  # 2
        i, f = self._interpretar_intervalo(inicio, fin)              # 3 y 4
        dominio.validar_no_pasado(i, self.ahora())                    # 5
        # 6: superposición, chequeada de forma atómica dentro del repositorio.
        return self.repositorio.crear_reserva(
            unidad=u.id, solicitante=s, inicio=i, fin=f, creada_en=self.ahora()
        )

    # ---------------------------------------------------------- cancelar --
    def cancelar(self, id_reserva) -> Reserva:
        if isinstance(id_reserva, bool) or not isinstance(id_reserva, int):
            raise ErrorValidacion(
                SOLICITUD_INVALIDA, f"Identificador de reserva inválido: {id_reserva!r}."
            )
        return self.repositorio.cancelar(id_reserva, self.ahora())

    # ------------------------------------------------------------- listar --
    def listar(self, incluir_canceladas: bool = True) -> list[Reserva]:
        return self.repositorio.listar(incluir_canceladas=incluir_canceladas)

    def obtener(self, id_reserva: int) -> Reserva | None:
        return self.repositorio.obtener(id_reserva)

    # ------------------------------------------------------------ interno --
    @staticmethod
    def _interpretar_intervalo(inicio, fin) -> tuple[datetime, datetime]:
        i = dominio.parsear_momento(inicio)                           # 3
        f = dominio.parsear_momento(fin)                              # 3
        dominio.validar_intervalo(i, f)                               # 4
        return i, f
