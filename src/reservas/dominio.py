"""Reglas de dominio del sistema de reservas.

Módulo puro: no accede a archivos, base de datos ni interfaz. Es el único lugar
donde vive el predicado de superposición (`hay_superposicion`), que usan tanto la
creación como la consulta de disponibilidad.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# --------------------------------------------------------------------------
# Zona horaria y formatos (declarados también en el README)
# --------------------------------------------------------------------------
ZONA_HORARIA = "America/Argentina/Buenos_Aires"
TZ = ZoneInfo(ZONA_HORARIA)
FORMATO_ENTRADA = "AAAA-MM-DDTHH:MM (ISO 8601, con segundos opcionales)"

_RE_MOMENTO = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")

# Estados posibles de una reserva.
ESTADO_ACTIVA = "activa"
ESTADO_CANCELADA = "cancelada"
ESTADOS = (ESTADO_ACTIVA, ESTADO_CANCELADA)

# --------------------------------------------------------------------------
# Códigos de error de negocio (se usan tal cual como códigos de la API)
# --------------------------------------------------------------------------
UNIDAD_DESCONOCIDA = "UNIDAD_DESCONOCIDA"
SOLICITANTE_VACIO = "SOLICITANTE_VACIO"
FECHA_INVALIDA = "FECHA_INVALIDA"
INTERVALO_INVALIDO = "INTERVALO_INVALIDO"
RESERVA_EN_PASADO = "RESERVA_EN_PASADO"
SUPERPOSICION = "SUPERPOSICION"
RESERVA_NO_ENCONTRADA = "RESERVA_NO_ENCONTRADA"
YA_CANCELADA = "YA_CANCELADA"
INVENTARIO_INVALIDO = "INVENTARIO_INVALIDO"
SOLICITUD_INVALIDA = "SOLICITUD_INVALIDA"


class ErrorValidacion(Exception):
    """Error de negocio con código traducible a la capa HTTP."""

    def __init__(self, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje

    def a_dict(self) -> dict:
        return {"codigo": self.codigo, "mensaje": self.mensaje}


# --------------------------------------------------------------------------
# Modelo
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Unidad:
    id: str
    equipo: str

    def a_dict(self) -> dict:
        return {"id": self.id, "equipo": self.equipo}


@dataclass(frozen=True)
class Reserva:
    id: int
    unidad: str
    solicitante: str
    inicio: datetime  # instante UTC consciente de zona horaria
    fin: datetime
    estado: str
    creada_en: datetime
    cancelada_en: datetime | None = None

    @property
    def activa(self) -> bool:
        return self.estado == ESTADO_ACTIVA

    def a_dict(self) -> dict:
        """Representación JSON: fechas en zona horaria declarada, con offset."""
        return {
            "id": self.id,
            "unidad": self.unidad,
            "solicitante": self.solicitante,
            "inicio": formato_local(self.inicio),
            "fin": formato_local(self.fin),
            "estado": self.estado,
            "creada_en": formato_local(self.creada_en),
            "cancelada_en": formato_local(self.cancelada_en) if self.cancelada_en else None,
        }

    def con_estado(self, estado: str, momento: datetime | None = None) -> "Reserva":
        return replace(self, estado=estado, cancelada_en=momento)


# --------------------------------------------------------------------------
# Conversión de fechas
# --------------------------------------------------------------------------
def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def local(dt: datetime) -> datetime:
    """Normaliza un instante a la zona horaria declarada."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).astimezone(TZ)
    return dt.astimezone(TZ)


def formato_local(dt: datetime) -> str:
    return local(dt).isoformat(timespec="seconds")


def desde_epoch(segundos: int) -> datetime:
    return datetime.fromtimestamp(int(segundos), tz=timezone.utc)


def hasta_epoch(dt: datetime) -> int:
    return int(dt.timestamp())


def parsear_momento(texto) -> datetime:
    """Interpreta una fecha/hora ISO 8601 como instante UTC.

    Sin offset se asume la zona horaria declarada (ZONA_HORARIA).
    """
    if not isinstance(texto, str) or not texto.strip():
        raise ErrorValidacion(
            FECHA_INVALIDA,
            f"Fecha y hora vacías o ausentes. Formato esperado: {FORMATO_ENTRADA}.",
        )
    bruto = texto.strip()
    if not _RE_MOMENTO.match(bruto):
        raise ErrorValidacion(
            FECHA_INVALIDA,
            f"'{bruto}' no incluye fecha y hora. Formato esperado: {FORMATO_ENTRADA}.",
        )
    try:
        momento = datetime.fromisoformat(bruto)
    except ValueError:
        raise ErrorValidacion(
            FECHA_INVALIDA,
            f"'{bruto}' no es una fecha/hora válida. Formato esperado: {FORMATO_ENTRADA}.",
        ) from None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=TZ)
    return momento.astimezone(timezone.utc)


