"""Pruebas centrales de funcionamiento: las reglas de la consigna.

Cubre los seis puntos exigidos en "Verificaciones requeridas":
  1. creación válida
  2. rechazo de superposición
  3. límites consecutivos
  4. unidades distintas en simultáneo
  5. entradas inválidas
  6. cancelación que conserva el registro y libera el horario
"""
from __future__ import annotations

import pytest

from reservas import dominio
from reservas.dominio import ErrorValidacion

from conftest import hhmm

UNIDAD = "MIC-01"


def reservar(servicio, inicio=hhmm(10), fin=hhmm(11), solicitante="Ana Díaz",
             unidad=UNIDAD):
    return servicio.reservar(unidad, solicitante, inicio, fin)


# ------------------------------------------------------- 1. creación válida
def test_creacion_valida(servicio):
    reserva = reservar(servicio)

    assert reserva.id > 0
    assert reserva.unidad == UNIDAD
    assert reserva.solicitante == "Ana Díaz"
    assert reserva.estado == dominio.ESTADO_ACTIVA
    assert reserva.activa is True
    assert reserva.cancelada_en is None
    assert reserva.inicio < reserva.fin

    guardadas = servicio.listar()
    assert [r.id for r in guardadas] == [reserva.id]


def test_cada_creacion_recibe_identificador_propio(servicio):
    primera = reservar(servicio, solicitante="Ana Díaz")
    segunda = reservar(servicio, hhmm(14), hhmm(15), solicitante="Bruno Sáez")
    assert segunda.id != primera.id


# -------------------------------------------------- 2. rechazo de superposición
@pytest.mark.parametrize(
    "inicio,fin",
    [
        (hhmm(10, 30), hhmm(11, 30)),  # rebasa por ambos lados (ejemplo 10:30–11:30)
        (hhmm(10), hhmm(11)),          # ventana idéntica
        (hhmm(9, 30), hhmm(10, 30)),   # rebasa por el inicio
        (hhmm(10, 15), hhmm(10, 45)),  # contenida por completo
        (hhmm(9), hhmm(12)),           # contiene por completo
    ],
)
def test_rechaza_superposicion_de_reservas_activas(servicio, inicio, fin):
    creada = reservar(servicio)  # 10:00–11:00 en MIC-01

    with pytest.raises(ErrorValidacion) as exc:
        reservar(servicio, inicio, fin, solicitante="Carla Nuñez")

    assert exc.value.codigo == dominio.SUPERPOSICION
    assert str(creada.id) in exc.value.mensaje  # el error señala a la reserva que bloquea
    assert len(servicio.listar()) == 1          # no quedó registro del intento


def test_no_cambia_el_inventario_de_activas_por_un_rechazo(servicio):
    reservar(servicio)
    with pytest.raises(ErrorValidacion):
        reservar(servicio, hhmm(10, 30), hhmm(11, 30))
    assert servicio.repositorio.conteo_por_estado() == {"activa": 1, "cancelada": 0}


# -------------------------------------------------- 3. límites consecutivos
def test_acepta_limite_consecutivo_posterior(servicio):
    """Ejemplo del enunciado: con 10:00–11:00, permitir 11:00–12:00."""
    reservar(servicio)                                   # 10:00–11:00
    siguiente = reservar(servicio, hhmm(11), hhmm(12), solicitante="Carla Nuñez")

    assert siguiente.estado == dominio.ESTADO_ACTIVA
    assert len(servicio.listar()) == 2


def test_acepta_limite_consecutivo_anterior(servicio):
    reservar(servicio, hhmm(10), hhmm(11))
    anterior = reservar(servicio, hhmm(9), hhmm(10), solicitante="Bruno Sáez")
    assert anterior.estado == dominio.ESTADO_ACTIVA


