"""Punto de entrada de la aplicación: `python -m reservas`.

Ejemplos:
    python -m reservas                          # http://127.0.0.1:8000
    python -m reservas --puerto 9000 --db data/otro.db
"""
from __future__ import annotations

import argparse
import sys

from .api import INVENTARIO_POR_DEFECTO, arrancar
from .dominio import ErrorValidacion
from .servicio import ServicioReservas

DB_POR_DEFECTO = "data/reservas.db"


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reservas",
        description="Sistema local de reservas de unidades de laboratorio.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Dirección a escuchar")
    parser.add_argument("--puerto", type=int, default=8000, help="Puerto TCP")
    parser.add_argument("--db", default=DB_POR_DEFECTO, help="Archivo SQLite de datos")
    parser.add_argument(
        "--inventario",
        default=str(INVENTARIO_POR_DEFECTO),
        help="Archivo JSON con el inventario precargado",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    try:
        servicio = ServicioReservas.crear(args.db, args.inventario)
    except ErrorValidacion as exc:
        print(f"Error al iniciar: [{exc.codigo}] {exc.mensaje}", file=sys.stderr)
        return 1

    servidor = arrancar(servicio, args.host, args.puerto)
    print(f"Reservas de laboratorio en http://{args.host}:{args.puerto}")
    print(f"  base de datos : {servicio.repositorio.ruta}")
    print(f"  inventario    : {args.inventario}")
    print(f"  unidades      : {', '.join(u.id for u in servicio.unidades())}")
    print("  Ctrl+C para detener (los datos persisten).")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nDetenido.")
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
