#!/usr/bin/env node
// Prueba de humo del ciclo vehicular completo contra la API local.
//
// Recorre: Captura -> Inspección visual -> OBD/SBD -> Prueba -> Folio ->
// Impresión Central, con un expediente de placa única (PRU-<dígitos>), y
// valida el estado del expediente después de cada paso. Termina con el estado
// final IMPRESO. Solo usa `fetch` nativo (Node 18 o superior).
//
// Uso:  node scripts/smoke_e2e_flujo.mjs
// Requiere backend, Postgres y Redis arriba y `python -m app.seed` aplicado
// (estaciones y usuarios de desarrollo). Ver scripts/README.md.

const config = {
  base: (process.env.API_URL || "http://localhost:8000").replace(/\/+$/, ""),
  usuario: process.env.SMOKE_USUARIO || "operador1",
  password: process.env.SMOKE_PASSWORD || "operador1",
  supervisor: process.env.SMOKE_SUPERVISOR || "supervisor1",
  passwordSupervisor: process.env.SMOKE_SUPERVISOR_PASSWORD || "supervisor1",
  estaciones: {
    captura: process.env.SMOKE_EST_CAPTURA || "CAPTURA-REFORMA-L1",
    prueba: process.env.SMOKE_EST_PRUEBA || "PRUEBA-REFORMA-L1",
    impresion: process.env.SMOKE_EST_IMPRESION || "IMPRESION-REFORMA-01",
  },
  tipoCertificado: process.env.SMOKE_TIPO_CERTIFICADO || "PARTICULAR",
  tipoVerificacion: process.env.SMOKE_TIPO_VERIFICACION || "ORDINARIA",
};

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  console.log(`Prueba de humo E2E del ciclo vehicular.

Variables de entorno (todas opcionales):
  API_URL                     ${config.base}
  SMOKE_USUARIO / SMOKE_PASSWORD
  SMOKE_SUPERVISOR / SMOKE_SUPERVISOR_PASSWORD   (solo para dar de alta folios si faltan)
  SMOKE_EST_CAPTURA / SMOKE_EST_PRUEBA / SMOKE_EST_IMPRESION   (device_identifier de cada estación)
  SMOKE_TIPO_CERTIFICADO      ${config.tipoCertificado}
  SMOKE_TIPO_VERIFICACION     ${config.tipoVerificacion}
`);
  process.exit(0);
}

// ---------------------------------------------------------------- utilidades

const placa = `PRU-${Date.now().toString().slice(-6)}`;
const sesiones = []; // para cerrar sesión al final
let pasos = 0;
const t0 = Date.now();

function detalleDe(data) {
  const detalle = data?.detail;
  if (detalle == null) return "";
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle)) return detalle.map((d) => d.msg ?? JSON.stringify(d)).join("; ");
  return JSON.stringify(detalle);
}

class ErrorApi extends Error {}

