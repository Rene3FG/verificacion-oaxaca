#!/usr/bin/env node
// Prueba de carga y concurrencia realista (Q4).
//
// Levanta sesiones en 2 líneas completas (Captura + Prueba en L1/L2) y en
// Impresión Central, prepara expedientes en paralelo, y valida bajo ráfagas
// concurrentes reales (`Promise.all`):
//   1. Pipeline multi-línea paralelo hasta PENDIENTE_IMPRESION + tipo certificado.
//   2. Asignación atómica de folios (`SKIP LOCKED`) con lote menor a la demanda:
//      N éxitos con folios únicos y M HTTP 409 por agotamiento exacto.
//   3. Idempotencia bajo ráfaga sobre el mismo expediente (`with_for_update=True`):
//      múltiples solicitudes simultáneas devuelven el mismo folio y consumen 1.
//   4. Generación concurrente de vista previa PDF + impresión definitiva (`IMPRESO`).
//
// Uso:
//   node scripts/smoke_carga_concurrencia.mjs
// Variables opcionales: API_URL, SMOKE_USUARIO, SMOKE_PASSWORD,
//   SMOKE_SUPERVISOR, SMOKE_SUPERVISOR_PASSWORD, CARGA_EXPEDIENTES (12),
//   CARGA_FOLIOS_LOTE (10), CARGA_IDEMPOTENCIA (6), CARGA_TIPO_CERTIFICADO.

const config = {
  base: (process.env.API_URL || "http://localhost:8000").replace(/\/+$/, ""),
  usuario: process.env.SMOKE_USUARIO || "operador1",
  password: process.env.SMOKE_PASSWORD || "operador1",
  supervisor: process.env.SMOKE_SUPERVISOR || "supervisor1",
  passwordSupervisor: process.env.SMOKE_SUPERVISOR_PASSWORD || "supervisor1",
  totalExpedientes: Number(process.env.CARGA_EXPEDIENTES || 12),
  foliosLote: Number(process.env.CARGA_FOLIOS_LOTE || 10),
  idempotenciaReps: Number(process.env.CARGA_IDEMPOTENCIA || 6),
  tipoCertificado: process.env.CARGA_TIPO_CERTIFICADO || "PARTICULAR",
  tipoVerificacion: process.env.CARGA_TIPO_VERIFICACION || "ORDINARIA",
  estaciones: {
    capturaL1: process.env.CARGA_CAPTURA_L1 || "CAPTURA-REFORMA-L1",
    capturaL2: process.env.CARGA_CAPTURA_L2 || "CAPTURA-REFORMA-L2",
    pruebaL1: process.env.CARGA_PRUEBA_L1 || "PRUEBA-REFORMA-L1",
    pruebaL2: process.env.CARGA_PRUEBA_L2 || "PRUEBA-REFORMA-L2",
    impresion: process.env.CARGA_IMPRESION || "IMPRESION-REFORMA-01",
  },
};

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  console.log(`Prueba de carga y concurrencia Q4 — Verificación Oaxaca

Variables de entorno (opcionales):
  API_URL                    ${config.base}
  SMOKE_USUARIO / SMOKE_PASSWORD
  SMOKE_SUPERVISOR / SMOKE_SUPERVISOR_PASSWORD
  CARGA_EXPEDIENTES          ${config.totalExpedientes}
  CARGA_FOLIOS_LOTE          ${config.foliosLote}
  CARGA_IDEMPOTENCIA         ${config.idempotenciaReps}
  CARGA_TIPO_CERTIFICADO     ${config.tipoCertificado}
`);
  process.exit(0);
}

const sesiones = [];
const t0 = Date.now();
let errores5xx = 0;

function detalleDe(data) {
  const detalle = data?.detail;
  if (detalle == null) return "";
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle)) return detalle.map((d) => d.msg ?? JSON.stringify(d)).join("; ");
  return JSON.stringify(detalle);
}

