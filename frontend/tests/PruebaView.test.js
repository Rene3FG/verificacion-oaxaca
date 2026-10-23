import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import * as directives from "vuetify/directives";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// jsdom no define visualViewport y el diálogo de interrupción (VOverlay) lo usa.
if (!globalThis.visualViewport) {
  globalThis.visualViewport = {
    width: 1024,
    height: 768,
    offsetLeft: 0,
    offsetTop: 0,
    scale: 1,
    addEventListener() {},
    removeEventListener() {},
  };
}

vi.mock("../src/api/client", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

import { api } from "../src/api/client";
import PruebaView from "../src/views/PruebaView.vue";
import { useSessionStore } from "../src/stores/session";

const CHECKLIST = [
  { clave: "luces", etiqueta: "Luces" },
  { clave: "llantas", etiqueta: "Llantas" },
  { clave: "escape", etiqueta: "Escape" },
];

// Resultado de una corrida finalizada de gasolina, como lo devuelve el gateway.
const RESULTADO_GAS = { ralenti: { hc_ppm: 50, co_pct: 0.2 }, crucero: { hc_ppm: 40, co_pct: 0.1 } };

const LISTA = [
  { id: "exp-1", placa: "AAA-001", estado: "INSPECCION_VISUAL_PENDIENTE" },
  { id: "exp-2", placa: "BBB-002", estado: "LISTO_PARA_PRUEBA" },
  { id: "exp-3", placa: "CCC-003", estado: "ERROR_INTEGRACION" },
  { id: "exp-4", placa: "DDD-004", estado: "CREADO" }, // aún en Captura: se filtra
  { id: "exp-5", placa: "EEE-005", estado: "IMPRESO" }, // ya salió: se filtra
];

function expedienteBase(extra = {}) {
  return {
    id: "exp-1",
    placa: "AAA-001",
    estado: "INSPECCION_VISUAL_PENDIENTE",
    linea_id: 1,
    centro_id: "OAX-01",
    folio_multa: null,
    certificado_anterior: null,
    tipo_prueba_final: null,
    vehiculo: {
      niv: "3N1AB7AP1MY111111",
      marca: "NISSAN",
      linea: "VERSA",
      modelo: 2021,
      combustible: "GASOLINA",
      fuente_datos: "SIOX",
    },
    ...extra,
  };
}

// Estado mutable del servidor simulado: cada prueba lo ajusta antes de montar.
let srv;

function reiniciarServidor() {
  srv = {
    lista: LISTA,
    expediente: expedienteBase(),
    equipo: { modo: "manual", estado: null, mensaje_tecnico: null },
    configuracion: {
      tipo_default: "DINAMICA",
      puede_cambiar_a_estatica: true,
      potencia_aplicada_bhp: { ralenti: 10, crucero: 20 },
    },
    corrida: null,
    fallaGet: {},
    postHandlers: {},
  };
}

function rechazo(status, detail) {
  return Promise.reject({ response: { status, data: { detail } } });
}

function instalarApi() {
  api.get.mockImplementation((url) => {
    if (srv.fallaGet[url]) return srv.fallaGet[url]();
    if (url.startsWith("/catalogos/")) return Promise.resolve({ data: [] });
    if (url === "/inspeccion/checklist") return Promise.resolve({ data: CHECKLIST });
    if (url === "/expedientes") return Promise.resolve({ data: srv.lista });
    if (url === "/pruebas/equipo/estado") return Promise.resolve({ data: srv.equipo });
    if (url.startsWith("/pruebas/equipo/corrida/")) return Promise.resolve({ data: srv.corrida });
    if (url.startsWith("/pruebas/configuracion/")) return Promise.resolve({ data: srv.configuracion });
    if (url.startsWith("/expedientes/")) return Promise.resolve({ data: srv.expediente });
    return Promise.reject(new Error(`GET no simulado: ${url}`));
  });
  api.post.mockImplementation((url, body, config) => {
    const handler = Object.entries(srv.postHandlers).find(([prefijo]) => url.startsWith(prefijo));
    if (handler) return handler[1](url, body, config);
    return Promise.resolve({ data: {} });
  });
  api.patch.mockResolvedValue({ data: {} });
}

function montar({ estacion } = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore();
  session.estacion = estacion ?? {
    id: "ws-pru-01",
    name: "Prueba Línea 1",
    station_type: "prueba",
    center_id: "OAX-01",
    line_id: 1,
  };
  session.sesion = { id: "ses-1", can_supervise: false };
  session.usuario = "operador1";
  instalarApi();

  const vuetify = createVuetify({ components, directives });
  return mount(PruebaView, { global: { plugins: [pinia, vuetify] } });
}

async function abrir(w, id = "exp-1") {
  await w.vm.abrirExpediente(id);
  await flushPromises();
}

function llamadasPost(prefijo) {
  return api.post.mock.calls.filter(([url]) => url.startsWith(prefijo));
}

beforeEach(() => {
  vi.clearAllMocks();
  reiniciarServidor();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("PruebaView - Lista de expedientes en curso", () => {
  it("carga la lista de la estación y muestra solo los estados que le corresponden a Prueba", async () => {
    const w = montar();
    await flushPromises();

    expect(api.get).toHaveBeenCalledWith("/expedientes", {
      params: { centro_id: "OAX-01", linea_id: 1 },
    });
    const t = w.text();
    expect(t).toContain("Estación de Prueba");
    expect(t).toContain("Placa AAA-001");
    expect(t).toContain("Placa BBB-002");
    expect(t).toContain("Placa CCC-003");
    expect(t).not.toContain("DDD-004");
    expect(t).not.toContain("EEE-005");
  });

  it("muestra mensaje vacío cuando no hay expedientes pendientes", async () => {
    srv.lista = [{ id: "x", placa: "ZZZ-999", estado: "IMPRESO" }];
    const w = montar();
    await flushPromises();
    expect(w.text()).toContain("No hay expedientes pendientes");
  });

  it("no consulta la lista si la estación no tiene centro y línea", async () => {
    montar({ estacion: { id: "ws", station_type: "prueba", center_id: "OAX-01", line_id: null } });
    await flushPromises();
    expect(api.get).not.toHaveBeenCalledWith("/expedientes", expect.anything());
  });

  it("muestra el detalle del backend si falla la carga de la lista", async () => {
    srv.fallaGet["/expedientes"] = () => rechazo(500, "Base de datos caída");
    const w = montar();
    await flushPromises();
    expect(w.text()).toContain("Base de datos caída");
  });

  it("carga el catálogo de checklist de inspección al montar", async () => {
    const w = montar();
    await flushPromises();
    expect(api.get).toHaveBeenCalledWith("/inspeccion/checklist");
    expect(w.vm.checklistItems).toHaveLength(3);
  });

  it("avisa si no se puede cargar el checklist", async () => {
    srv.fallaGet["/inspeccion/checklist"] = () => rechazo(500, "Checklist no disponible");
    const w = montar();
    await flushPromises();
    expect(w.vm.error).toBe("Checklist no disponible");
  });
});

describe("PruebaView - Apertura de expediente", () => {
  it("abre el expediente y no consulta equipo ni configuración en inspección visual", async () => {
    const w = montar();
    await flushPromises();
    await abrir(w);

    expect(w.vm.expediente.id).toBe("exp-1");
    expect(w.text()).toContain("Volver a la lista");
    expect(api.get).not.toHaveBeenCalledWith("/pruebas/equipo/estado");
    expect(api.get).not.toHaveBeenCalledWith("/pruebas/configuracion/exp-1");
  });

  it("en LISTO_PARA_PRUEBA consulta estado del equipo y configuración del servidor", async () => {
    srv.expediente = expedienteBase({ estado: "LISTO_PARA_PRUEBA" });
    const w = montar();
    await flushPromises();
    await abrir(w);

    expect(api.get).toHaveBeenCalledWith("/pruebas/equipo/estado");
    expect(api.get).toHaveBeenCalledWith("/pruebas/configuracion/exp-1");
    expect(w.vm.configuracionPrueba.tipo_default).toBe("DINAMICA");
  });

  it("si falla la configuración usa el respaldo local por combustible", async () => {
    srv.expediente = expedienteBase({ estado: "LISTO_PARA_PRUEBA" });
    srv.fallaGet["/pruebas/configuracion/exp-1"] = () => rechazo(500, "x");
    const w = montar();
    await flushPromises();
    await abrir(w);

    expect(w.vm.configuracionPrueba).toBeNull();
    expect(w.vm.tipoPruebaDefault).toBe("DINAMICA");
    expect(w.vm.puedeCambiarAEstatica).toBe(true);
    expect(w.vm.error).toBeNull();
  });

  it("el respaldo local para diésel es OPACIDAD sin cambio a estática", async () => {
    srv.expediente = expedienteBase({
      estado: "LISTO_PARA_PRUEBA",
      vehiculo: { combustible: "DIESEL" },
    });
    srv.fallaGet["/pruebas/configuracion/exp-1"] = () => rechazo(500, "x");
    const w = montar();
    await flushPromises();
    await abrir(w);

    expect(w.vm.tipoPruebaDefault).toBe("OPACIDAD");
    expect(w.vm.puedeCambiarAEstatica).toBe(false);
  });

  it("muestra el error si no se puede abrir el expediente", async () => {
    srv.fallaGet["/expedientes/exp-1"] = () => rechazo(404, "Expediente no encontrado");
    const w = montar();
    await flushPromises();
    await w.vm.abrirExpediente("exp-1");
    await flushPromises();
    expect(w.vm.expediente).toBeNull();
    expect(w.vm.error).toBe("Expediente no encontrado");
  });

  it("'Volver a la lista' cierra el expediente y recarga la lista", async () => {
    const w = montar();
    await flushPromises();
    await abrir(w);
    api.get.mockClear();

    w.vm.cerrarExpediente();
    await flushPromises();

    expect(w.vm.expediente).toBeNull();
    expect(api.get).toHaveBeenCalledWith("/expedientes", expect.anything());
  });
});

describe("PruebaView - Inspección visual", () => {
  async function conChecklist() {
    const w = montar();
    await flushPromises();
    await abrir(w);
    return w;
  }

  it("no hay resultado ni checklist completo hasta pronunciarse sobre los 8 puntos", async () => {
    const w = await conChecklist();
    expect(w.vm.checklistCompleto).toBe(false);
    expect(w.vm.resultadoInspeccion).toBeNull();

    w.vm.checklistForm.luces = "BUENO";
    w.vm.checklistForm.llantas = "NO_APLICA";
    await flushPromises();
    expect(w.vm.checklistCompleto).toBe(false);
  });

  it("espejo informativo: APROBADA si no hay MALO, RECHAZADA con al menos uno", async () => {
    const w = await conChecklist();
    w.vm.checklistForm.luces = "BUENO";
    w.vm.checklistForm.llantas = "NO_APLICA";
    w.vm.checklistForm.escape = "BUENO";
    await flushPromises();
    expect(w.vm.resultadoInspeccion).toBe("APROBADA");

    w.vm.checklistForm.escape = "MALO";
    await flushPromises();
    expect(w.vm.resultadoInspeccion).toBe("RECHAZADA");
    expect(w.vm.itemsMalos.map((i) => i.clave)).toEqual(["escape"]);
  });

  it("registra inspección aprobada, avisa y recarga el expediente", async () => {
    srv.postHandlers["/inspeccion/"] = () => Promise.resolve({ data: { resultado: "APROBADA" } });
    const w = await conChecklist();
    w.vm.checklistForm.luces = "BUENO";
    w.vm.checklistForm.llantas = "BUENO";
    w.vm.checklistForm.escape = "BUENO";
    w.vm.observacionesInspeccion = "  todo en orden  ";

    await w.vm.registrarInspeccion();
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith("/inspeccion/exp-1", {
      checklist: { luces: "BUENO", llantas: "BUENO", escape: "BUENO" },
      observaciones: "todo en orden",
    });
    expect(w.vm.aviso).toBe("Inspección visual aprobada.");
    expect(w.vm.expediente).not.toBeNull();
  });

  it("observaciones vacías viajan como null", async () => {
    srv.postHandlers["/inspeccion/"] = () => Promise.resolve({ data: { resultado: "APROBADA" } });
    const w = await conChecklist();
    w.vm.observacionesInspeccion = "   ";
    await w.vm.registrarInspeccion();
    expect(api.post.mock.calls.find(([u]) => u === "/inspeccion/exp-1")[1].observaciones).toBeNull();
  });

  it("inspección RECHAZADA envía el expediente a Impresión y vuelve a la lista", async () => {
    srv.postHandlers["/inspeccion/"] = () => Promise.resolve({ data: { resultado: "RECHAZADA" } });
    const w = await conChecklist();

    await w.vm.registrarInspeccion();
    await flushPromises();

    expect(w.vm.expediente).toBeNull();
    expect(llamadasPost("/inspeccion/")).toHaveLength(1);
  });

  // DEFECTO CONOCIDO (PruebaView.vue, de René): registrarInspeccion asigna
  // aviso y luego cerrarExpediente() lo pone en null, así que el operador
  // nunca ve "Inspección rechazada…". it.fails pasa mientras el defecto
  // exista y se pondrá en rojo cuando se corrija: ahí quitar el .fails.
  it.fails("el aviso de inspección rechazada sobrevive al cierre del expediente", async () => {
    srv.postHandlers["/inspeccion/"] = () => Promise.resolve({ data: { resultado: "RECHAZADA" } });
    const w = await conChecklist();
    await w.vm.registrarInspeccion();
    await flushPromises();
    expect(w.vm.aviso).toContain("Inspección rechazada");
  });

  it("muestra el error del backend si no se puede registrar la inspección", async () => {
    srv.postHandlers["/inspeccion/"] = () => rechazo(409, "Estado inválido para inspección");
    const w = await conChecklist();
    await w.vm.registrarInspeccion();
    await flushPromises();
    expect(w.vm.error).toBe("Estado inválido para inspección");
    expect(w.vm.registrandoInspeccion).toBe(false);
  });
});

describe("PruebaView - OBD/SBD", () => {
  async function conObd(estado = "INSPECCION_VISUAL_APROBADA") {
    srv.expediente = expedienteBase({ estado });
    const w = montar();
    await flushPromises();
    await abrir(w);
    return w;
  }

  it("HU-029: evaluar muestra el motivo cuando OBD/SBD aplica", async () => {
    srv.postHandlers["/obd/evaluar/"] = () =>
      Promise.resolve({ data: { aplica: true, motivo: "Modelo 2021 con OBD." } });
    const w = await conObd();
    await w.vm.evaluarObd();
    await flushPromises();
    expect(w.vm.aviso).toBe("OBD/SBD aplica: Modelo 2021 con OBD.");
  });

  it("HU-029: evaluar indica que pasa directo a Prueba cuando no aplica", async () => {
    srv.postHandlers["/obd/evaluar/"] = () =>
      Promise.resolve({ data: { aplica: false, motivo: "Vehículo anterior a 2006." } });
    const w = await conObd();
    await w.vm.evaluarObd();
    await flushPromises();
    expect(w.vm.aviso).toContain("OBD/SBD no aplica: Vehículo anterior a 2006.");
    expect(w.vm.aviso).toContain("pasa directo a Prueba");
  });

  it("solicitar OBD llama al endpoint y avisa", async () => {
    const w = await conObd("OBD_PENDIENTE");
    await w.vm.solicitarObd();
    await flushPromises();
    expect(api.post).toHaveBeenCalledWith("/obd/solicitar/exp-1");
    expect(w.vm.aviso).toBe("OBD/SBD solicitado.");
  });

  it("resultado APROBADO viaja tal cual y sin mensaje técnico", async () => {
    const w = await conObd("OBD_RECIBIDO");
    w.vm.resultadoObd = "APROBADO";
    await w.vm.guardarResultadoObd();
    await flushPromises();
    expect(api.post).toHaveBeenCalledWith("/obd/resultado/exp-1", {
      resultado: "APROBADO",
      sin_comunicacion: false,
      mensaje_tecnico: null,
    });
    expect(w.vm.aviso).toContain("listo para prueba");
  });

  it("SIN_COMUNICACION se envía como ERROR con bandera y mensaje técnico recortado", async () => {
    const w = await conObd("OBD_RECIBIDO");
    w.vm.resultadoObd = "SIN_COMUNICACION";
    w.vm.mensajeObd = "  Conector dañado  ";
    await w.vm.guardarResultadoObd();
    expect(api.post).toHaveBeenCalledWith("/obd/resultado/exp-1", {
      resultado: "ERROR",
      sin_comunicacion: true,
      mensaje_tecnico: "Conector dañado",
    });
  });

  it("muestra el error si falla guardar el resultado de OBD", async () => {
    srv.postHandlers["/obd/resultado/"] = () => rechazo(422, "Resultado inválido");
    const w = await conObd("OBD_RECIBIDO");
    await w.vm.guardarResultadoObd();
    await flushPromises();
    expect(w.vm.error).toBe("Resultado inválido");
    expect(w.vm.guardandoObd).toBe(false);
  });
});

describe("PruebaView - Configuración de la prueba", () => {
  async function listo(extra = {}) {
    srv.expediente = expedienteBase({ estado: "LISTO_PARA_PRUEBA", ...extra });
    const w = montar();
    await flushPromises();
    await abrir(w);
    return w;
  }

  it("configura con el tipo por defecto del servidor y sin cambio manual", async () => {
    const w = await listo();
    await w.vm.configurarPrueba();
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith("/pruebas/configurar/exp-1", null, {
      params: { tipo_prueba: "DINAMICA", cambio_manual: false, motivo: undefined },
    });
    expect(w.vm.aviso).toBe("Prueba configurada: DINAMICA.");
  });

  it("cambio a ESTATICA envía cambio_manual y motivo", async () => {
    const w = await listo();
    w.vm.cambioAEstatica = true;
    w.vm.motivoCambio = "Dinamómetro sin capacidad";
    await flushPromises();
    expect(w.vm.tipoPruebaElegido).toBe("ESTATICA");

    await w.vm.configurarPrueba();
    expect(api.post).toHaveBeenCalledWith("/pruebas/configurar/exp-1", null, {
      params: { tipo_prueba: "ESTATICA", cambio_manual: true, motivo: "Dinamómetro sin capacidad" },
    });
  });

  it("si el servidor no permite cambiar a estática, el tipo elegido sigue el default", async () => {
    srv.configuracion = { ...srv.configuracion, puede_cambiar_a_estatica: false };
    const w = await listo();
    w.vm.cambioAEstatica = true;
    await flushPromises();
    expect(w.vm.tipoPruebaElegido).toBe("DINAMICA");
  });

  it("potenciaCompleta exige ralentí y crucero", async () => {
    const w = await listo();
    expect(w.vm.potenciaCompleta).toBe(true);

    w.vm.configuracionPrueba = {
      ...srv.configuracion,
      potencia_aplicada_bhp: { ralenti: 10, crucero: null },
    };
    await flushPromises();
    expect(w.vm.potenciaCompleta).toBe(false);
  });

  it("muestra el error del backend si falla la configuración", async () => {
    srv.postHandlers["/pruebas/configurar/"] = () => rechazo(409, "Estado no permite configurar");
    const w = await listo();
    await w.vm.configurarPrueba();
    await flushPromises();
    expect(w.vm.error).toBe("Estado no permite configurar");
    expect(w.vm.configurando).toBe(false);
  });
});

describe("PruebaView - Inicio de prueba y preparación NOM-045 (diésel)", () => {
  async function configurada(extra = {}) {
    srv.expediente = expedienteBase({ estado: "PRUEBA_CONFIGURADA", ...extra });
    const w = montar();
    await flushPromises();
    await abrir(w);
    return w;
  }

  it("gasolina: no exige preparación y envía preparacion_nom045 null", async () => {
    const w = await configurada({ tipo_prueba_final: "DINAMICA" });
    expect(w.vm.preparacionCompleta).toBe(true);

    await w.vm.iniciarPrueba();
    await flushPromises();
    expect(api.post).toHaveBeenCalledWith("/pruebas/iniciar/exp-1", { preparacion_nom045: null });
    expect(w.vm.aviso).toBe("Prueba iniciada.");
  });

  it("diésel: la preparación se completa solo con los 6 puntos confirmados", async () => {
    const w = await configurada({
      tipo_prueba_final: "OPACIDAD",
      vehiculo: { combustible: "DIESEL" },
    });
    expect(w.vm.preparacionCompleta).toBe(false);

    const ids = ["transmision", "temperatura", "regimen", "escape", "pedal"];
    ids.forEach((id) => (w.vm.preparacionNom045[id] = true));
    await flushPromises();
    expect(w.vm.preparacionCompleta).toBe(false);

    w.vm.preparacionNom045.humo = true;
    await flushPromises();
    expect(w.vm.preparacionCompleta).toBe(true);
  });

  it("diésel: envía los 6 puntos de preparación al iniciar", async () => {
    const w = await configurada({ tipo_prueba_final: "OPACIDAD", vehiculo: { combustible: "DIESEL" } });
    for (const id of ["transmision", "temperatura", "regimen", "escape", "pedal", "humo"]) {
      w.vm.preparacionNom045[id] = true;
    }
    await w.vm.iniciarPrueba();

    const [, body] = api.post.mock.calls.find(([u]) => u === "/pruebas/iniciar/exp-1");
    expect(body.preparacion_nom045).toEqual({
      transmision: true,
      temperatura: true,
      regimen: true,
      escape: true,
      pedal: true,
      humo: true,
    });
  });

  it("muestra el 422 del backend si la preparación no se acepta", async () => {
    srv.postHandlers["/pruebas/iniciar/"] = () => rechazo(422, "Preparación NOM-045 incompleta");
    const w = await configurada({ tipo_prueba_final: "DINAMICA" });
    await w.vm.iniciarPrueba();
    await flushPromises();
    expect(w.vm.error).toBe("Preparación NOM-045 incompleta");
    expect(w.vm.iniciando).toBe(false);
  });
});

describe("PruebaView - Captura manual del resultado", () => {
  async function enProceso(extra = {}) {
    srv.expediente = expedienteBase({ estado: "PRUEBA_EN_PROCESO", ...extra });
    const w = montar();
    await flushPromises();
    await abrir(w);
    return w;
  }

  function llenarFase(fase, valores) {
    Object.assign(fase, valores);
  }

  it("gasolina: lecturaCompleta exige HC, CO, CO2 y O2 en ralentí y crucero", async () => {
    const w = await enProceso({ tipo_prueba_final: "DINAMICA" });
    expect(w.vm.esMetodoGasolina).toBe(true);
    expect(w.vm.lecturaCompleta).toBe(false);

    llenarFase(w.vm.lecturaGasolina.ralenti, { hc_ppm: 50, co_pct: 0.2, co2_pct: 14, o2_pct: 0.5 });
    await flushPromises();
    expect(w.vm.lecturaCompleta).toBe(false);

    llenarFase(w.vm.lecturaGasolina.crucero, { hc_ppm: 40, co_pct: 0.1, co2_pct: 14, o2_pct: 0.4 });
    await flushPromises();
    expect(w.vm.lecturaCompleta).toBe(true);
  });

  it("gasolina: el payload omite opcionales vacíos y conserva los capturados", async () => {
    srv.postHandlers["/pruebas/resultado/"] = () =>
      Promise.resolve({ data: { estado_expediente: "PENDIENTE_DE_IMPRESION" } });
    const w = await enProceso({ tipo_prueba_final: "ESTATICA" });
    llenarFase(w.vm.lecturaGasolina.ralenti, {
      hc_ppm: 50, co_pct: 0.2, co2_pct: 14, o2_pct: 0.5, nox_ppm: 10,
    });
    llenarFase(w.vm.lecturaGasolina.crucero, {
      hc_ppm: 40, co_pct: 0.1, co2_pct: 14, o2_pct: 0.4, lambda_factor: 1.01, speed_kph: "",
    });

    await w.vm.guardarResultadoPrueba();
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith("/pruebas/resultado/exp-1", {
      normalized_payload: {
        ralenti: { hc_ppm: 50, co_pct: 0.2, co2_pct: 14, o2_pct: 0.5, nox_ppm: 10 },
        crucero: { hc_ppm: 40, co_pct: 0.1, co2_pct: 14, o2_pct: 0.4, lambda_factor: 1.01 },
      },
    });
    expect(w.vm.expediente).toBeNull();
  });

  it("diésel: lecturaCompleta solo exige el coeficiente K y el payload omite vacíos", async () => {
    srv.postHandlers["/pruebas/resultado/"] = () =>
      Promise.resolve({ data: { estado_expediente: "PENDIENTE_DE_IMPRESION" } });
    const w = await enProceso({ tipo_prueba_final: "OPACIDAD", vehiculo: { combustible: "DIESEL" } });
    expect(w.vm.esMetodoGasolina).toBe(false);
    expect(w.vm.lecturaCompleta).toBe(false);

    w.vm.lecturaDiesel.coefficient_absorption_final_k_m1 = 1.2;
    w.vm.lecturaDiesel.rpm_peak = 3200;
    await flushPromises();
    expect(w.vm.lecturaCompleta).toBe(true);

    await w.vm.guardarResultadoPrueba();
    expect(api.post).toHaveBeenCalledWith("/pruebas/resultado/exp-1", {
      normalized_payload: { coefficient_absorption_final_k_m1: 1.2, rpm_peak: 3200 },
    });
  });

  it("resultado fuera de límites avisa rechazo y envía a Impresión Central", async () => {
    srv.postHandlers["/pruebas/resultado/"] = () =>
      Promise.resolve({ data: { estado_expediente: "PENDIENTE_DE_IMPRESION_RECHAZO" } });
    const w = await enProceso({ tipo_prueba_final: "DINAMICA" });
    await w.vm.guardarResultadoPrueba();
    await flushPromises();
    expect(w.vm.expediente).toBeNull();
  });

  // DEFECTO CONOCIDO (mismo que en inspección): guardarResultadoPrueba asigna
  // aviso y cerrarExpediente() lo borra. Quitar .fails al corregirlo.
  it.fails("el aviso de prueba rechazada sobrevive al cierre del expediente", async () => {
    srv.postHandlers["/pruebas/resultado/"] = () =>
      Promise.resolve({ data: { estado_expediente: "PENDIENTE_DE_IMPRESION_RECHAZO" } });
    const w = await enProceso({ tipo_prueba_final: "DINAMICA" });
    await w.vm.guardarResultadoPrueba();
    await flushPromises();
    expect(w.vm.aviso).toContain("Prueba rechazada");
  });

  it("detail de texto se muestra tal cual", async () => {
    srv.postHandlers["/pruebas/resultado/"] = () => rechazo(422, "Lectura fuera de rango");
    const w = await enProceso({ tipo_prueba_final: "DINAMICA" });
    await w.vm.guardarResultadoPrueba();
    await flushPromises();
    expect(w.vm.error).toBe("Lectura fuera de rango");
    expect(w.vm.guardandoResultado).toBe(false);
  });

  it("detail estructurado (422 de validación) se serializa a JSON", async () => {
    const detalle = [{ loc: ["body", "ralenti"], msg: "campo requerido" }];
    srv.postHandlers["/pruebas/resultado/"] = () => rechazo(422, detalle);
    const w = await enProceso({ tipo_prueba_final: "DINAMICA" });
    await w.vm.guardarResultadoPrueba();
    await flushPromises();
    expect(w.vm.error).toBe(JSON.stringify(detalle));
  });

  it("sin detail usa el mensaje genérico", async () => {
    srv.postHandlers["/pruebas/resultado/"] = () => Promise.reject({ response: { status: 500, data: {} } });
    const w = await enProceso({ tipo_prueba_final: "DINAMICA" });
    await w.vm.guardarResultadoPrueba();
    await flushPromises();
    expect(w.vm.error).toBe("No se pudo guardar el resultado de la prueba.");
  });
});

describe("PruebaView - Integración con equipo (Equipment Integration Contract v1)", () => {
  async function conGateway(modo, corrida = null, estado = "PRUEBA_EN_PROCESO") {
    srv.equipo = { modo, estado: "LISTO", mensaje_tecnico: null };
    srv.corrida = corrida;
    srv.expediente = expedienteBase({ estado, tipo_prueba_final: "DINAMICA" });
    const w = montar();
    await flushPromises();
    await abrir(w);
    return w;
  }

  it("modo manual: conEquipo es falso y no se consulta la corrida", async () => {
    const w = await conGateway("manual");
    expect(w.vm.conEquipo).toBe(false);
    expect(api.get).not.toHaveBeenCalledWith("/pruebas/equipo/corrida/exp-1");
  });

  it("con gateway y prueba en proceso consulta la corrida al abrir", async () => {
    const w = await conGateway("simulador", { estado: "FINALIZADA", resultado: RESULTADO_GAS, test_run_id: "run-1", lecturas: [] });
    expect(w.vm.conEquipo).toBe(true);
    expect(api.get).toHaveBeenCalledWith("/pruebas/equipo/corrida/exp-1");
    expect(w.vm.corridaFinalizada).toBeTruthy();
  });

  it("si el estado del equipo no se puede leer cae a modo manual", async () => {
    srv.fallaGet["/pruebas/equipo/estado"] = () => rechazo(500, "x");
    srv.expediente = expedienteBase({ estado: "PRUEBA_EN_PROCESO", tipo_prueba_final: "DINAMICA" });
    const w = montar();
    await flushPromises();
    await abrir(w);
    expect(w.vm.equipo.modo).toBe("manual");
    expect(w.vm.conEquipo).toBe(false);
  });

  it("iniciar lectura con simulador manda el escenario elegido", async () => {
    srv.postHandlers["/pruebas/equipo/iniciar/"] = () =>
      Promise.resolve({ data: { estado: "FINALIZADA", resultado: RESULTADO_GAS, test_run_id: "run-2", lecturas: [] } });
    const w = await conGateway("simulador");
    w.vm.escenarioSimulador = "RECHAZADO";
    srv.corrida = { estado: "FINALIZADA", resultado: RESULTADO_GAS, test_run_id: "run-2", lecturas: [] };

    await w.vm.iniciarLecturaEquipo();
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith("/pruebas/equipo/iniciar/exp-1", null, {
      params: { escenario: "RECHAZADO" },
    });
  });

  it("iniciar lectura con gateway real no manda escenario", async () => {
    srv.postHandlers["/pruebas/equipo/iniciar/"] = () =>
      Promise.resolve({ data: { estado: "FINALIZADA", resultado: RESULTADO_GAS, test_run_id: "run-3", lecturas: [] } });
    const w = await conGateway("gateway");
    srv.corrida = { estado: "FINALIZADA", resultado: RESULTADO_GAS, test_run_id: "run-3", lecturas: [] };

    await w.vm.iniciarLecturaEquipo();
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith("/pruebas/equipo/iniciar/exp-1", null, { params: {} });
  });

  it("falla al iniciar lectura muestra el error y libera el botón", async () => {
    srv.postHandlers["/pruebas/equipo/iniciar/"] = () => rechazo(503, "Equipo no responde");
    const w = await conGateway("gateway");
    await w.vm.iniciarLecturaEquipo();
    await flushPromises();
    expect(w.vm.error).toBe("Equipo no responde");
    expect(w.vm.iniciandoLectura).toBe(false);
  });

  it("con equipo el resultado se toma de la corrida (test_run_id), no del formulario", async () => {
    srv.postHandlers["/pruebas/resultado/"] = () =>
      Promise.resolve({ data: { estado_expediente: "PENDIENTE_DE_IMPRESION" } });
    const w = await conGateway("simulador", { estado: "FINALIZADA", resultado: RESULTADO_GAS, test_run_id: "run-9", lecturas: [] });

    await w.vm.guardarResultadoPrueba();
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith("/pruebas/resultado/exp-1", { test_run_id: "run-9" });
  });

  it("infoEstadoEquipo traduce estados conocidos y tolera desconocidos o nulos", async () => {
    const w = await conGateway("manual");
    expect(w.vm.infoEstadoEquipo("LISTO")).toEqual({ texto: "Listo", color: "success" });
    expect(w.vm.infoEstadoEquipo("ERROR").color).toBe("error");
    expect(w.vm.infoEstadoEquipo("RARO")).toEqual({ texto: "RARO", color: "grey" });
    expect(w.vm.infoEstadoEquipo(null)).toEqual({ texto: "Sin dato", color: "grey" });
  });

  it("textoParametros usa etiquetas legibles y conserva claves desconocidas", async () => {
    const w = await conGateway("manual");
    expect(w.vm.textoParametros({ hc_ppm: 50, co_pct: 0.2, otro: 1 })).toBe(
      "HC (ppm): 50 · CO (%): 0.2 · otro: 1"
    );
  });

  it("el sondeo de la corrida sigue mientras no sea terminal y se detiene al finalizar", async () => {
    const w = await conGateway("simulador");
    vi.useFakeTimers();

    srv.corrida = { estado: "PRUEBA_EN_PROCESO", test_run_id: "run-5", lecturas: [] };
    await w.vm.cargarCorrida();
    const tras1 = api.get.mock.calls.filter(([u]) => u === "/pruebas/equipo/corrida/exp-1").length;

    await vi.advanceTimersByTimeAsync(2000);
    const tras2 = api.get.mock.calls.filter(([u]) => u === "/pruebas/equipo/corrida/exp-1").length;
    expect(tras2).toBeGreaterThan(tras1);

    srv.corrida = { estado: "FINALIZADA", resultado: RESULTADO_GAS, test_run_id: "run-5", lecturas: [] };
    await vi.advanceTimersByTimeAsync(1000);
    const alFinalizar = api.get.mock.calls.filter(([u]) => u === "/pruebas/equipo/corrida/exp-1").length;

    await vi.advanceTimersByTimeAsync(5000);
    const despues = api.get.mock.calls.filter(([u]) => u === "/pruebas/equipo/corrida/exp-1").length;
    expect(despues).toBe(alFinalizar);
  });

  it("error al leer la corrida detiene el sondeo y muestra el detalle", async () => {
    const w = await conGateway("simulador");
    vi.useFakeTimers();
    srv.corrida = { estado: "PRUEBA_EN_PROCESO", test_run_id: "run-6", lecturas: [] };
    await w.vm.cargarCorrida();

    srv.fallaGet["/pruebas/equipo/corrida/exp-1"] = () => rechazo(500, "Equipo desconectado");
    await vi.advanceTimersByTimeAsync(1000);
    const n = api.get.mock.calls.filter(([u]) => u === "/pruebas/equipo/corrida/exp-1").length;
    await vi.advanceTimersByTimeAsync(5000);

    expect(w.vm.error).toBe("Equipo desconectado");
    expect(api.get.mock.calls.filter(([u]) => u === "/pruebas/equipo/corrida/exp-1").length).toBe(n);
  });

  it("al desmontar se detiene el sondeo", async () => {
    const w = await conGateway("simulador");
    vi.useFakeTimers();
    srv.corrida = { estado: "PRUEBA_EN_PROCESO", test_run_id: "run-7", lecturas: [] };
    await w.vm.cargarCorrida();

    w.unmount();
    const n = api.get.mock.calls.filter(([u]) => u === "/pruebas/equipo/corrida/exp-1").length;
    await vi.advanceTimersByTimeAsync(5000);
    expect(api.get.mock.calls.filter(([u]) => u === "/pruebas/equipo/corrida/exp-1").length).toBe(n);
  });
});

describe("PruebaView - Reintento (F2) e interrupción", () => {
  it("F2: reintentar autoriza el reintento del expediente en ERROR_INTEGRACION", async () => {
    srv.expediente = expedienteBase({ estado: "ERROR_INTEGRACION" });
    const w = montar();
    await flushPromises();
    await abrir(w);

    await w.vm.reintentarPrueba();
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith("/pruebas/reintentar/exp-1");
    expect(w.vm.aviso).toContain("Reintento autorizado");
    expect(w.vm.reintentando).toBe(false);
  });

  it("F2: muestra el error si el reintento es rechazado", async () => {
    srv.postHandlers["/pruebas/reintentar/"] = () => rechazo(403, "Solo supervisor");
    srv.expediente = expedienteBase({ estado: "ERROR_INTEGRACION" });
    const w = montar();
    await flushPromises();
    await abrir(w);
    await w.vm.reintentarPrueba();
    await flushPromises();
    expect(w.vm.error).toBe("Solo supervisor");
  });

  it("abrirInterrupcion prepara el diálogo con causa y mensaje técnico y limpia el motivo", async () => {
    const w = montar();
    await flushPromises();
    w.vm.interrupcion.motivo = "viejo";
    w.vm.abrirInterrupcion("FALLA_EQUIPO", "Sonda obstruida");
    expect(w.vm.interrupcion).toMatchObject({
      abierto: true,
      causa: "FALLA_EQUIPO",
      motivo: "",
      mensajeTecnico: "Sonda obstruida",
    });
  });

  it("interrumpir envía causa, motivo y mensaje recortados, cierra el diálogo y avisa el intento", async () => {
    srv.postHandlers["/pruebas/interrumpir/"] = () => Promise.resolve({ data: { intento: 2 } });
    srv.expediente = expedienteBase({ estado: "PRUEBA_EN_PROCESO", tipo_prueba_final: "DINAMICA" });
    const w = montar();
    await flushPromises();
    await abrir(w);

    w.vm.abrirInterrupcion("CANCELADA");
    w.vm.interrupcion.motivo = "  Vehículo se sobrecalentó  ";
    w.vm.interrupcion.mensajeTecnico = "   ";
    await w.vm.interrumpirPrueba();
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith("/pruebas/interrumpir/exp-1", {
      causa: "CANCELADA",
      motivo: "Vehículo se sobrecalentó",
      mensaje_tecnico: null,
    });
    expect(w.vm.interrupcion.abierto).toBe(false);
    expect(w.vm.aviso).toBe("Prueba interrumpida (intento 2). El expediente volvió a la cola.");
    expect(w.vm.interrupcion.enviando).toBe(false);
  });

  it("si falla la interrupción deja el diálogo abierto y muestra el error", async () => {
    srv.postHandlers["/pruebas/interrumpir/"] = () => rechazo(409, "La prueba ya terminó");
    srv.expediente = expedienteBase({ estado: "PRUEBA_EN_PROCESO", tipo_prueba_final: "DINAMICA" });
    const w = montar();
    await flushPromises();
    await abrir(w);

    w.vm.abrirInterrupcion("CANCELADA");
    w.vm.interrupcion.motivo = "x";
    await w.vm.interrumpirPrueba();
    await flushPromises();

    expect(w.vm.interrupcion.abierto).toBe(true);
    expect(w.vm.error).toBe("La prueba ya terminó");
  });
});

describe("PruebaView - Corrección de datos del vehículo", () => {
  it("al abrir el expediente sincroniza el formulario con los datos del vehículo", async () => {
    srv.expediente = expedienteBase({ folio_multa: "M-1", certificado_anterior: "C-9" });
    const w = montar();
    await flushPromises();
    await abrir(w);

    expect(w.vm.vehiculoForm.marca).toBe("NISSAN");
    expect(w.vm.vehiculoForm.modelo).toBe(2021);
    expect(w.vm.vehiculoForm.traccion).toBeNull();
    expect(w.vm.certificadoForm).toEqual({ folio_multa: "M-1", certificado_anterior: "C-9" });
  });

  it("guardar corrige vehículo y datos del certificado por PATCH y recarga", async () => {
    const w = montar();
    await flushPromises();
    await abrir(w);

    w.vm.vehiculoForm.marca = "TOYOTA";
    w.vm.certificadoForm.folio_multa = "";
    w.vm.certificadoForm.certificado_anterior = "C-1";
    w.vm.editandoVehiculo = true;
    await w.vm.guardarVehiculo();
    await flushPromises();

    const [urlVeh, bodyVeh] = api.patch.mock.calls[0];
    expect(urlVeh).toBe("/expedientes/exp-1/vehiculo");
    expect(bodyVeh.marca).toBe("TOYOTA");
    expect(api.patch).toHaveBeenCalledWith("/expedientes/exp-1/datos-certificado", {
      folio_multa: null,
      certificado_anterior: "C-1",
    });
    expect(w.vm.aviso).toBe("Datos del vehículo corregidos.");
    expect(w.vm.editandoVehiculo).toBe(false);
  });

  it("si falla el PATCH muestra el error y no cierra la edición", async () => {
    const w = montar();
    await flushPromises();
    await abrir(w);
    api.patch.mockRejectedValueOnce({ response: { data: { detail: "NIV duplicado" } } });

    w.vm.editandoVehiculo = true;
    await w.vm.guardarVehiculo();
    await flushPromises();

    expect(w.vm.error).toBe("NIV duplicado");
    expect(w.vm.editandoVehiculo).toBe(true);
    expect(w.vm.guardandoVehiculo).toBe(false);
  });
});