async function api(metodo, ruta, { sesion, query, cuerpo } = {}) {
  const url = new URL(config.base + ruta);
  for (const [clave, valor] of Object.entries(query ?? {})) {
    if (valor !== undefined && valor !== null) url.searchParams.set(clave, String(valor));
  }
  const cabeceras = { Accept: "application/json" };
  if (sesion) cabeceras["X-Session-Id"] = sesion.id;
  const opciones = { method: metodo, headers: cabeceras };
  if (cuerpo !== undefined) {
    cabeceras["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(cuerpo);
  }
  let respuesta;
  try {
    respuesta = await fetch(url, opciones);
  } catch (err) {
    throw new ErrorApi(
      `no se pudo conectar con ${config.base} (${err.cause?.code ?? err.message}); ¿están arriba el backend, Postgres y Redis?`
    );
  }
  const texto = await respuesta.text();
  let data = null;
  try {
    data = texto ? JSON.parse(texto) : null;
  } catch {
    data = null;
  }
  if (!respuesta.ok) {
    throw new ErrorApi(`${metodo} ${ruta} -> HTTP ${respuesta.status}${detalleDe(data) ? `: ${detalleDe(data)}` : ""}`);
  }
  return data;
}

function esperar(condicion, mensaje) {
  if (!condicion) throw new ErrorApi(mensaje);
}

async function paso(nombre, fn) {
  pasos += 1;
  const inicio = Date.now();
  try {
    const resultado = await fn();
    const nota = resultado?.nota ? ` — ${resultado.nota}` : "";
    console.log(`✓ ${String(pasos).padStart(2, "0")}. ${nombre} (${Date.now() - inicio} ms)${nota}`);
    return resultado?.valor ?? resultado;
  } catch (err) {
    console.log(`✗ ${String(pasos).padStart(2, "0")}. ${nombre}`);
    console.log(`    ${err.message}`);
    throw err;
  }
}

async function iniciarSesion(tipo, usuario = config.usuario, password = config.password, device) {
  const identificador = device ?? config.estaciones[tipo];
  const estacion = await api("GET", `/api/estaciones/${encodeURIComponent(identificador)}`);
  const sesion = await api("POST", "/api/estaciones/login", {
    cuerpo: { workstation_id: estacion.id, username: usuario, password },
  });
  sesiones.push(sesion);
  return { sesion, estacion };
}

// ------------------------------------------------------------------ el ciclo

async function ciclo() {
  console.log(`Prueba de humo E2E — ${config.base}`);
  console.log(`Placa de prueba: ${placa}\n`);

  // 1-2. Captura
  const captura = await paso(`Login en caseta de Captura (${config.estaciones.captura})`, async () => {
    const { sesion, estacion } = await iniciarSesion("captura");
    esperar(estacion.station_type === "captura", `la estación detectada es de tipo ${estacion.station_type}`);
    return { valor: sesion, nota: `centro ${sesion.center_id}, línea ${sesion.line_id}` };
  });

  const expediente = await paso("Crear expediente en Captura", async () => {
    const exp = await api("POST", "/api/expedientes", { sesion: captura, cuerpo: { placa } });
    esperar(exp.estado === "CREADO", `estado esperado CREADO, recibido ${exp.estado}`);
    return { valor: exp, nota: exp.id };
  });
  const id = expediente.id;

  await paso("Capturar datos del vehículo y del certificado", async () => {
    const r = await api("POST", `/api/siox/captura-manual/${id}`, {
      sesion: captura,
      cuerpo: {
        niv: `SMOKE${Date.now().toString().slice(-12)}`,
        marca: "NISSAN",
        linea: "TSURU",
        modelo: 2000, // anterior al mínimo de OBD/SBD: el flujo sigue directo a Prueba
        tipo_vehiculo: "vehiculo",
        combustible: "GASOLINA",
        entidad_federativa: "OAXACA",
        numero_cilindros: 4,
        clasificacion_carroceria: "SEDAN",
        peso_bruto_vehicular_kg: 1500,
        pbv: "1500",
        traccion: "4x2",
        tarjeta_circulacion: `TC-${placa}`,
        propietario_estado: "Oaxaca",
        propietario_municipio: "Oaxaca de Juárez",
        propietario_codigo_postal: "68000",
        propietario_colonia: "Centro",
        propietario_calle: "Calle de Prueba",
        propietario_numero_exterior: "1",
        razon_social: "PRUEBA DE HUMO",
      },
    });
    esperar(
      r.estado_expediente === "DATOS_CAPTURADOS_MANUALMENTE",
      `estado esperado DATOS_CAPTURADOS_MANUALMENTE, recibido ${r.estado_expediente}`
    );
  });

  await paso("Confirmar normalización y enviar a Inspección Visual", async () => {
    const exp = await api("POST", `/api/expedientes/${id}/normalizar`, { sesion: captura });
    esperar(
      exp.estado === "INSPECCION_VISUAL_PENDIENTE",
      `estado esperado INSPECCION_VISUAL_PENDIENTE, recibido ${exp.estado}`
    );
  });

  // 3-4. Inspección visual y OBD en la estación de Prueba
  const prueba = await paso(`Login en estación de Prueba (${config.estaciones.prueba})`, async () => {
    const { sesion, estacion } = await iniciarSesion("prueba");
    esperar(estacion.station_type === "prueba", `la estación detectada es de tipo ${estacion.station_type}`);
    return { valor: sesion, nota: `línea ${sesion.line_id}` };
  });

  await paso("Inspección visual aprobada (todos los puntos en BUENO)", async () => {
    const puntos = await api("GET", "/api/inspeccion/checklist", { sesion: prueba });
    esperar(Array.isArray(puntos) && puntos.length > 0, "el checklist de inspección llegó vacío");
    const checklist = Object.fromEntries(puntos.map((p) => [p.clave, "BUENO"]));
    const r = await api("POST", `/api/inspeccion/${id}`, { sesion: prueba, cuerpo: { checklist } });
    esperar(r.resultado === "APROBADA", `resultado esperado APROBADA, recibido ${r.resultado}`);
    return { nota: `${puntos.length} puntos` };
  });

  await paso("Evaluar OBD/SBD", async () => {
    const r = await api("POST", `/api/obd/evaluar/${id}`, { sesion: prueba });
    if (r.aplica) {
      await api("POST", `/api/obd/solicitar/${id}`, { sesion: prueba });
      await api("POST", `/api/obd/resultado/${id}`, { sesion: prueba, cuerpo: { resultado: "APROBADO" } });
      return { nota: "aplica; resultado APROBADO" };
    }
    esperar(
      r.estado_expediente === "LISTO_PARA_PRUEBA",
      `estado esperado LISTO_PARA_PRUEBA, recibido ${r.estado_expediente}`
    );
    return { nota: "no aplica; pasa directo a Prueba" };
  });

  // 5. Prueba vehicular
  const configuracion = await paso("Consultar tipo de prueba que corresponde", async () => {
    const c = await api("GET", `/api/pruebas/configuracion/${id}`, { sesion: prueba });
    esperar(Boolean(c.tipo_default), "la configuración no trae tipo_default");
    return { valor: c, nota: c.tipo_default };
  });

  await paso(`Configurar prueba (${configuracion.tipo_default})`, async () => {
    await api("POST", `/api/pruebas/configurar/${id}`, {
      sesion: prueba,
      query: { tipo_prueba: configuracion.tipo_default },
    });
  });

  const equipo = await api("GET", "/api/pruebas/equipo/estado", { sesion: prueba }).catch(() => ({ modo: "manual" }));
  const diesel = configuracion.tipo_default === "OPACIDAD";

  await paso(`Iniciar prueba (equipo en modo ${equipo.modo})`, async () => {
    if (equipo.modo !== "manual") {
      esperar(equipo.modo === "simulador", `el modo de equipo '${equipo.modo}' no se puede automatizar en la prueba de humo`);
      for (let i = 0; i < 20; i += 1) {
        const estado = await api("GET", "/api/pruebas/equipo/estado", { sesion: prueba });
        if (estado.estado === "LISTO") break;
        await new Promise((r) => setTimeout(r, 500));
      }
    }
    const preparacion = diesel
      ? Object.fromEntries(["transmision", "temperatura", "regimen", "escape", "pedal", "humo"].map((p) => [p, true]))
      : null;
    await api("POST", `/api/pruebas/iniciar/${id}`, { sesion: prueba, cuerpo: { preparacion_nom045: preparacion } });
  });

  await paso("Guardar resultado de la prueba con lecturas aprobadas", async () => {
    let cuerpo;
    if (equipo.modo === "simulador") {
      let corrida = await api("POST", `/api/pruebas/equipo/iniciar/${id}`, {
        sesion: prueba,
        query: { escenario: "APROBADO" },
      });
      for (let i = 0; i < 60 && corrida.estado !== "FINALIZADA"; i += 1) {
        await new Promise((r) => setTimeout(r, 500));
        corrida = await api("GET", `/api/pruebas/equipo/corrida/${id}`, { sesion: prueba });
      }
      esperar(corrida.estado === "FINALIZADA", `la corrida del simulador no finalizó (estado ${corrida.estado})`);
      cuerpo = { test_run_id: corrida.test_run_id };
    } else if (diesel) {
      cuerpo = { normalized_payload: { coefficient_absorption_final_k_m1: 0.5 } };
    } else {
      const fase = { hc_ppm: 20, co_pct: 0.1, co2_pct: 14, o2_pct: 0.3 };
      cuerpo = { normalized_payload: { ralenti: fase, crucero: fase } };
    }
    const r = await api("POST", `/api/pruebas/resultado/${id}`, { sesion: prueba, cuerpo });
    esperar(
      r.estado_expediente === "PENDIENTE_IMPRESION",
      `estado esperado PENDIENTE_IMPRESION (prueba aprobada), recibido ${r.estado_expediente}`
    );
  });

  // 6. Impresión Central: folio e impresión
  const impresion = await paso(`Login en Impresión Central (${config.estaciones.impresion})`, async () => {
    const { sesion, estacion } = await iniciarSesion("impresion");
    esperar(estacion.station_type === "impresion", `la estación detectada es de tipo ${estacion.station_type}`);
    return { valor: sesion, nota: `líneas ${(estacion.allowed_line_ids ?? []).join(", ") || "todas"}` };
  });

  await paso(`Verificar inventario de folios ${config.tipoCertificado}`, async () => {
    let supervisor;
    try {
      ({ sesion: supervisor } = await iniciarSesion("captura", config.supervisor, config.passwordSupervisor));
    } catch (err) {
      return { nota: `sin sesión de supervisor, se omite la verificación (${err.message})` };
    }
    const inventario = await api("GET", "/api/folios/inventario", { sesion: supervisor });
    const fila = inventario.find((f) => f.tipo_certificado === config.tipoCertificado);
    if (fila && fila.disponibles >= 1) return { nota: `${fila.disponibles} disponibles` };
    const prefijo = `SMK-${Date.now()}-`;
    const lote = await api("POST", "/api/folios/lotes", {
      sesion: supervisor,
      query: {
        tipo_certificado: config.tipoCertificado,
        folio_inicio: `${prefijo}0001`,
        folio_fin: `${prefijo}0005`,
      },
    });
    return { nota: `sin folios; se registró un lote de ${lote.cantidad}` };
  });

  await paso(`Determinar tipo de certificado (${config.tipoCertificado}, ${config.tipoVerificacion})`, async () => {
    const r = await api("POST", `/api/impresion/tipo-certificado/${id}`, {
      sesion: impresion,
      query: { tipo_certificado: config.tipoCertificado, tipo_verificacion: config.tipoVerificacion },
    });
    esperar(r.certificado_tipo === config.tipoCertificado, `tipo esperado ${config.tipoCertificado}, recibido ${r.certificado_tipo}`);
  });

  const folio = await paso("Solicitar folio", async () => {
    const r = await api("POST", `/api/folios/solicitar/${id}`, {
      sesion: impresion,
      query: { tipo_certificado: config.tipoCertificado },
    });
    esperar(r.estado_expediente === "FOLIO_ASIGNADO", `estado esperado FOLIO_ASIGNADO, recibido ${r.estado_expediente}`);
    esperar(Boolean(r.folio), "la respuesta no trae folio");
    return { valor: r.folio, nota: r.folio };
  });

  await paso("Imprimir certificado", async () => {
    const r = await api("POST", `/api/impresion/imprimir/${id}`, { sesion: impresion });
    esperar(r.estado_expediente === "IMPRESO", `estado final esperado IMPRESO, recibido ${r.estado_expediente}`);
  });

  await paso("Verificar el expediente impreso", async () => {
    const exp = await api("GET", `/api/expedientes/${id}`, { sesion: impresion });
    esperar(exp.estado === "IMPRESO", `estado final esperado IMPRESO, recibido ${exp.estado}`);
    esperar(exp.folio_externo === folio, `folio esperado ${folio}, recibido ${exp.folio_externo}`);
    return { nota: `${exp.placa} · folio ${exp.folio_externo} · ${exp.certificado_tipo}` };
  });
}

async function cerrarSesiones() {
  for (const sesion of sesiones.splice(0)) {
    try {
      await api("POST", `/api/estaciones/logout/${sesion.id}`, { sesion });
    } catch {
      // Si la sesión ya caducó o el backend cayó, no hay nada que limpiar.
    }
  }
}

let fallo = false;
try {
  await ciclo();
} catch {
  fallo = true;
} finally {
  await cerrarSesiones();
}

const segundos = ((Date.now() - t0) / 1000).toFixed(1);
if (fallo) {
  console.log(`\n✗ La prueba de humo falló en el paso ${String(pasos).padStart(2, "0")} (${segundos} s). Placa ${placa}.`);
  // exitCode en vez de process.exit(): en Windows, salir de golpe con
  // conexiones de fetch abiertas aborta Node (aserción de libuv).
  process.exitCode = 1;
} else {
  console.log(`\n✓ Ciclo completo OK: ${pasos} pasos, expediente ${placa} en estado IMPRESO (${segundos} s).`);
}
