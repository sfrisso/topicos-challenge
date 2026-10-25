/* Frontend de la aplicación de reservas.
   Sin dependencias externas: fetch + DOM. Los horarios se envían como
   texto ISO sin offset y el servidor los interpreta en
   America/Argentina/Buenos_Aires. */
"use strict";

const ZONA = "America/Argentina/Buenos_Aires";
const $ = (id) => document.getElementById(id);

const estado = { unidades: [] };

/* ------------------------------------------------ utilidades de horario */

/** "AAAA-MM-DDTHH:MM" en la zona declarada, a partir del reloj del navegador. */
function ahoraZona() {
  const partes = new Intl.DateTimeFormat("sv-SE", {
    timeZone: ZONA, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date());
  return partes.replace(" ", "T"); // sv-SE => "AAAA-MM-DD HH:MM"
}

/** Formatea un instante (ms epoch) como "AAAA-MM-DD HH:MM" usando UTC,
    lo que mantiene coherente la aritmética de reloj sin zonas. */
function comoTexto(ms) {
  const d = new Date(ms);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}` +
         `T${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}

/** Próxima hora completa, con duración de una hora. */
function horariosSugeridos() {
  const base = Date.parse(ahoraZona() + ":00Z");
  const inicio = Date.parse(comoTexto(base + 60 * 60 * 1000).replace("T", " ") + "Z");
  const redondeado = new Date(inicio);
  redondeado.setUTCMinutes(0, 0, 0);
  return { inicio: comoTexto(redondeado.getTime()),
           fin: comoTexto(redondeado.getTime() + 60 * 60 * 1000) };
}

/** "2030-01-15T10:00:00-03:00" -> "2030-01-15 10:00" (muestra local). */
function mostrar(iso) {
  return iso ? iso.slice(0, 16).replace("T", " ") : "—";
}

/* ---------------------------------------------------------- mensajes */

function mostrarError(codigo, mensaje) {
  const caja = $("error");
  caja.classList.remove("oculto");
  caja.innerHTML = "";
  const etiqueta = document.createElement("span");
  etiqueta.className = "codigo";
  etiqueta.textContent = codigo;
  caja.append(etiqueta, document.createTextNode(mensaje));
  $("resultado").classList.add("oculto");
}

function limpiarError() {
  $("error").classList.add("oculto");
  $("error").innerHTML = "";
}

function mostrarResultado(clase, texto) {
  const caja = $("resultado");
  caja.className = "resultado " + clase;
  caja.textContent = texto;
}

async function pedir(ruta, opciones) {
  let respuesta;
  try {
    respuesta = await fetch(ruta, opciones);
  } catch {
    throw { codigo: "SIN_SERVICIO", mensaje: "No se pudo contactar al servidor local." };
  }
  let datos = null;
  try { datos = await respuesta.json(); } catch { /* respuesta vacía */ }
  if (!respuesta.ok) {
    const err = (datos && datos.error) || {};
    throw { codigo: err.codigo || "HTTP_" + respuesta.status,
            mensaje: err.mensaje || "Error inesperado del servidor." };
  }
  return datos;
}

/* ---------------------------------------------------------- inventario */

async function cargarInventario() {
  const datos = await pedir("/api/inventario");
  estado.unidades = datos.unidades;

  const lista = $("lista-unidades");
  lista.innerHTML = "";
  for (const u of datos.unidades) {
    const li = document.createElement("li");
    li.innerHTML = `<strong>${u.id}</strong> · ${u.equipo}`;
    lista.append(li);
  }

  const selector = $("campo-unidad");
  selector.innerHTML = "";
  for (const u of datos.unidades) {
    const opcion = document.createElement("option");
    opcion.value = u.id;
    opcion.textContent = `${u.id} — ${u.equipo}`;
    selector.append(opcion);
  }
}

/* ----------------------------------------------------------- reservas */

async function cargarReservas() {
  const datos = await pedir("/api/reservas");
  const cuerpo = $("cuerpo-reservas");
  cuerpo.innerHTML = "";

  if (!datos.reservas.length) {
    cuerpo.innerHTML = `<tr><td colspan="7" class="cargando">Todavía no hay reservas.</td></tr>`;
    return;
  }

  for (const r of datos.reservas) {
    const fila = document.createElement("tr");
    if (r.estado !== "activa") fila.classList.add("cancelada");

    const celda = (texto) => {
      const td = document.createElement("td");
      td.textContent = texto;
      return td;
    };

    fila.append(
      celda("#" + r.id),
      celda(r.unidad),
      celda(r.solicitante),
      celda(mostrar(r.inicio)),
      celda(mostrar(r.fin)),
    );

    const tdEstado = document.createElement("td");
    tdEstado.className = "badge";
    tdEstado.innerHTML = `<span class="badge ${r.estado}">${r.estado}</span>`;
    fila.append(tdEstado);

    const tdAccion = document.createElement("td");
    tdAccion.className = "acciones-celda";
    if (r.estado === "activa") {
      const boton = document.createElement("button");
      boton.className = "peligro";
      boton.type = "button";
      boton.textContent = "Cancelar";
      boton.addEventListener("click", () => cancelar(r.id));
      tdAccion.append(boton);
    }
    fila.append(tdAccion);
    cuerpo.append(fila);
  }
}

async function cancelar(id) {
  limpiarError();
  try {
    const datos = await pedir(`/api/reservas/${id}/cancelar`, { method: "POST" });
    mostrarResultado("ok",
      `Reserva #${datos.reserva.id} cancelada. Se conservó el registro y el ` +
      `intervalo ${mostrar(datos.reserva.inicio)} – ${mostrar(datos.reserva.fin)} ` +
      `quedó libre.`);
    await cargarReservas();
  } catch (e) {
    mostrarError(e.codigo, e.mensaje);
  }
}

async function consultarDisponibilidad(event) {
  event.preventDefault();
  limpiarError();
  const { unidad, inicio, fin } = leerFormulario();
  const params = new URLSearchParams({ unidad, inicio, fin });
  try {
    const datos = await pedir(`/api/disponibilidad?${params}`);
    if (datos.disponible) {
      mostrarResultado("ok",
        `${unidad} está DISPONIBLE de ${mostrar(datos.inicio)} a ${mostrar(datos.fin)}.`);
    } else {
      const conflictos = datos.conflictos.map((c) =>
        `#${c.id} ${c.solicitante} (${mostrar(c.inicio)}–${mostrar(c.fin)})`).join(" · ");
      mostrarResultado("mal",
        `${unidad} NO está disponible. Ocupa: ${conflictos}`);
    }
  } catch (e) {
    mostrarError(e.codigo, e.mensaje);
  }
}

function leerFormulario() {
  return {
    unidad: $("campo-unidad").value,
    solicitante: $("campo-solicitante").value,
    inicio: $("campo-inicio").value,
    fin: $("campo-fin").value,
  };
}

async function crearReserva(evento) {
  evento.preventDefault();
  limpiarError();
  const datos = leerFormulario();
  try {
    const respuesta = await pedir("/api/reservas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(datos),
    });
    const r = respuesta.reserva;
    mostrarResultado("ok",
      `Reserva #${r.id} creada: ${r.unidad} para ${r.solicitante}, de ` +
      `${mostrar(r.inicio)} a ${mostrar(r.fin)}.`);
    $("campo-solicitante").value = "";
    await cargarReservas();
  } catch (e) {
    mostrarError(e.codigo, e.mensaje);
    // Si el rechazo fue por superposición, mostramos la disponibilidad real.
    if (e.codigo === "SUPERPOSICION") consultarDisponibilidad(evento);
  }
}

/* --------------------------------------------------------------- arranque */

function prepararHorarios() {
  const { inicio, fin } = horariosSugeridos();
  $("campo-inicio").value = inicio;
  $("campo-fin").value = fin;
}

document.addEventListener("DOMContentLoaded", () => {
  prepararHorarios();
  $("form-reserva").addEventListener("submit", crearReserva);
  $("btn-disponibilidad").addEventListener("click", consultarDisponibilidad);
  $("btn-actualizar").addEventListener("click", () => {
    limpiarError();
    cargarReservas().catch((e) => mostrarError(e.codigo, e.mensaje));
  });
  Promise.all([
    cargarInventario().catch((e) => mostrarError(e.codigo, e.mensaje)),
    cargarReservas().catch((e) => mostrarError(e.codigo, e.mensaje)),
  ]);
});
