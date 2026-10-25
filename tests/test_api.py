"""Pruebas de punta a punta contra el servidor HTTP local y sus rutas estáticas."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest
from http.server import ThreadingHTTPServer

from reservas.api import crear_handler

from conftest import hhmm


@pytest.fixture
def servidor(ruta_db, reabrir):
    servicio = reabrir()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), crear_handler(servicio))
    hilo = threading.Thread(target=httpd.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
    hilo.join(timeout=5)


def _pedir(base: str, ruta: str, cuerpo=None, metodo=None):
    datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
    peticion = urllib.request.Request(
        base + ruta,
        data=datos,
        method=metodo or ("POST" if datos is not None else "GET"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=10) as respuesta:
            return respuesta.status, json.loads(respuesta.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # respuestas 4xx/5xx también son JSON
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _texto(base: str, ruta: str) -> tuple[int, str, str]:
    with urllib.request.urlopen(base + ruta, timeout=10) as respuesta:
        return (
            respuesta.status,
            respuesta.read().decode("utf-8"),
            respuesta.headers.get("Content-Type", ""),
        )


# ------------------------------------------------------------- inventario
def test_inventario_precargado(servidor):
    estado, datos = _pedir(servidor, "/api/inventario")
    assert estado == 200
    ids = [u["id"] for u in datos["unidades"]]
    assert ids == ["MIC-01", "MIC-02", "OSC-01", "MUL-01", "FUE-01"]
    assert datos["zona_horaria"] == "America/Argentina/Buenos_Aires"


# --------------------------------------------------------- disponibilidad
def test_disponibilidad_sobre_el_servidor(servidor):
    estado, datos = _pedir(
        servidor, "/api/disponibilidad?unidad=MIC-01&inicio=" + hhmm(10) + "&fin=" + hhmm(11)
    )
    assert estado == 200
    assert datos["disponible"] is True


def test_disponibilidad_con_unidad_desconocida(servidor):
    estado, datos = _pedir(
        servidor, "/api/disponibilidad?unidad=XYZ-99&inicio=" + hhmm(10) + "&fin=" + hhmm(11)
    )
    assert estado == 400
    assert datos["error"]["codigo"] == "UNIDAD_DESCONOCIDA"


# ----------------------------------------------------------------- crear
def test_crear_reserva_por_http(servidor):
    estado, datos = _pedir(
        servidor,
        "/api/reservas",
        {"unidad": "MIC-01", "solicitante": "Ana Díaz",
         "inicio": hhmm(10), "fin": hhmm(11)},
    )
    assert estado == 201
    assert datos["reserva"]["estado"] == "activa"
    assert datos["reserva"]["solicitante"] == "Ana Díaz"
    assert datos["reserva"]["inicio"].startswith("2030-06-10T10:00")


def test_superposicion_responde_409(servidor):
    _pedir(servidor, "/api/reservas",
           {"unidad": "MIC-01", "solicitante": "Ana Díaz",
            "inicio": hhmm(10), "fin": hhmm(11)})
    estado, datos = _pedir(servidor, "/api/reservas",
                           {"unidad": "MIC-01", "solicitante": "Carla Nuñez",
                            "inicio": hhmm(10, 30), "fin": hhmm(11, 30)})
    assert estado == 409
    assert datos["error"]["codigo"] == "SUPERPOSICION"
    assert "MIC-01" in datos["error"]["mensaje"]


def test_entrada_invalida_responde_400(servidor):
    estado, datos = _pedir(servidor, "/api/reservas",
                           {"unidad": "MIC-01", "solicitante": "   ",
                            "inicio": hhmm(10), "fin": hhmm(11)})
    assert estado == 400
    assert datos["error"]["codigo"] == "SOLICITANTE_VACIO"


def test_cuerpo_no_json_responde_400(servidor):
    peticion = urllib.request.Request(
        servidor + "/api/reservas", data=b"no soy json", method="POST",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(peticion, timeout=10)
    assert exc.value.code == 400
    assert json.loads(exc.value.read().decode())["error"]["codigo"] == "SOLICITUD_INVALIDA"


# -------------------------------------------------------------- cancelar
def test_cancelar_por_http_libera_el_horario(servidor):
    _, creado = _pedir(servidor, "/api/reservas",
                       {"unidad": "OSC-01", "solicitante": "Bruno Sáez",
                        "inicio": hhmm(14), "fin": hhmm(15)})
    id_reserva = creado["reserva"]["id"]

    estado, cancelada = _pedir(servidor, f"/api/reservas/{id_reserva}/cancelar", metodo="POST")
    assert estado == 200
    assert cancelada["reserva"]["estado"] == "cancelada"
    assert cancelada["reserva"]["id"] == id_reserva
    assert cancelada["reserva"]["solicitante"] == "Bruno Sáez"

    _, consulta = _pedir(
        servidor,
        "/api/disponibilidad?unidad=OSC-01&inicio=" + hhmm(14) + "&fin=" + hhmm(15),
    )
    assert consulta["disponible"] is True

    _, historial = _pedir(servidor, "/api/reservas")
    assert len(historial["reservas"]) == 1  # sigue en el historial


def test_cancelar_dos_veces_responde_409(servidor):
    _, creado = _pedir(servidor, "/api/reservas",
                       {"unidad": "MUL-01", "solicitante": "Carla Nuñez",
                        "inicio": hhmm(14), "fin": hhmm(15)})
    id_reserva = creado["reserva"]["id"]
    _pedir(servidor, f"/api/reservas/{id_reserva}/cancelar", metodo="POST")
    estado, datos = _pedir(servidor, f"/api/reservas/{id_reserva}/cancelar", metodo="POST")
    assert estado == 409
    assert datos["error"]["codigo"] == "YA_CANCELADA"


def test_cancelar_inexistente_responde_404(servidor):
    estado, datos = _pedir(servidor, "/api/reservas/4242/cancelar", metodo="POST")
    assert estado == 404
    assert datos["error"]["codigo"] == "RESERVA_NO_ENCONTRADA"


# --------------------------------------------------------------- errores
def test_ruta_desconocida_responde_404(servidor):
    estado, datos = _pedir(servidor, "/api/nada")
    assert estado == 404
    assert datos["error"]["codigo"] == "NO_ENCONTRADA"


def test_no_se_escapa_del_directorio_estatico(servidor):
    for ruta in ["/static/../pyproject.toml", "/static/%2e%2e/pyproject.toml",
                 "/static/../../etc/passwd"]:
        estado, datos = _pedir(servidor, ruta)
        assert estado == 404, ruta
        assert datos["error"]["codigo"] == "NO_ENCONTRADA"


# ---------------------------------------------------------- página y assets
def test_pagina_principal(servidor):
    estado, cuerpo, tipo = _texto(servidor, "/")
    assert estado == 200
    assert "text/html" in tipo
    assert "Reservas de unidades de laboratorio" in cuerpo


def test_javascript_y_css(servidor):
    for ruta, tipo_esperado in [("/static/app.js", "javascript"),
                                 ("/static/styles.css", "text/css")]:
        estado, cuerpo, tipo = _texto(servidor, ruta)
        assert estado == 200
        assert tipo_esperado in tipo
        assert len(cuerpo) > 0
