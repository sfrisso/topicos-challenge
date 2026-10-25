"""Servidor HTTP local (stdlib) + API JSON + página HTML estática.

Sin dependencias externas: `http.server`, `json` y `pathlib`.

Rutas:
    GET  /                          página de la aplicación (static/index.html)
    GET  /static/<archivo>          CSS/JS de la página
    GET  /api/inventario            unidades precargadas
    GET  /api/disponibilidad        ?unidad=&inicio=&fin=
    GET  /api/reservas              todas (activas y canceladas)
    POST /api/reservas              crear  {unidad, solicitante, inicio, fin}
    POST /api/reservas/<id>/cancelar
"""
from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .dominio import ErrorValidacion, RESERVA_NO_ENCONTRADA, SUPERPOSICION, YA_CANCELADA
from .servicio import ServicioReservas

RAIZ = Path(__file__).resolve().parents[2]          # raíz del repositorio
STATIC = RAIZ / "static"
INVENTARIO_POR_DEFECTO = RAIZ / "inventario.json"
_RUTA_CANCELAR = re.compile(r"^/api/reservas/(\d+)/cancelar$")

_ARCHIVOS_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
}


def _codigo_http(codigo_error: str) -> int:
    """409 para conflictos de estado, 400 para validación."""
    if codigo_error in (SUPERPOSICION, YA_CANCELADA):
        return 409
    return 400


def crear_handler(servicio: ServicioReservas):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ReservasLab/0.1"

        # ---------------------------------------------------------- utilidades
        def _json(self, datos, estado: int = 200) -> None:
            cuerpo = json.dumps(datos, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(estado)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cuerpo)

        def _error(self, exc: ErrorValidacion, estado: int | None = None) -> None:
            self._json({"error": exc.a_dict()}, estado or _codigo_http(exc.codigo))

        def _archivo(self, ruta: Path) -> None:
            ruta = ruta.resolve()
            if not ruta.is_file() or STATIC not in ruta.parents:
                self._json(
                    {"error": {"codigo": "NO_ENCONTRADA", "mensaje": "Recurso inexistente"}},
                    404,
                )
                return
            cuerpo = ruta.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type", _ARCHIVOS_MIME.get(ruta.suffix, "application/octet-stream")
            )
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def _cuerpo_json(self) -> dict:
            largo = int(self.headers.get("Content-Length") or 0)
            if largo <= 0:
                raise ErrorValidacion(
                    "SOLICITUD_INVALIDA", "Falta el cuerpo JSON de la solicitud."
                )
            try:
                datos = json.loads(self.rfile.read(largo).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise ErrorValidacion("SOLICITUD_INVALIDA", "El cuerpo no es JSON válido.") from None
            if not isinstance(datos, dict):
                raise ErrorValidacion(
                    "SOLICITUD_INVALIDA", "Se esperaba un objeto JSON."
                )
            return datos

        # ------------------------------------------------------------ GET
        def do_GET(self):  # noqa: N802 (API de http.server)
            url = urlparse(self.path)
            try:
                if url.path in ("/", "/index.html"):
                    self._archivo(STATIC / "index.html")
                    return
                if url.path.startswith("/static/"):
                    self._archivo(STATIC / url.path.removeprefix("/static/"))
                    return
                consulta = parse_qs(url.query)

                def parametro(*nombres: str) -> str | None:
                    for nombre in nombres:
                        if nombre in consulta and consulta[nombre]:
                            return consulta[nombre][0]
                    return None

                if url.path == "/api/inventario":
                    self._json(
                        {
                            "zona_horaria": "America/Argentina/Buenos_Aires",
                            "formato": "AAAA-MM-DDTHH:MM",
                            "unidades": [u.a_dict() for u in servicio.unidades()],
                        }
                    )
                elif url.path == "/api/disponibilidad":
                    self._json(
                        servicio.disponibilidad(
                            parametro("unidad", "unit"),
                            parametro("inicio", "start"),
                            parametro("fin", "end"),
                        )
                    )
                elif url.path == "/api/reservas":
                    incluir = parametro("incl_canceladas") != "no"
                    reservas = servicio.listar(incluir_canceladas=incluir)
                    self._json({"reservas": [r.a_dict() for r in reservas]})
                else:
                    self._json(
                        {"error": {"codigo": "NO_ENCONTRADA", "mensaje": "Ruta desconocida"}},
                        404,
                    )
            except ErrorValidacion as exc:
                self._error(exc)
            except BrokenPipeError:
                pass

        # ----------------------------------------------------------- POST
        def do_POST(self):  # noqa: N802
            url = urlparse(self.path)
            try:
                if url.path == "/api/reservas":
                    datos = self._cuerpo_json()
                    reserva = servicio.reservar(
                        datos.get("unidad"),
                        datos.get("solicitante"),
                        datos.get("inicio"),
                        datos.get("fin"),
                    )
                    self._json({"reserva": reserva.a_dict()}, 201)
                    return
                coincidencia = _RUTA_CANCELAR.match(url.path)
                if coincidencia:
                    reserva = servicio.cancelar(int(coincidencia.group(1)))
                    self._json({"reserva": reserva.a_dict()})
                    return
                self._json(
                    {"error": {"codigo": "NO_ENCONTRADA", "mensaje": "Ruta desconocida"}},
                    404,
                )
            except ErrorValidacion as exc:
                if exc.codigo == RESERVA_NO_ENCONTRADA:
                    self._error(exc, 404)
                else:
                    self._error(exc)
            except BrokenPipeError:
                pass

        def log_message(self, formato, *args):
            sys.stderr.write("[api] %s - %s\n" % (self.address_string(), formato % args))

    return Handler


def arrancar(servicio: ServicioReservas, host: str = "127.0.0.1", puerto: int = 8000):
    servidor = ThreadingHTTPServer((host, puerto), crear_handler(servicio))
    return servidor