def test_tres_turnos_consecutivos_en_la_misma_unidad(servicio):
    reservar(servicio, hhmm(8), hhmm(9), solicitante="Ana Díaz")
    reservar(servicio, hhmm(9), hhmm(10), solicitante="Bruno Sáez")
    reservar(servicio, hhmm(10), hhmm(11), solicitante="Carla Nuñez")
    assert len(servicio.listar(incluir_canceladas=False)) == 3


# ------------------------------------------- 4. unidades distintas en simultáneo
def test_unidades_distintas_pueden_reservar_el_mismo_intervalo(servicio):
    """Ejemplo del enunciado: MIC-02 se reserva 10:00–11:00 con MIC-01 ocupado."""
    reservar(servicio)                                             # MIC-01 ocupado
    segundo = reservar(servicio, unidad="MIC-02", solicitante="Bruno Sáez")
    assert segundo.unidad == "MIC-02" and segundo.estado == "activa"

    # La reserva de MIC-02 se aceptó pese a MIC-01 ocupado (ejemplo de la consigna)
    assert len(servicio.listar()) == 2

    # La disponibilidad se calcula por unidad, no global.
    assert servicio.disponibilidad("MIC-01", hhmm(10), hhmm(11))["disponible"] is False
    assert servicio.disponibilidad("MIC-02", hhmm(10), hhmm(11))["disponible"] is False
    assert servicio.disponibilidad("MIC-02", hhmm(11), hhmm(12))["disponible"] is True
    assert servicio.disponibilidad("OSC-01", hhmm(10), hhmm(11))["disponible"] is True


# ------------------------------------------------------------ 5. entradas inválidas
@pytest.mark.parametrize(
    "unidad,solicitante,inicio,fin,codigo_esperado",
    [
        ("MIC-99", "Ana Díaz", hhmm(10), hhmm(11), dominio.UNIDAD_DESCONOCIDA),
        ("", "Ana Díaz", hhmm(10), hhmm(11), dominio.UNIDAD_DESCONOCIDA),
        ("MIC-01", "", hhmm(10), hhmm(11), dominio.SOLICITANTE_VACIO),
        ("MIC-01", "   ", hhmm(10), hhmm(11), dominio.SOLICITANTE_VACIO),
        ("MIC-01", "Ana Díaz", "no-es-fecha", hhmm(11), dominio.FECHA_INVALIDA),
        ("MIC-01", "Ana Díaz", hhmm(10), "2030-06-10", dominio.FECHA_INVALIDA),
        ("MIC-01", "Ana Díaz", hhmm(11), hhmm(10), dominio.INTERVALO_INVALIDO),
        ("MIC-01", "Ana Díaz", hhmm(10), hhmm(10), dominio.INTERVALO_INVALIDO),
        ("MIC-01", "Ana Díaz", hhmm(6), hhmm(7), dominio.RESERVA_EN_PASADO),
        (None, None, None, None, dominio.UNIDAD_DESCONOCIDA),
    ],
)
def test_entradas_invalidas(servicio, unidad, solicitante, inicio, fin, codigo_esperado):
    with pytest.raises(ErrorValidacion) as exc:
        reservar(servicio, inicio, fin, solicitante=solicitante, unidad=unidad)
    assert exc.value.codigo == codigo_esperado
    assert servicio.listar() == []  # ninguna entrada inválida deja registro


def test_orden_de_validaciones_unidad_antes_que_solicitante(servicio):
    with pytest.raises(ErrorValidacion) as exc:
        reservar(servicio, solicitante="   ", unidad="MIC-99")
    assert exc.value.codigo == dominio.UNIDAD_DESCONOCIDA


def test_orden_de_validaciones_fecha_antes_que_superposicion(servicio):
    reservar(servicio)
    with pytest.raises(ErrorValidacion) as exc:
        reservar(servicio, "mal", hhmm(11), solicitante="Carla Nuñez")
    assert exc.value.codigo == dominio.FECHA_INVALIDA


