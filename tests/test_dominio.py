"""Reglas de dominio: fechas, validaciones y el predicado de superposición."""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from reservas import dominio
from reservas.dominio import ErrorValidacion, hay_superposicion

from conftest import RELOJ, hhmm


def momento(hora: int, minuto: int = 0) -> datetime:
    return datetime.fromisoformat(hhmm(hora, minuto)).replace(
        tzinfo=dominio.TZ
    ).astimezone(timezone.utc)


# ------------------------------------------------------------ fechas
def test_parsea_iso_sin_offset_como_hora_local():
    assert dominio.parsear_momento(hhmm(10, 30)) == momento(10, 30)


def test_parsea_iso_con_offset():
    assert dominio.parsear_momento("2030-06-10T10:30:00-03:00") == momento(10, 30)


@pytest.mark.parametrize(
    "bruto",
    ["", "   ", None, 42, "mañana", "10/06/2030 10:00", "2030-06-10", "2030-13-45T10:00"],
)
def test_rechaza_fechas_invalidas(bruto):
    with pytest.raises(ErrorValidacion) as exc:
        dominio.parsear_momento(bruto)
    assert exc.value.codigo == dominio.FECHA_INVALIDA


# ------------------------------------------------------- solicitante / unidad
@pytest.mark.parametrize("bruto", ["", "   ", None, "\t\n"])
def test_solicitante_vacio_rechazado(bruto):
    with pytest.raises(ErrorValidacion) as exc:
        dominio.validar_solicitante(bruto)
    assert exc.value.codigo == dominio.SOLICITANTE_VACIO


def test_solicitante_se_apaña():
    assert dominio.validar_solicitante("  Ana Díaz  ") == "Ana Díaz"


def test_unidad_desconocida_lista_las_conocidas():
    inventario = dominio.validar_inventario(
        {"unidades": [{"id": "MIC-01", "equipo": "Microscopio digital"}]}
    )
    with pytest.raises(ErrorValidacion) as exc:
        dominio.validar_unidad("MIC-99", inventario)
    assert exc.value.codigo == dominio.UNIDAD_DESCONOCIDA
    assert "MIC-01" in exc.value.mensaje  # el mensaje lista las conocidas


def test_unidad_se_normaliza_a_mayusculas():
    inventario = dominio.validar_inventario(
        {"unidades": [{"id": "mic-01", "equipo": "Microscopio digital"}]}
    )
    assert dominio.validar_unidad(" mic-01 ", inventario).id == "MIC-01"


def test_inventario_rechaza_ids_repetidos():
    with pytest.raises(ErrorValidacion) as exc:
        dominio.validar_inventario(
            {"unidades": [{"id": "MIC-01"}, {"id": "MIC-01"}]}
        )
    assert exc.value.codigo == dominio.INVENTARIO_INVALIDO


# ------------------------------------------------------------- intervalo
def test_intervalo_requiere_inicio_estrictamente_menor():
    for inicio, fin in [(hhmm(10), hhmm(10)), (hhmm(11), hhmm(10))]:
        with pytest.raises(ErrorValidacion) as exc:
            dominio.validar_intervalo(
                dominio.parsear_momento(inicio), dominio.parsear_momento(fin)
            )
        assert exc.value.codigo == dominio.INTERVALO_INVALIDO


def test_intervalo_desde_el_reloj_en_adelante_es_valido():
    dominio.validar_intervalo(RELOJ, RELOJ + timedelta(hours=1))


def test_no_en_pasado_rechaza_inicio_anterior_al_reloj():
    with pytest.raises(ErrorValidacion) as exc:
        dominio.validar_no_pasado(momento(6), RELOJ)  # 06:00 < 07:00 (reloj)
    assert exc.value.codigo == dominio.RESERVA_EN_PASADO


def test_no_en_pasado_acepta_el_mismo_minuto():
    dominio.validar_no_pasado(RELOJ, RELOJ)  # mismo minuto => permitido


# ------------------------------------------- predicado único de superposición
@pytest.mark.parametrize(
    "hi,mi,hf,mf,esperado,descripcion",
    [
        (10, 30, 11, 30, True, "rebasan por ambos lados"),
        (10, 45, 11, 0, True, "contenido estrictamente dentro"),
        (10, 0, 11, 0, True, "intervalos idénticos"),
        (11, 0, 12, 0, False, "límite consecutivo: fin == inicio"),
        (9, 0, 10, 0, False, "límite consecutivo anterior: fin == inicio"),
        (9, 30, 10, 30, True, "rebasan por el inicio"),
        (9, 0, 12, 0, True, "contiene por completo"),
        (12, 0, 13, 0, False, "posterior sin contacto"),
    ],
)
def test_predicado_de_superposicion(hi, mi, hf, mf, esperado, descripcion):
    base = (momento(10), momento(11))
    otro = (momento(hi, mi), momento(hf, mf))
    assert hay_superposicion(*base, *otro) is esperado, descripcion


def test_el_predicado_vive_en_un_solo_lugar():
    """Guarda de AGENTS.md §1.3: creación y disponibilidad comparten la función."""
    import reservas.persistencia as persistencia
    import reservas.servicio as servicio

    fuente_creacion = inspect.getsource(persistencia)
    fuente_disponibilidad = inspect.getsource(servicio.ServicioReservas.disponibilidad)
    fuente_dominio = inspect.getsource(dominio)

    assert "hay_superposicion" in fuente_creacion          # creación
    assert "conflictos_activos" in fuente_disponibilidad    # delega en dominio
    assert "conflictos_activos" in fuente_dominio
    assert "hay_superposicion" in fuente_dominio