async function rawFetch(metodo, ruta, { sesion, query, cuerpo, aceptarPdf = false } = {}) {
  const url = new URL(config.base + ruta);
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
  }
  const headers = { Accept: aceptarPdf ? "application/pdf" : "application/json" };
  if (sesion) headers["X-Session-Id"] = sesion.id;
  const opciones = { method: metodo, headers };
  if (cuerpo !== undefined) {
    headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(cuerpo);
  }
  const inicio = Date.now();
  const res = await fetch(url, opciones);
  const ms = Date.now() - inicio;
  if (res.status >= 500) errores5xx += 1;

  if (aceptarPdf) {
    const buf = new Uint8Array(await res.arrayBuffer());
    return { ok: res.ok, status: res.status, ms, contentType: res.headers.get("content-type") || "", bytes: buf };
  }

  const texto = await res.text();
  let data = null;
  try {
    data = texto ? JSON.parse(texto) : null;
  } catch {
    data = null;
  }
  return { ok: res.ok, status: res.status, ms, data, detalle: detalleDe(data) };
}

async function api(metodo, ruta, opts = {}) {
  const r = await rawFetch(metodo, ruta, opts);
  if (!r.ok) {
    throw new Error(`${metodo} ${ruta} -> HTTP ${r.status}${r.detalle ? `: ${r.detalle}` : ""}`);
  }
  return r.data;
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

function resumenTiempos(listaMs) {
  const ordenados = [...listaMs].sort((a, b) => a - b);
  const sum = ordenados.reduce((a, b) => a + b, 0);
  const p95Idx = Math.min(ordenados.length - 1, Math.floor(ordenados.length * 0.95));
  return {
    min: ordenados[0] ?? 0,
    avg: ordenados.length ? Math.round(sum / ordenados.length) : 0,
    p95: ordenados[p95Idx] ?? 0,
    max: ordenados[ordenados.length - 1] ?? 0,
  };
}

async function abrirSesion(identificador, tipoEsperado, usuario, password) {
  const est = await api("GET", `/api/estaciones/${encodeURIComponent(identificador)}`);
  assert(est.station_type === tipoEsperado, `${identificador} devolvió tipo ${est.station_type}`);
  const sesion = await api("POST", "/api/estaciones/login", {
    cuerpo: { workstation_id: est.id, username: usuario, password },
  });
  sesiones.push(sesion);
  return sesion;
}

async function prepararExpedienteHastaImpresion(indice, lineaCtx, impresionSesion, puntosChecklist) {
  const tInicio = Date.now();
  const sufijo = `${String(indice).padStart(2, "0")}${Date.now().toString().slice(-4)}`;
  const placa = `Q4L${lineaCtx.linea}${sufijo}`;

  const exp = await api("POST", "/api/expedientes", {
    sesion: lineaCtx.captura,
    cuerpo: { placa },
  });
  const id = exp.id;

  await api("POST", `/api/siox/captura-manual/${id}`, {
    sesion: lineaCtx.captura,
    cuerpo: {
      niv: `CARGA${String(indice).padStart(2, "0")}${Date.now().toString().slice(-10)}`,
      marca: "NISSAN",
      linea: "TSURU",
      modelo: 2000,
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
      propietario_calle: "Calle de Carga",
      propietario_numero_exterior: String(indice + 1),
      razon_social: "PRUEBA DE CARGA Q4",
    },
  });

  await api("POST", `/api/expedientes/${id}/normalizar`, { sesion: lineaCtx.captura });

  const checklist = Object.fromEntries(puntosChecklist.map((p) => [p.clave, "BUENO"]));
  const insp = await api("POST", `/api/inspeccion/${id}`, {
    sesion: lineaCtx.captura,
    cuerpo: { checklist },
  });
  assert(insp.resultado === "APROBADA", `inspección inesperada en ${id}: ${insp.resultado}`);

  const obd = await api("POST", `/api/obd/evaluar/${id}`, { sesion: lineaCtx.prueba });
  assert(obd.estado_expediente === "LISTO_PARA_PRUEBA", `OBD inesperado en ${id}: ${obd.estado_expediente}`);

  const cfg = await api("GET", `/api/pruebas/configuracion/${id}`, { sesion: lineaCtx.prueba });
  await api("POST", `/api/pruebas/configurar/${id}`, {
    sesion: lineaCtx.prueba,
    query: { tipo_prueba: cfg.tipo_default },
  });
  await api("POST", `/api/pruebas/iniciar/${id}`, {
    sesion: lineaCtx.prueba,
    cuerpo: { preparacion_nom045: null },
  });

  const fase = { hc_ppm: 20, co_pct: 0.1, co2_pct: 14, o2_pct: 0.3 };
  const resPrueba = await api("POST", `/api/pruebas/resultado/${id}`, {
    sesion: lineaCtx.prueba,
    cuerpo: { normalized_payload: { ralenti: fase, crucero: fase } },
  });
  assert(
    resPrueba.estado_expediente === "PENDIENTE_IMPRESION",
    `estado esperado PENDIENTE_IMPRESION en ${id}, recibido ${resPrueba.estado_expediente}`
  );

  const tipoResp = await api("POST", `/api/impresion/tipo-certificado/${id}`, {
    sesion: impresionSesion,
    query: { tipo_certificado: config.tipoCertificado, tipo_verificacion: config.tipoVerificacion },
  });
  assert(tipoResp.certificado_tipo === config.tipoCertificado, `certificado_tipo inesperado en ${id}`);

  return { id, placa, linea: lineaCtx.linea, ms: Date.now() - tInicio };
}

async function obtenerFilaInventario(supervisor) {
  const inv = await api("GET", "/api/folios/inventario", { sesion: supervisor });
  return inv.find((f) => f.tipo_certificado === config.tipoCertificado) || {
    disponibles: 0,
    asignados: 0,
    impresos: 0,
  };
}

async function ejecutar() {
  assert(config.totalExpedientes > config.foliosLote, "CARGA_EXPEDIENTES debe ser mayor que CARGA_FOLIOS_LOTE");
  console.log(`Prueba Q4 carga y concurrencia — ${config.base}`);
  console.log(
    `Parámetros: ${config.totalExpedientes} expedientes (L1/L2 en paralelo), lote inicial=${config.foliosLote}, ráfaga idempotencia=${config.idempotenciaReps}x\n`
  );

  // 1. Sesiones (2 líneas completas + Impresión Central + Supervisor)
  const [capturaL1, capturaL2, pruebaL1, pruebaL2, impresion, supervisor] = await Promise.all([
    abrirSesion(config.estaciones.capturaL1, "captura", config.usuario, config.password),
    abrirSesion(config.estaciones.capturaL2, "captura", config.usuario, config.password),
    abrirSesion(config.estaciones.pruebaL1, "prueba", config.usuario, config.password),
    abrirSesion(config.estaciones.pruebaL2, "prueba", config.usuario, config.password),
    abrirSesion(config.estaciones.impresion, "impresion", config.usuario, config.password),
    abrirSesion(config.estaciones.capturaL1, "captura", config.supervisor, config.passwordSupervisor),
  ]);
  console.log("✓ 01. 6 sesiones concurrentes abiertas (Capturas L1/L2, Pruebas L1/L2, Impresión 01, Supervisor)");

  const invInicial = await obtenerFilaInventario(supervisor);
  assert(
    invInicial.disponibles === 0,
    `Para medir agotamiento exacto se espera iniciar con 0 folios ${config.tipoCertificado} disponibles (hay ${invInicial.disponibles})`
  );

  const puntosChecklist = await api("GET", "/api/inspeccion/checklist", { sesion: capturaL1 });
  assert(Array.isArray(puntosChecklist) && puntosChecklist.length > 0, "checklist de inspección vacío");

  // 2. Preparación concurrente en L1 y L2
  const lineas = [
    { linea: 1, captura: capturaL1, prueba: pruebaL1 },
    { linea: 2, captura: capturaL2, prueba: pruebaL2 },
  ];
  const tPrep = Date.now();
  const expedientes = await Promise.all(
    Array.from({ length: config.totalExpedientes }, (_, i) =>
      prepararExpedienteHastaImpresion(i, lineas[i % 2], impresion, puntosChecklist)
    )
  );
  const statsPrep = resumenTiempos(expedientes.map((e) => e.ms));
  console.log(
    `✓ 02. ${expedientes.length} expedientes preparados en paralelo L1/L2 en ${Date.now() - tPrep} ms ` +
      `(por exp min/avg/p95/max = ${statsPrep.min}/${statsPrep.avg}/${statsPrep.p95}/${statsPrep.max} ms)`
  );

  // 3. Registrar lote exacto menor a la demanda
  const prefijo1 = `Q4A-${Date.now()}-`;
  await api("POST", "/api/folios/lotes", {
    sesion: supervisor,
    query: {
      tipo_certificado: config.tipoCertificado,
      folio_inicio: `${prefijo1}0001`,
      folio_fin: `${prefijo1}${String(config.foliosLote).padStart(4, "0")}`,
    },
  });
  const invAntesRafaga = await obtenerFilaInventario(supervisor);
  assert(invAntesRafaga.disponibles === config.foliosLote, `disponibles esperados ${config.foliosLote}`);
  console.log(`✓ 03. Lote registrado (${config.foliosLote} folios disponibles vs ${expedientes.length} solicitudes)`);

  // 4. Ráfaga simultánea de solicitud de folios sobre expedientes distintos
  const tRafaga = Date.now();
  const resultadosRafaga = await Promise.all(
    expedientes.map((e) =>
      rawFetch("POST", `/api/folios/solicitar/${e.id}`, {
        sesion: impresion,
        query: { tipo_certificado: config.tipoCertificado },
      }).then((r) => ({ exp: e, ...r }))
    )
  );
  const asignados = resultadosRafaga.filter((r) => r.status === 200);
  const agotados = resultadosRafaga.filter((r) => r.status === 409);
  const inesperados = resultadosRafaga.filter((r) => r.status !== 200 && r.status !== 409);
  assert(inesperados.length === 0, `respuestas inesperadas en ráfaga: ${JSON.stringify(inesperados.map((x) => x.status))}`);
  assert(
    asignados.length === config.foliosLote && agotados.length === config.totalExpedientes - config.foliosLote,
    `asignados=${asignados.length} agotados=${agotados.length}`
  );
  const foliosUnicos = new Set(asignados.map((r) => r.data?.folio));
  assert(foliosUnicos.size === config.foliosLote, `colisión de folios detectada: ${foliosUnicos.size}/${config.foliosLote}`);
  const statsRafaga = resumenTiempos(resultadosRafaga.map((r) => r.ms));
  console.log(
    `✓ 04. Ráfaga folios (${expedientes.length} simultáneas en ${Date.now() - tRafaga} ms): ` +
      `${asignados.length} asignados únicos, ${agotados.length} HTTP 409 exactos ` +
      `(min/avg/p95/max = ${statsRafaga.min}/${statsRafaga.avg}/${statsRafaga.p95}/${statsRafaga.max} ms)`
  );

  // 5. Idempotencia bajo ráfaga sobre el MISMO expediente (with_for_update=True)
  const prefijo2 = `Q4B-${Date.now()}-`;
  await api("POST", "/api/folios/lotes", {
    sesion: supervisor,
    query: {
      tipo_certificado: config.tipoCertificado,
      folio_inicio: `${prefijo2}0001`,
      folio_fin: `${prefijo2}0003`,
    },
  });
  const expReintento = agotados[0].exp;
  const tIdemp = Date.now();
  const resIdemp = await Promise.all(
    Array.from({ length: config.idempotenciaReps }, () =>
      rawFetch("POST", `/api/folios/solicitar/${expReintento.id}`, {
        sesion: impresion,
        query: { tipo_certificado: config.tipoCertificado },
      })
    )
  );
  assert(
    resIdemp.every((r) => r.status === 200),
    `fallo en ráfaga idempotente: ${resIdemp.map((r) => `${r.status}:${r.detalle}`).join(", ")}`
  );
  const foliosIdemp = new Set(resIdemp.map((r) => r.data?.folio));
  assert(foliosIdemp.size === 1, `la ráfaga idempotente asignó más de 1 folio: ${[...foliosIdemp].join(", ")}`);
  const invTrasIdemp = await obtenerFilaInventario(supervisor);
  assert(
    invTrasIdemp.disponibles === 2 && invTrasIdemp.asignados === invInicial.asignados + config.foliosLote + 1,
    `consumo inesperado tras idempotencia: ${JSON.stringify(invTrasIdemp)}`
  );
  console.log(
    `✓ 05. Idempotencia mismo expediente (${config.idempotenciaReps}x simultáneas en ${Date.now() - tIdemp} ms): ` +
      `${resIdemp.length}/${config.idempotenciaReps} HTTP 200 con folio único ${[...foliosIdemp][0]} y 2 folios intactos`
  );

  // 6. Vista previa PDF e Impresión definitiva concurrentes
  const conFolio = [...asignados.map((a) => a.exp), expReintento];
  const tPdf = Date.now();
  const resPdf = await Promise.all(
    conFolio.map((e) => rawFetch("GET", `/api/impresion/vista-previa/${e.id}`, { sesion: impresion, aceptarPdf: true }))
  );
  for (const r of resPdf) {
    assert(r.status === 200, `vista previa devolvió HTTP ${r.status}`);
    assert(r.contentType.includes("application/pdf"), `Content-Type inesperado: ${r.contentType}`);
    const cabecera = String.fromCharCode(...r.bytes.slice(0, 5));
    assert(cabecera === "%PDF-", `cabecera PDF inválida: ${cabecera}`);
  }
  const statsPdf = resumenTiempos(resPdf.map((r) => r.ms));
  console.log(
    `✓ 06. ${resPdf.length} vistas previas PDF (WeasyPrint) en paralelo en ${Date.now() - tPdf} ms ` +
      `(min/avg/p95/max = ${statsPdf.min}/${statsPdf.avg}/${statsPdf.p95}/${statsPdf.max} ms)`
  );

  const tImp = Date.now();
  const resImp = await Promise.all(
    conFolio.map((e) => rawFetch("POST", `/api/impresion/imprimir/${e.id}`, { sesion: impresion }))
  );
  assert(
    resImp.every((r) => r.status === 200 && r.data?.estado_expediente === "IMPRESO"),
    `fallo en impresión concurrente: ${resImp.map((r) => `${r.status}:${r.detalle}`).join(", ")}`
  );
  const statsImp = resumenTiempos(resImp.map((r) => r.ms));
  console.log(
    `✓ 07. ${resImp.length} impresiones definitivas en paralelo en ${Date.now() - tImp} ms ` +
      `(min/avg/p95/max = ${statsImp.min}/${statsImp.avg}/${statsImp.p95}/${statsImp.max} ms)`
  );

  const invFinal = await obtenerFilaInventario(supervisor);
  assert(
    invFinal.disponibles === 2 &&
      invFinal.asignados === invInicial.asignados &&
      invFinal.impresos === invInicial.impresos + conFolio.length,
    `inventario final inconsistente: ${JSON.stringify(invFinal)}`
  );
  assert(errores5xx === 0, `se detectaron ${errores5xx} respuestas HTTP 5xx`);
  console.log(
    `✓ 08. Inventario final consistente (disponibles=${invFinal.disponibles}, asignados=${invFinal.asignados}, impresos=${invFinal.impresos}), 0 errores 5xx`
  );
}

async function cerrarSesiones() {
  for (const s of sesiones.splice(0)) {
    try {
      await rawFetch("POST", `/api/estaciones/logout/${s.id}`, { sesion: s });
    } catch {
      // ignorar si ya caducó
    }
  }
}

let fallo = false;
try {
  await ejecutar();
} catch (err) {
  fallo = true;
  console.error(`\n✗ Fallo en Q4: ${err.message}`);
} finally {
  await cerrarSesiones();
}

const seg = ((Date.now() - t0) / 1000).toFixed(1);
if (fallo || errores5xx > 0) {
  process.exitCode = 1;
} else {
  console.log(`\n✓ Prueba Q4 completa sin deadlocks ni 5xx (${seg} s).`);
}
