"""Diagnóstico de la única corrección ocurrida durante el desarrollo.

Reproducible con:

    PYTHONPATH=src .venv/bin/python docs/evidencia/diagnostico_correccion.py

Contexto: la primera corrida de la suite dejó 81 pruebas en verde y una en
rojo, `test_unidades_distintas_pueden_reservar_el_mismo_intervalo`. La prueba
afirmaba que MIC-02 estaba *disponible* de 10:00 a 11:00 después de que la
propia prueba acabara de reservar MIC-02 en ese intervalo. El código estaba
bien: quien estaba mal era la afirmación. Este script muestra el diagnóstico.
"""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from reservas import dominio
from reservas.servicio import ServicioReservas

TZ = ZoneInfo(dominio.ZONA_HORARIA)
RELOJ = datetime(2030, 6, 10, 7, 0, tzinfo=TZ)  # reloj fijo de las pruebas
BASE = Path(__file__).resolve().parents[2]
RUTA_DB = BASE / "data" / "diagnostico.db"
RUTA_DB.unlink(missing_ok=True)  # arranca limpio

servicio = ServicioReservas.crear(RUTA_DB, BASE / "inventario.json", ahora=lambda: RELOJ)

servicio.reservar("MIC-01", "Ana Díaz", "2030-06-10T10:00", "2030-06-10T11:00")
servicio.reservar("MIC-02", "Bruno Sáez", "2030-06-10T10:00", "2030-06-10T11:00")

print("Reservas creadas por el diagnóstico:")
for r in servicio.listar():
    print(f"  #{r.id} {r.unidad} {r.solicitante} "
          f"{dominio.formato_local(r.inicio)[:16]} a {dominio.formato_local(r.fin)[:16]} "
          f"{r.estado}")

print()
print("Afirmación ORIGINAL (la que falló):")
print("  disponibilidad('MIC-02', 10:00, 11:00) es True")
real = servicio.disponibilidad("MIC-02", "2030-06-10T10:00", "2030-06-10T11:00")
print(f"  valor real: {real['disponible']}")
print("  -> la prueba era incorrecta: MIC-02 está ocupada por la reserva que")
print("     la MISMA prueba acababa de crear; el código se comporta bien.")
print()
print("Corrección aplicada (las afirmaciones que quedaron):")
for unidad, inicio, fin, comentario in [
    ("MIC-02", "2030-06-10T10:00", "2030-06-10T11:00", "ocupada por su propia reserva"),
    ("MIC-02", "2030-06-10T11:00", "2030-06-10T12:00", "límite consecutivo"),
    ("OSC-01", "2030-06-10T10:00", "2030-06-10T11:00", "otra unidad libre"),
]:
    r = servicio.disponibilidad(unidad, inicio, fin)
    print(f"  disponibilidad('{unidad}', {inicio[11:]}, {fin[11:]}) = "
          f"{r['disponible']}  # {comentario}")

RUTA_DB.unlink(missing_ok=True)
