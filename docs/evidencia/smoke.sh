#!/usr/bin/env bash
# Evidencia reproducible: API HTTP local + persistencia entre reinicios.
#
#   bash docs/evidencia/smoke.sh
#
# Usa su propio archivo de datos (data/evidencia-smoke.db) y lo borra al
# empezar, así que puede correrse las veces que haga falta sin afectar las
# reservas reales de data/reservas.db. Requiere el venv descrito en el README.
set -u

cd "$(dirname "$0")/../.." || exit 1
PY=${PY:-.venv/bin/python}
DB=data/evidencia-smoke.db
PUERTO=${PUERTO:-8130}
BASE="http://127.0.0.1:$PUERTO"
LOG=/tmp/opencode/smoke-servidor.log

limpiar() {
  [ -n "${PID:-}" ] && kill "$PID" 2>/dev/null
}
trap limpiar EXIT

echo "### 1. Arranque (base de datos propia de la evidencia)"
rm -f "$DB"
PYTHONPATH=src "$PY" -m reservas --puerto "$PUERTO" --db "$DB" >"$LOG" 2>&1 &
PID=$!
sleep 2

pedir() {  # pedir METODO RUTA [CUERPO]
  local metodo=$1 ruta=$2 cuerpo=${3:-}
  if [ -n "$cuerpo" ]; then
    printf '$ curl -X %s %s -d %s\n' "$metodo" "$ruta" "$cuerpo"
    curl -s -w '\n[HTTP %{http_code}]\n' -X "$metodo" "$BASE$ruta" \
      -H 'Content-Type: application/json' -d "$cuerpo"
  else
    printf '$ curl -X %s %s\n' "$metodo" "$ruta"
    curl -s -w '\n[HTTP %{http_code}]\n' -X "$metodo" "$BASE$ruta"
  fi
  echo
}

echo "### 2. Inventario precargado"
pedir GET /api/inventario

echo "### 3. Disponibilidad inicial (MIC-01 10:00-11:00)"
pedir GET "/api/disponibilidad?unidad=MIC-01&inicio=2030-06-10T10:00&fin=2030-06-10T11:00"

echo "### 4. Crear reserva válida (espera HTTP 201)"
pedir POST /api/reservas '{"unidad":"MIC-01","solicitante":"Ana Díaz","inicio":"2030-06-10T10:00","fin":"2030-06-10T11:00"}'

echo "### 5. Superposición 10:30-11:30 (espera HTTP 409 SUPERPOSICION)"
pedir POST /api/reservas '{"unidad":"MIC-01","solicitante":"Carla Nuñez","inicio":"2030-06-10T10:30","fin":"2030-06-10T11:30"}'

echo "### 6. Límite consecutivo 11:00-12:00 (espera HTTP 201)"
pedir POST /api/reservas '{"unidad":"MIC-01","solicitante":"Bruno Sáez","inicio":"2030-06-10T11:00","fin":"2030-06-10T12:00"}'

echo "### 7. MIC-02 en el mismo intervalo de MIC-01 (espera HTTP 201)"
pedir POST /api/reservas '{"unidad":"MIC-02","solicitante":"Carla Nuñez","inicio":"2030-06-10T10:00","fin":"2030-06-10T11:00"}'

echo "### 8. Solicitante vacío (espera HTTP 400 SOLICITANTE_VACIO)"
pedir POST /api/reservas '{"unidad":"MUL-01","solicitante":"   ","inicio":"2030-06-10T13:00","fin":"2030-06-10T14:00"}'

echo "### 9. Cancelar la reserva #1 (espera HTTP 200, conserva id y datos)"
pedir POST /api/reservas/1/cancelar

echo "### 10. Disponibilidad tras cancelar: el intervalo vuelve a estar libre"
pedir GET "/api/disponibilidad?unidad=MIC-01&inicio=2030-06-10T10:00&fin=2030-06-10T11:00"

echo "### 11. Historial antes de detener el proceso"
pedir GET /api/reservas

echo "### 12. Detener el proceso (kill $PID) y volver a arrancar con el mismo archivo"
kill "$PID"
wait "$PID" 2>/dev/null
PYTHONPATH=src "$PY" -m reservas --puerto "$PUERTO" --db "$DB" >"$LOG" 2>&1 &
PID=$!
sleep 2

echo "### 13. Historial tras el reinicio: siguen activas Y canceladas"
pedir GET /api/reservas

echo "### 14. Contenido del archivo SQLite en disco"
"$PY" - "$DB" <<'EOF'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
for fila in con.execute("select id, unidad, solicitante, estado from reservas order by id"):
    print(fila)
EOF

echo "### Listo: proceso $PID queda detenido en la salida de este script."