# --------------------------------------------------------------------------
# Validaciones
# --------------------------------------------------------------------------
def validar_unidad(unidad, inventario: dict[str, Unidad]) -> Unidad:
    if not isinstance(unidad, str) or not unidad.strip():
        raise ErrorValidacion(UNIDAD_DESCONOCIDA, "Falta el identificador de la unidad.")
    clave = unidad.strip().upper()
    if clave not in inventario:
        conocidas = ", ".join(sorted(inventario))
        raise ErrorValidacion(
            UNIDAD_DESCONOCIDA,
            f"Unidad desconocida '{unidad}'. Unidades disponibles: {conocidas}.",
        )
    return inventario[clave]


def validar_solicitante(solicitante) -> str:
    if not isinstance(solicitante, str) or not solicitante.strip():
        raise ErrorValidacion(
            SOLICITANTE_VACIO,
            "El solicitante no puede estar vacío ni ser solo espacios.",
        )
    return solicitante.strip()


def validar_intervalo(inicio: datetime, fin: datetime) -> None:
    if not inicio < fin:
        raise ErrorValidacion(
            INTERVALO_INVALIDO,
            "El inicio debe ser estrictamente anterior al fin "
            f"(inicio {formato_local(inicio)}, fin {formato_local(fin)}).",
        )


def validar_no_pasado(inicio: datetime, momento_actual: datetime) -> None:
    """Las reservas no pueden comenzar en el pasado (minuto a minuto)."""
    referencia = momento_actual.replace(second=0, microsecond=0)
    if inicio < referencia:
        raise ErrorValidacion(
            RESERVA_EN_PASADO,
            f"La reserva comienza en el pasado ({formato_local(inicio)}). "
            f"Ahora son {formato_local(momento_actual)}.",
        )


def validar_inventario(datos) -> dict[str, Unidad]:
    """Valida la estructura del inventario precargado y lo indexa por id."""
    if not isinstance(datos, dict) or "unidades" not in datos:
        raise ErrorValidacion(
            INVENTARIO_INVALIDO, "El inventario debe ser un objeto con la clave 'unidades'."
        )
    filas = datos["unidades"]
    if not isinstance(filas, list) or not filas:
        raise ErrorValidacion(
            INVENTARIO_INVALIDO, "El inventario debe contener al menos una unidad."
        )
    inventario: dict[str, Unidad] = {}
    for fila in filas:
        if not isinstance(fila, dict) or not str(fila.get("id", "")).strip():
            raise ErrorValidacion(
                INVENTARIO_INVALIDO, f"Entrada de inventario sin id: {fila!r}"
            )
        identificador = str(fila["id"]).strip().upper()
        equipo = str(fila.get("equipo", "")).strip() or "Sin descripción"
        if identificador in inventario:
            raise ErrorValidacion(
                INVENTARIO_INVALIDO, f"Id de unidad repetido en el inventario: {identificador}"
            )
        inventario[identificador] = Unidad(id=identificador, equipo=equipo)
    return inventario


# --------------------------------------------------------------------------
# Predicado único de superposición (lo usan creación y disponibilidad)
# --------------------------------------------------------------------------
def hay_superposicion(a_inicio: datetime, a_fin: datetime,
                      b_inicio: datetime, b_fin: datetime) -> bool:
    """Intervalos semiabiertos [inicio, fin).

    Dos intervalos se pisan si cada uno empieza antes de que termine el otro.
    Con `a_fin == b_inicio` (límites consecutivos) no hay superposición.
    """
    return a_inicio < b_fin and b_inicio < a_fin


def conflictos_activos(
    reservas: list[Reserva], inicio: datetime, fin: datetime
) -> list[Reserva]:
    """Reservas activas de la lista que se superponen con [inicio, fin)."""
    return [
        r
        for r in reservas
        if r.activa and hay_superposicion(inicio, fin, r.inicio, r.fin)
    ]