# ----------------------------------------- 6. cancelación: conserva y libera
def test_cancelacion_conserva_el_registro_y_libera_el_horario(servicio):
    creada = reservar(servicio, solicitante="Ana Díaz")

    cancelada = servicio.cancelar(creada.id)

    # Conserva identificador y todos los datos originales.
    assert cancelada.id == creada.id
    assert cancelada.unidad == creada.unidad
    assert cancelada.solicitante == creada.solicitante
    assert cancelada.inicio == creada.inicio
    assert cancelada.fin == creada.fin
    assert cancelada.estado == dominio.ESTADO_CANCELADA
    assert cancelada.activa is False
    assert cancelada.cancelada_en is not None

    # Sigue estando en el historial.
    historial = servicio.listar()
    assert [r.id for r in historial] == [creada.id]
    assert historial[0].estado == dominio.ESTADO_CANCELADA

    # Y el intervalo quedó libre: se puede volver a reservar y consultarlo.
    assert servicio.disponibilidad(UNIDAD, hhmm(10), hhmm(11))["disponible"] is True
    repetida = reservar(servicio, solicitante="Carla Nuñez")
    assert repetida.id != creada.id
    assert servicio.repositorio.conteo_por_estado() == {"activa": 1, "cancelada": 1}


def test_cancelada_no_bloquea_pero_activa_si(servicio):
    reserva = reservar(servicio)
    assert servicio.disponibilidad(UNIDAD, hhmm(10, 30), hhmm(11, 30))["disponible"] is False
    servicio.cancelar(reserva.id)
    assert servicio.disponibilidad(UNIDAD, hhmm(10, 30), hhmm(11, 30))["disponible"] is True


def test_cancelar_dos_veces_es_error(servicio):
    reserva = reservar(servicio)
    servicio.cancelar(reserva.id)
    with pytest.raises(ErrorValidacion) as exc:
        servicio.cancelar(reserva.id)
    assert exc.value.codigo == dominio.YA_CANCELADA


def test_cancelar_inexistente_es_error(servicio):
    with pytest.raises(ErrorValidacion) as exc:
        servicio.cancelar(999)
    assert exc.value.codigo == dominio.RESERVA_NO_ENCONTRADA


# ------------------------------------------- disponibilidad con las mismas reglas
def test_disponibilidad_devuelve_el_conflicto(servicio):
    bloqueo = reservar(servicio)

    consulta = servicio.disponibilidad(UNIDAD, hhmm(10, 30), hhmm(11, 30))

    assert consulta["disponible"] is False
    assert len(consulta["conflictos"]) == 1
    assert consulta["conflictos"][0]["id"] == bloqueo.id
    assert consulta["unidad"]["id"] == UNIDAD


def test_disponibilidad_permite_limites_consecutivos(servicio):
    reservar(servicio, hhmm(10), hhmm(11))
    assert servicio.disponibilidad(UNIDAD, hhmm(11), hhmm(12))["disponible"] is True
    assert servicio.disponibilidad(UNIDAD, hhmm(9), hhmm(10))["disponible"] is True


def test_disponibilidad_valida_como_la_creacion(servicio):
    casos = [
        ("MIC-01", "mal", hhmm(11), dominio.FECHA_INVALIDA),
        ("MIC-01", hhmm(11), hhmm(10), dominio.INTERVALO_INVALIDO),
        ("MIC-99", hhmm(10), hhmm(11), dominio.UNIDAD_DESCONOCIDA),
    ]
    for unidad, inicio, fin, codigo in casos:
        with pytest.raises(ErrorValidacion) as exc:
            servicio.disponibilidad(unidad, inicio, fin)
        assert exc.value.codigo == codigo


def test_disponibilidad_no_pide_solicitante(servicio):
    """La consulta no recibe solicitante: ese campo sólo aplica a la creación."""
    consulta = servicio.disponibilidad(UNIDAD, hhmm(10), hhmm(11))
    assert consulta["disponible"] is True
    assert "solicitante" not in consulta
