import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import * as directives from "vuetify/directives";
import { beforeEach, describe, expect, it, vi } from "vitest";

// jsdom no define visualViewport y los diálogos (VOverlay) lo usan.
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
    delete: vi.fn(),
  },
}));

import { api } from "../src/api/client";
import SupervisorView from "../src/views/SupervisorView.vue";
import { useSessionStore } from "../src/stores/session";

const MONITOR = [
  {
    id: "exp-1",
    placa: "AAA-001",
    estado: "INSPECCION_VISUAL_PENDIENTE",
    linea_id: 1,
    updated_at: "2026-10-23T10:00:00Z",
  },
  {
    id: "exp-2",
    placa: "BBB-002",
    estado: "PRUEBA_EN_PROCESO",
    linea_id: 2,
    updated_at: "2026-10-23T11:00:00Z",
  },
];

const INCIDENCIAS = [
  { id: "inc-1", placa: "AAA-001", expediente_id: "exp-1", linea_id: 1, accion: "REINTENTAR_IMPRESION" },
  { id: "inc-2", placa: "BBB-002", expediente_id: "exp-2", linea_id: 3, accion: "REINTENTAR_PRUEBA" },
];

const ESTACIONES = [
  { id: "e1", line_id: 1, name: "Línea 1 Prueba", capacidad_dinamometro_kg: 3500 },
  { id: "e2", line_id: null, name: "Estación Móvil", capacidad_dinamometro_kg: null },
];

const EQUIPOS = [
  {
    id: "eq-1",
    workstation_id: "e1",
    tipo: "ANALIZADOR_GASES",
    marca: "Sensors",
    modelo: "AMB II",
    numero_serie: "SN-1001",
    is_active: true,
  },
  {
    id: "eq-2",
    workstation_id: "e1",
    tipo: "DINAMOMETRO",
    marca: "Maha",
    modelo: "ASM AF",
    numero_serie: "SN-2002",
    is_active: false,
  },
];

// Servidor simulado: cada prueba ajusta srv antes de montar.
let srv;

function reiniciarServidor() {
  srv = {
    get: {
      "/supervision/monitor": MONITOR,
      "/supervision/auditoria": { total: 0, items: [] },
      "/usuarios": [{ id: "u1", username: "operador1" }],
      "/permisos": [],
      "/sync/estado": { pendientes: 0 },
      "/supervision/incidencias": INCIDENCIAS,
      "/folios/inventario": [],
      "/pruebas/limites-emision": [],
      "/estaciones": [],
      "/equipos": [],
      "/supervision/semestre": { fecha_final: null },
    },
    fallas: {}, // url -> detail (o null para respuesta sin detail)
    diferidos: {}, // url -> () => Promise
    post: {}, // prefijo -> (url, body, config) => Promise
    patch: {},
  };
}

function rechazo(detail) {
  return Promise.reject({ response: { status: 422, data: detail === undefined ? {} : { detail } } });
}

function instalarApi() {
  api.get.mockImplementation((url) => {
    if (url in srv.diferidos) return srv.diferidos[url]();
    if (url in srv.fallas) return rechazo(srv.fallas[url]);
    const buscado = Object.keys(srv.get).find((k) => url === k);
    if (buscado) return Promise.resolve({ data: srv.get[buscado] });
    if (url.startsWith("/supervision/expedientes/")) return Promise.resolve({ data: [] });
    return Promise.reject(new Error(`GET no simulado: ${url}`));
  });
  const mutacion = (tabla) => (url, body, config) => {
    const hit = Object.entries(tabla).find(([prefijo]) => url.startsWith(prefijo));
    if (hit) return hit[1](url, body, config);
    return Promise.resolve({ data: {} });
  };
  api.post.mockImplementation(mutacion(srv.post));
  api.patch.mockImplementation(mutacion(srv.patch));
  api.delete.mockResolvedValue({ data: {} });
}

async function montar({ station_type = "captura" } = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore();
  session.estacion = {
    id: "ws-1",
    name: "Estación",
    station_type,
    center_id: "OAX-01",
    line_id: 1,
  };
  session.sesion = { id: "ses-1", can_supervise: true };
  session.usuario = "supervisor1";
  instalarApi();

  const vuetify = createVuetify({ components, directives });
  const w = mount(SupervisorView, {
    global: { plugins: [pinia, vuetify], stubs: { AdministracionPanel: true } },
  });
  await flushPromises();
  return { w, session };
}

function llamadas(metodo, prefijo) {
  return api[metodo].mock.calls.filter(([url]) => url.startsWith(prefijo));
}

beforeEach(() => {
  vi.clearAllMocks();
  reiniciarServidor();
});

describe("SupervisorView - Carga inicial y monitor (HU-111)", () => {
  it("al montar consulta las once fuentes de datos de la vista", async () => {
    await montar();
    const urls = api.get.mock.calls.map(([u]) => u);
    for (const esperada of [
      "/supervision/monitor",
      "/supervision/auditoria",
      "/usuarios",
      "/permisos",
      "/sync/estado",
      "/supervision/incidencias",
      "/folios/inventario",
      "/pruebas/limites-emision",
      "/estaciones",
      "/equipos",
      "/supervision/semestre",
    ]) {
      expect(urls).toContain(esperada);
    }
  });

  it("filtra permisos y estaciones por el centro de la estación", async () => {
    await montar();
    expect(api.get).toHaveBeenCalledWith("/permisos", { params: { center_id: "OAX-01" } });
    expect(api.get).toHaveBeenCalledWith("/estaciones", {
      params: { center_id: "OAX-01", station_type: "prueba" },
    });
  });

  it("muestra el centro y los expedientes del monitor con su estado", async () => {
    const { w } = await montar();
    const t = w.text();
    expect(t).toContain("Supervisión · Centro OAX-01");
    expect(t).toContain("AAA-001");
    expect(t).toContain("BBB-002");
    expect(w.vm.expedientes).toHaveLength(2);
  });

  it("muestra mensaje vacío si no hay expedientes activos", async () => {
    srv.get["/supervision/monitor"] = [];
    const { w } = await montar();
    expect(w.text()).toContain("No hay expedientes activos en este centro.");
  });

  it("muestra el detalle del backend si falla el monitor", async () => {
    srv.fallas["/supervision/monitor"] = "Sin acceso al centro";
    const { w } = await montar();
    expect(w.text()).toContain("Sin acceso al centro");
  });

  it("usa mensaje genérico si el error no trae detail", async () => {
    srv.fallas["/supervision/monitor"] = undefined;
    const { w } = await montar();
    expect(w.vm.error).toBe("No se pudo cargar el monitor del centro.");
  });

  it("arranca en la pestaña Monitor", async () => {
    const { w } = await montar();
    expect(w.vm.tab).toBe("monitor");
  });
});

describe("SupervisorView - Mensajes de error de carga", () => {
  const CASOS = [
    ["cargarUsuarios", "/usuarios", "No se pudo cargar la lista de usuarios."],
    ["cargarPermisos", "/permisos", "No se pudo cargar la lista de permisos."],
    ["cargarEstadoSync", "/sync/estado", "No se pudo cargar el estado de sincronización."],
    ["cargarIncidencias", "/supervision/incidencias", "No se pudieron cargar las incidencias."],
    ["cargarInventarioFolios", "/folios/inventario", "No se pudo cargar el inventario de folios."],
    ["cargarLimitesEmision", "/pruebas/limites-emision", "No se pudo cargar el catálogo de límites de emisión."],
    ["cargarEstacionesPrueba", "/estaciones", "No se pudo cargar el listado de estaciones."],
    ["cargarSemestre", "/supervision/semestre", "No se pudo cargar la configuración de semestre."],
    ["cargarAuditoria", "/supervision/auditoria", "No se pudo cargar la auditoría."],
  ];

  it.each(CASOS)("%s: detail del backend tiene prioridad", async (fn, url) => {
    const { w } = await montar();
    srv.fallas[url] = `Falla en ${url}`;
    w.vm.error = null;
    await w.vm[fn]();
    expect(w.vm.error).toBe(`Falla en ${url}`);
  });

  it.each(CASOS)("%s: sin detail usa el mensaje genérico", async (fn, url, generico) => {
    const { w } = await montar();
    srv.fallas[url] = undefined;
    w.vm.error = null;
    await w.vm[fn]();
    expect(w.vm.error).toBe(generico);
  });

  it("los indicadores de carga se apagan aunque la consulta falle", async () => {
    const { w } = await montar();
    srv.fallas["/permisos"] = "x";
    srv.fallas["/sync/estado"] = "x";
    await w.vm.cargarPermisos();
    await w.vm.cargarEstadoSync();
    expect(w.vm.cargandoPermisos).toBe(false);
    expect(w.vm.cargandoEstadoSync).toBe(false);
  });
});

describe("SupervisorView - Bitácora (HU-117) y reasignación de línea (HU-114)", () => {
  it("abrir bitácora la muestra, carga los eventos del expediente y apaga el spinner", async () => {
    srv.get["/supervision/expedientes/exp-1/bitacora"] = [{ id: 1, evento: "CREADO" }];
    const { w } = await montar();
    await w.vm.abrirBitacora(MONITOR[0]);
    expect(api.get).toHaveBeenCalledWith("/supervision/expedientes/exp-1/bitacora");
    expect(w.vm.bitacoraAbierta).toBe(true);
    expect(w.vm.bitacoraExpediente.placa).toBe("AAA-001");
    expect(w.vm.bitacora).toEqual([{ id: 1, evento: "CREADO" }]);
    expect(w.vm.cargandoBitacora).toBe(false);
  });

  it("si falla la bitácora deja la lista vacía y muestra el error", async () => {
    srv.fallas["/supervision/expedientes/exp-1/bitacora"] = "Bitácora no disponible";
    const { w } = await montar();
    await w.vm.abrirBitacora(MONITOR[0]);
    expect(w.vm.bitacora).toEqual([]);
    expect(w.vm.error).toBe("Bitácora no disponible");
    expect(w.vm.cargandoBitacora).toBe(false);
  });

  it("abrirReasignar abre el diálogo con el formulario limpio", async () => {
    const { w } = await montar();
    w.vm.reasignarForm.nueva_linea_id = 9;
    w.vm.reasignarForm.motivo = "viejo";
    w.vm.abrirReasignar(MONITOR[1]);
    expect(w.vm.reasignarAbierto).toBe(true);
    expect(w.vm.reasignarExpediente.id).toBe("exp-2");
    expect(w.vm.reasignarForm).toEqual({ nueva_linea_id: null, motivo: "" });
  });

  it("confirmar reasigna, avisa, cierra el diálogo y recarga el monitor", async () => {
    const { w } = await montar();
    w.vm.abrirReasignar(MONITOR[0]);
    w.vm.reasignarForm.nueva_linea_id = 2;
    w.vm.reasignarForm.motivo = "Línea 1 en mantenimiento";
    api.get.mockClear();

    await w.vm.confirmarReasignar();
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith("/expedientes/exp-1/reasignar-linea", {
      nueva_linea_id: 2,
      motivo: "Línea 1 en mantenimiento",
    });
    expect(w.vm.aviso).toBe("Expediente reasignado a la línea 2.");
    expect(w.vm.reasignarAbierto).toBe(false);
    expect(api.get).toHaveBeenCalledWith("/supervision/monitor");
  });

  it("si falla la reasignación deja el diálogo abierto con el error", async () => {
    srv.post["/expedientes/exp-1/reasignar-linea"] = () => rechazo("Línea inexistente");
    const { w } = await montar();
    w.vm.abrirReasignar(MONITOR[0]);
    w.vm.reasignarForm.nueva_linea_id = 99;
    await w.vm.confirmarReasignar();
    expect(w.vm.error).toBe("Línea inexistente");
    expect(w.vm.reasignarAbierto).toBe(true);
    expect(w.vm.reasignando).toBe(false);
  });
});

describe("SupervisorView - Permisos (HU-121)", () => {
  it("usuariosPorId indexa la lista de usuarios por id", async () => {
    srv.get["/usuarios"] = [
      { id: "u1", username: "a" },
      { id: "u2", username: "b" },
    ];
    const { w } = await montar();
    expect(w.vm.usuariosPorId.u2.username).toBe("b");
  });

  it("nuevo permiso arranca con valores por defecto y el centro de la estación", async () => {
    const { w } = await montar();
    w.vm.permisoForm.user_id = "u9";
    w.vm.permisoForm.can_supervise = true;
    w.vm.abrirNuevoPermiso();
    expect(w.vm.permisoAbierto).toBe(true);
    expect(w.vm.permisoForm).toEqual({
      user_id: null,
      station_type: "captura",
      center_id: "OAX-01",
      line_id: null,
      can_operate: true,
      can_supervise: false,
    });
  });

  it("crear permiso envía el formulario, avisa, cierra y recarga", async () => {
    const { w } = await montar();
    w.vm.abrirNuevoPermiso();
    w.vm.permisoForm.user_id = "u1";
    w.vm.permisoForm.station_type = "prueba";
    api.get.mockClear();

    await w.vm.crearPermiso();

    expect(api.post).toHaveBeenCalledWith("/permisos", expect.objectContaining({
      user_id: "u1",
      station_type: "prueba",
      center_id: "OAX-01",
    }));
    expect(w.vm.aviso).toBe("Permiso creado.");
    expect(w.vm.permisoAbierto).toBe(false);
    expect(api.get).toHaveBeenCalledWith("/permisos", expect.anything());
  });

  it("si falla crear el permiso conserva el diálogo y muestra el error", async () => {
    srv.post["/permisos"] = () => rechazo("Permiso duplicado");
    const { w } = await montar();
    w.vm.abrirNuevoPermiso();
    await w.vm.crearPermiso();
    expect(w.vm.error).toBe("Permiso duplicado");
    expect(w.vm.permisoAbierto).toBe(true);
    expect(w.vm.guardandoPermiso).toBe(false);
  });

  it("actualizar envía solo el campo cambiado y recarga", async () => {
    const { w } = await montar();
    api.get.mockClear();
    await w.vm.actualizarPermiso({ id: "p1" }, "can_supervise", true);
    expect(api.patch).toHaveBeenCalledWith("/permisos/p1", { can_supervise: true });
    expect(api.get).toHaveBeenCalledWith("/permisos", expect.anything());
  });

  it("si falla actualizar recarga igualmente para revertir el interruptor", async () => {
    srv.patch["/permisos/"] = () => rechazo("No puedes quitarte tu propio permiso");
    const { w } = await montar();
    api.get.mockClear();
    await w.vm.actualizarPermiso({ id: "p1" }, "can_operate", false);
    expect(api.patch).toHaveBeenCalledWith("/permisos/p1", { can_operate: false });
    expect(api.get).toHaveBeenCalledWith("/permisos", expect.anything());
  });

  it("el mensaje de error al actualizar un permiso sobrevive a la recarga", async () => {
    srv.patch["/permisos/"] = () => rechazo("No puedes quitarte tu propio permiso");
    const { w } = await montar();
    await w.vm.actualizarPermiso({ id: "p1" }, "can_operate", false);
    expect(w.vm.error).toBe("No puedes quitarte tu propio permiso");
  });

  it("eliminar borra, avisa y recarga", async () => {
    const { w } = await montar();
    api.get.mockClear();
    await w.vm.eliminarPermiso({ id: "p7" });
    expect(api.delete).toHaveBeenCalledWith("/permisos/p7");
    expect(w.vm.aviso).toBe("Permiso eliminado.");
    expect(api.get).toHaveBeenCalledWith("/permisos", expect.anything());
  });

  it("si falla eliminar muestra el error y no avisa éxito", async () => {
    api.delete.mockRejectedValueOnce({ response: { data: { detail: "Permiso en uso" } } });
    const { w } = await montar();
    await w.vm.eliminarPermiso({ id: "p7" });
    expect(w.vm.error).toBe("Permiso en uso");
    expect(w.vm.aviso).toBeNull();
  });
});

describe("SupervisorView - Errores y reintentos", () => {
  it("carga las incidencias y selecciona la primera", async () => {
    const { w } = await montar();
    expect(w.vm.incidencias).toHaveLength(2);
    expect(w.vm.incidenciaSel.id).toBe("inc-1");
  });

  it("sin incidencias no hay selección", async () => {
    srv.get["/supervision/incidencias"] = [];
    const { w } = await montar();
    expect(w.vm.incidenciaSel).toBeNull();
  });

  it("al recargar conserva la incidencia seleccionada por id", async () => {
    const { w } = await montar();
    w.vm.incidenciaSel = INCIDENCIAS[1];
    srv.get["/supervision/incidencias"] = INCIDENCIAS.map((i) => ({ ...i }));
    await w.vm.cargarIncidencias();
    expect(w.vm.incidenciaSel.id).toBe("inc-2");
  });

  it("si la seleccionada ya no existe pasa a la primera", async () => {
    const { w } = await montar();
    w.vm.incidenciaSel = INCIDENCIAS[1];
    srv.get["/supervision/incidencias"] = [INCIDENCIAS[0]];
    await w.vm.cargarIncidencias();
    expect(w.vm.incidenciaSel.id).toBe("inc-1");
  });

  it("los filtros viajan como params sin vacíos ni espacios sobrantes", async () => {
    const { w } = await montar();
    api.get.mockClear();
    w.vm.filtrosIncidencias.q = "  AAA  ";
    w.vm.filtrosIncidencias.linea_id = 2;
    w.vm.filtrosIncidencias.origen = "Sincronización";
    await w.vm.cargarIncidencias();
    expect(api.get).toHaveBeenCalledWith("/supervision/incidencias", {
      params: { estado: "abiertas", q: "AAA", linea_id: 2, origen: "Sincronización" },
    });

    api.get.mockClear();
    w.vm.filtrosIncidencias.q = "   ";
    w.vm.filtrosIncidencias.linea_id = null;
    w.vm.filtrosIncidencias.origen = null;
    await w.vm.cargarIncidencias();
    expect(api.get).toHaveBeenCalledWith("/supervision/incidencias", { params: { estado: "abiertas" } });
  });

  it("la línea 0 sí cuenta como filtro (no se confunde con vacío)", async () => {
    const { w } = await montar();
    api.get.mockClear();
    w.vm.filtrosIncidencias.linea_id = 0;
    await w.vm.cargarIncidencias();
    expect(api.get).toHaveBeenCalledWith("/supervision/incidencias", { params: { estado: "abiertas", linea_id: 0 } });
  });

  it("limpiar filtros los restablece y vuelve a consultar", async () => {
    const { w } = await montar();
    w.vm.filtrosIncidencias.q = "x";
    w.vm.filtrosIncidencias.linea_id = 2;
    w.vm.filtrosIncidencias.origen = "Impresión Central";
    w.vm.filtrosIncidencias.estado = "resueltas";
    api.get.mockClear();
    w.vm.limpiarFiltrosIncidencias();
    await flushPromises();
    expect(w.vm.filtrosIncidencias).toEqual({ q: "", linea_id: null, origen: null, estado: "abiertas" });
    expect(api.get).toHaveBeenCalledWith("/supervision/incidencias", { params: { estado: "abiertas" } });
  });

  it("el filtro de estado consulta incidencias resueltas o todas", async () => {
    const { w } = await montar();
    api.get.mockClear();
    w.vm.filtrosIncidencias.estado = "resueltas";
    await w.vm.cargarIncidencias();
    expect(api.get).toHaveBeenCalledWith("/supervision/incidencias", { params: { estado: "resueltas" } });

    api.get.mockClear();
    w.vm.filtrosIncidencias.estado = "todas";
    await w.vm.cargarIncidencias();
    expect(api.get).toHaveBeenCalledWith("/supervision/incidencias", { params: { estado: "todas" } });
  });

  it("las incidencias resueltas muestran chip Resuelta y deshabilitan la acción de reintento", async () => {
    const incidenciaResuelta = {
      ...INCIDENCIAS[0],
      id: "inc-resuelta",
      resuelta_at: "2026-10-28T18:00:00Z",
    };
    srv.get["/supervision/incidencias"] = [incidenciaResuelta];
    const { w } = await montar({ station_type: "impresion" });
    w.vm.tab = "errores";
    await flushPromises();

    expect(w.text()).toContain("Resuelta");
    const chip = w.findAllComponents({ name: "VChip" }).find((c) => c.text().includes("Resuelta"));
    expect(chip).toBeDefined();
    expect(chip.props("color")).toBe("success");

    const btnReintentar = w.findAllComponents({ name: "VBtn" }).find((b) => b.text().includes("Reintentar impresión"));
    expect(btnReintentar).toBeDefined();
    expect(btnReintentar.attributes("disabled")).toBeDefined();
  });

  it("una respuesta vieja que llega tarde no pisa a la consulta más reciente", async () => {
    const { w } = await montar();
    let resolverLenta;
    srv.diferidos["/supervision/incidencias"] = () =>
      new Promise((r) => {
        resolverLenta = r;
      });
    const lenta = w.vm.cargarIncidencias();

    delete srv.diferidos["/supervision/incidencias"];
    srv.get["/supervision/incidencias"] = [{ id: "inc-9", placa: "NUEVA", linea_id: 1, accion: "SINCRONIZAR" }];
    await w.vm.cargarIncidencias();
    expect(w.vm.incidencias.map((i) => i.id)).toEqual(["inc-9"]);

    resolverLenta({ data: INCIDENCIAS });
    await lenta;
    expect(w.vm.incidencias.map((i) => i.id)).toEqual(["inc-9"]);
    expect(w.vm.cargandoIncidencias).toBe(false);
  });

  it("lineasIncidencias une líneas del monitor y de las incidencias, sin repetir y ordenadas", async () => {
    srv.get["/supervision/incidencias"] = [
      { id: "i", placa: "X", linea_id: 3, accion: "SINCRONIZAR" },
      { id: "j", placa: "Y", linea_id: null, accion: "SINCRONIZAR" },
      { id: "k", placa: "Z", linea_id: 1, accion: "SINCRONIZAR" },
    ];
    const { w } = await montar();
    expect(w.vm.lineasIncidencias).toEqual([1, 2, 3]);
  });

  describe("acción bloqueada por estación (el hardware está en otra estación)", () => {
    it("reintentar impresión solo se permite desde la estación de impresión", async () => {
      const captura = await montar({ station_type: "captura" });
      expect(captura.w.vm.accionBloqueada({ accion: "REINTENTAR_IMPRESION" })).toBe(true);
      const impresion = await montar({ station_type: "impresion" });
      expect(impresion.w.vm.accionBloqueada({ accion: "REINTENTAR_IMPRESION" })).toBe(false);
    });

    it("reintentar prueba solo se permite desde la estación de prueba", async () => {
      const captura = await montar({ station_type: "captura" });
      expect(captura.w.vm.accionBloqueada({ accion: "REINTENTAR_PRUEBA" })).toBe(true);
      const prueba = await montar({ station_type: "prueba" });
      expect(prueba.w.vm.accionBloqueada({ accion: "REINTENTAR_PRUEBA" })).toBe(false);
    });

    it("sincronizar y registrar lote nunca se bloquean por estación", async () => {
      const { w } = await montar({ station_type: "captura" });
      expect(w.vm.accionBloqueada({ accion: "SINCRONIZAR" })).toBe(false);
      expect(w.vm.accionBloqueada({ accion: "REGISTRAR_LOTE" })).toBe(false);
    });
  });

  describe("reintentarIncidencia", () => {
    it("REGISTRAR_LOTE no llama a la API: salta a Administración > Catálogos > Folios", async () => {
      const { w } = await montar();
      api.post.mockClear();
      await w.vm.reintentarIncidencia({ accion: "REGISTRAR_LOTE" });
      expect(w.vm.tab).toBe("administracion");
      expect(w.vm.destinoAdmin).toEqual({ seccion: "catalogos", catalogo: "folios" });
      expect(api.post).not.toHaveBeenCalled();
    });

    it("REINTENTAR_PRUEBA autoriza el reintento, avisa con la placa y recarga incidencias", async () => {
      const { w } = await montar({ station_type: "prueba" });
      api.get.mockClear();
      await w.vm.reintentarIncidencia(INCIDENCIAS[1]);
      expect(api.post).toHaveBeenCalledWith("/pruebas/reintentar/exp-2");
      expect(w.vm.aviso).toBe("BBB-002 volvió a la cola de Prueba.");
      expect(w.vm.reintentando).toBe(false);
      expect(api.get).toHaveBeenCalledWith("/supervision/incidencias", expect.anything());
    });

    it("REINTENTAR_IMPRESION: avisa éxito cuando el expediente queda IMPRESO", async () => {
      srv.post["/impresion/imprimir/"] = () =>
        Promise.resolve({ data: { estado_expediente: "IMPRESO", intentos: 2 } });
      const { w } = await montar({ station_type: "impresion" });
      await w.vm.reintentarIncidencia(INCIDENCIAS[0]);
      expect(api.post).toHaveBeenCalledWith("/impresion/imprimir/exp-1");
      expect(w.vm.aviso).toBe("Certificado de AAA-001 impreso en el reintento.");
    });

    it("REINTENTAR_IMPRESION: avisa los intentos cuando la impresora vuelve a fallar", async () => {
      srv.post["/impresion/imprimir/"] = () =>
        Promise.resolve({ data: { estado_expediente: "IMPRESION_FALLIDA", intentos: 3 } });
      const { w } = await montar({ station_type: "impresion" });
      await w.vm.reintentarIncidencia(INCIDENCIAS[0]);
      expect(w.vm.aviso).toBe("La impresora volvió a fallar (3 intentos).");
    });

    it("SINCRONIZAR reutiliza la sincronización forzada", async () => {
      const { w } = await montar();
      await w.vm.reintentarIncidencia({ accion: "SINCRONIZAR" });
      expect(api.post).toHaveBeenCalledWith("/sync/procesar", null, { params: { forzar: true } });
    });

    it("si el reintento falla muestra el error, libera el botón y recarga igual", async () => {
      srv.post["/pruebas/reintentar/"] = () => rechazo("Solo desde la estación de prueba");
      const { w } = await montar({ station_type: "prueba" });
      api.get.mockClear();
      await w.vm.reintentarIncidencia(INCIDENCIAS[1]);
      expect(w.vm.error).toBe("Solo desde la estación de prueba");
      expect(w.vm.reintentando).toBe(false);
      expect(api.get).toHaveBeenCalledWith("/supervision/incidencias", expect.anything());
    });

    it("sin detail usa el mensaje genérico de reintento", async () => {
      srv.post["/pruebas/reintentar/"] = () => rechazo(undefined);
      const { w } = await montar({ station_type: "prueba" });
      await w.vm.reintentarIncidencia(INCIDENCIAS[1]);
      expect(w.vm.error).toBe("No se pudo reintentar.");
    });
  });
});

describe("SupervisorView - Sincronización", () => {
  it("carga el estado de sync_outbox", async () => {
    srv.get["/sync/estado"] = { pendientes: 4, errores: 1 };
    const { w } = await montar();
    expect(w.vm.estadoSync).toEqual({ pendientes: 4, errores: 1 });
  });

  it("sincronizar ahora fuerza el procesamiento, guarda el resultado y refresca el estado", async () => {
    srv.post["/sync/procesar"] = () => Promise.resolve({ data: { enviados: 3 } });
    const { w } = await montar();
    api.get.mockClear();

    await w.vm.sincronizarAhora();

    expect(api.post).toHaveBeenCalledWith("/sync/procesar", null, { params: { forzar: true } });
    expect(w.vm.resultadoSync).toEqual({ enviados: 3 });
    expect(api.get).toHaveBeenCalledWith("/sync/estado");
    expect(w.vm.sincronizando).toBe(false);
  });

  it("limpia el resultado anterior antes de volver a sincronizar", async () => {
    const { w } = await montar();
    w.vm.resultadoSync = { enviados: 99 };
    srv.post["/sync/procesar"] = () => rechazo("Central no disponible");
    await w.vm.sincronizarAhora();
    expect(w.vm.resultadoSync).toBeNull();
    expect(w.vm.error).toBe("Central no disponible");
    expect(w.vm.sincronizando).toBe(false);
  });

  it("sin detail usa el mensaje genérico de la cola", async () => {
    srv.post["/sync/procesar"] = () => rechazo(undefined);
    const { w } = await montar();
    await w.vm.sincronizarAhora();
    expect(w.vm.error).toBe("No se pudo procesar la cola de sincronización.");
  });
});

describe("SupervisorView - Inventario de folios", () => {
  it("registrar lote envía el formulario como params, avisa, limpia el rango y recarga", async () => {
    srv.post["/folios/lotes"] = () =>
      Promise.resolve({ data: { cantidad: 100, tipo_certificado: "INTENSIVO" } });
    const { w } = await montar();
    w.vm.loteForm.tipo_certificado = "INTENSIVO";
    w.vm.loteForm.folio_inicio = "A001";
    w.vm.loteForm.folio_fin = "A100";
    api.get.mockClear();

    await w.vm.registrarLoteFolios();

    expect(api.post).toHaveBeenCalledWith("/folios/lotes", null, {
      params: { tipo_certificado: "INTENSIVO", folio_inicio: "A001", folio_fin: "A100" },
    });
    expect(w.vm.aviso).toBe("100 folio(s) INTENSIVO registrados.");
    expect(w.vm.loteForm.folio_inicio).toBe("");
    expect(w.vm.loteForm.folio_fin).toBe("");
    expect(w.vm.loteForm.tipo_certificado).toBe("INTENSIVO");
    expect(api.get).toHaveBeenCalledWith("/folios/inventario");
  });

  it("si falla el alta del lote conserva el rango capturado", async () => {
    srv.post["/folios/lotes"] = () => rechazo("Rango traslapado con un lote existente");
    const { w } = await montar();
    w.vm.loteForm.folio_inicio = "A001";
    w.vm.loteForm.folio_fin = "A100";
    await w.vm.registrarLoteFolios();
    expect(w.vm.error).toBe("Rango traslapado con un lote existente");
    expect(w.vm.loteForm.folio_inicio).toBe("A001");
    expect(w.vm.registrandoLote).toBe(false);
  });
});

describe("SupervisorView - Límites de emisión", () => {
  it("rangoTexto: sin acotar, abierto por un lado o cerrado", async () => {
    const { w } = await montar();
    expect(w.vm.rangoTexto(null, null)).toBe("Sin acotar");
    expect(w.vm.rangoTexto(undefined, undefined)).toBe("Sin acotar");
    expect(w.vm.rangoTexto(2000, null)).toBe("2000 – —");
    expect(w.vm.rangoTexto(null, 2010)).toBe("— – 2010");
    expect(w.vm.rangoTexto(0, 2010)).toBe("0 – 2010");
  });

  it("nuevo límite arranca como GAS_DYNAMIC / RALENTI / hc_ppm sin acotar", async () => {
    const { w } = await montar();
    w.vm.limiteForm.valor_maximo = 123;
    w.vm.limiteForm.anio_modelo_desde = 1999;
    w.vm.abrirNuevoLimite();
    expect(w.vm.limiteAbierto).toBe(true);
    expect(w.vm.limiteForm).toMatchObject({
      metodo: "GAS_DYNAMIC",
      fase: "RALENTI",
      parametro: "hc_ppm",
      valor_maximo: null,
      anio_modelo_desde: null,
      anio_modelo_hasta: null,
      peso_bruto_desde_kg: null,
      peso_bruto_hasta_kg: null,
    });
  });

  it("cambiar a DIESEL_OPACITY quita la fase y deja el coeficiente K como único parámetro", async () => {
    const { w } = await montar();
    w.vm.onMetodoLimiteChange("DIESEL_OPACITY");
    expect(w.vm.limiteEsDiesel).toBe(true);
    expect(w.vm.limiteForm.fase).toBeNull();
    expect(w.vm.limiteForm.parametro).toBe("coefficient_absorption_final_k_m1");
    expect(w.vm.parametrosDisponibles).toEqual(["coefficient_absorption_final_k_m1"]);
  });

  it("volver a gasolina restablece fase RALENTI y los parámetros de gases", async () => {
    const { w } = await montar();
    w.vm.onMetodoLimiteChange("DIESEL_OPACITY");
    w.vm.onMetodoLimiteChange("GAS_STATIC");
    expect(w.vm.limiteEsDiesel).toBe(false);
    expect(w.vm.limiteForm.fase).toBe("RALENTI");
    expect(w.vm.parametrosDisponibles).toEqual(["hc_ppm", "co_pct", "o2_pct"]);
  });

  it("cambiar de método descarta los rangos de año y de peso", async () => {
    const { w } = await montar();
    Object.assign(w.vm.limiteForm, {
      anio_modelo_desde: 2000,
      anio_modelo_hasta: 2010,
      peso_bruto_desde_kg: 1000,
      peso_bruto_hasta_kg: 3000,
    });
    w.vm.onMetodoLimiteChange("DIESEL_OPACITY");
    expect(w.vm.limiteForm).toMatchObject({
      anio_modelo_desde: null,
      anio_modelo_hasta: null,
      peso_bruto_desde_kg: null,
      peso_bruto_hasta_kg: null,
    });
  });

  it("guardar límite envía el formulario, avisa, cierra y recarga el catálogo", async () => {
    const { w } = await montar();
    w.vm.abrirNuevoLimite();
    w.vm.limiteForm.valor_maximo = 100;
    api.get.mockClear();

    await w.vm.guardarLimite();

    expect(api.post).toHaveBeenCalledWith(
      "/pruebas/limites-emision",
      expect.objectContaining({ metodo: "GAS_DYNAMIC", fase: "RALENTI", parametro: "hc_ppm", valor_maximo: 100 })
    );
    expect(w.vm.aviso).toBe("Límite de emisión guardado.");
    expect(w.vm.limiteAbierto).toBe(false);
    expect(api.get).toHaveBeenCalledWith("/pruebas/limites-emision");
  });

  it("detail de texto se muestra tal cual", async () => {
    srv.post["/pruebas/limites-emision"] = () => rechazo("Rango traslapado");
    const { w } = await montar();
    w.vm.abrirNuevoLimite();
    await w.vm.guardarLimite();
    expect(w.vm.error).toBe("Rango traslapado");
    expect(w.vm.limiteAbierto).toBe(true);
    expect(w.vm.guardandoLimite).toBe(false);
  });

  it("detail estructurado (422 de validación) se serializa a JSON", async () => {
    const detalle = [{ loc: ["body", "valor_maximo"], msg: "campo requerido" }];
    srv.post["/pruebas/limites-emision"] = () => rechazo(detalle);
    const { w } = await montar();
    w.vm.abrirNuevoLimite();
    await w.vm.guardarLimite();
    expect(w.vm.error).toBe(JSON.stringify(detalle));
  });

  it("sin detail usa el mensaje genérico", async () => {
    srv.post["/pruebas/limites-emision"] = () => rechazo(undefined);
    const { w } = await montar();
    w.vm.abrirNuevoLimite();
    await w.vm.guardarLimite();
    expect(w.vm.error).toBe("No se pudo guardar el límite de emisión.");
  });
});

describe("SupervisorView - Capacidad del dinamómetro por línea", () => {
  it("carga las estaciones de prueba y copia la capacidad a un valor editable", async () => {
    srv.get["/estaciones"] = ESTACIONES;
    const { w } = await montar();
    expect(w.vm.estacionesPrueba).toHaveLength(2);
    expect(w.vm.estacionesPrueba[0]._valor).toBe(3500);
    expect(w.vm.estacionesPrueba[1]._valor).toBeNull();
  });

  it("guardar envía la capacidad, actualiza la fila con la respuesta y avisa la línea", async () => {
    srv.get["/estaciones"] = ESTACIONES;
    srv.patch["/estaciones/e1/capacidad-dinamometro"] = () =>
      Promise.resolve({ data: { capacidad_dinamometro_kg: 4000 } });
    const { w } = await montar();
    w.vm.estacionesPrueba[0]._valor = 4000;

    await w.vm.guardarCapacidad(w.vm.estacionesPrueba[0]);

    expect(api.patch).toHaveBeenCalledWith("/estaciones/e1/capacidad-dinamometro", {
      capacidad_dinamometro_kg: 4000,
    });
    expect(w.vm.estacionesPrueba[0].capacidad_dinamometro_kg).toBe(4000);
    expect(w.vm.estacionesPrueba[0]._valor).toBe(4000);
    expect(w.vm.aviso).toBe("Capacidad de línea 1 actualizada.");
    expect(w.vm.guardandoCapacidad.e1).toBe(false);
  });

  it("cadena vacía se envía como null (borrar la capacidad) y la línea nula se muestra como guion", async () => {
    srv.get["/estaciones"] = ESTACIONES;
    srv.patch["/estaciones/e2/capacidad-dinamometro"] = () =>
      Promise.resolve({ data: { capacidad_dinamometro_kg: null } });
    const { w } = await montar();
    w.vm.estacionesPrueba[1]._valor = "";

    await w.vm.guardarCapacidad(w.vm.estacionesPrueba[1]);

    expect(api.patch).toHaveBeenCalledWith("/estaciones/e2/capacidad-dinamometro", {
      capacidad_dinamometro_kg: null,
    });
    expect(w.vm.aviso).toBe("Capacidad de línea — actualizada.");
  });

  it("si falla conserva el valor tecleado y libera el botón de esa fila", async () => {
    srv.get["/estaciones"] = ESTACIONES;
    srv.patch["/estaciones/e1/capacidad-dinamometro"] = () => rechazo("Capacidad fuera de rango");
    const { w } = await montar();
    w.vm.estacionesPrueba[0]._valor = 99999;

    await w.vm.guardarCapacidad(w.vm.estacionesPrueba[0]);

    expect(w.vm.error).toBe("Capacidad fuera de rango");
    expect(w.vm.estacionesPrueba[0]._valor).toBe(99999);
    expect(w.vm.estacionesPrueba[0].capacidad_dinamometro_kg).toBe(3500);
    expect(w.vm.guardandoCapacidad.e1).toBe(false);
  });
});

describe("SupervisorView - Catálogo de equipos de prueba (F4, HU-042/102)", () => {
  it("carga el catálogo de equipos al montar", async () => {
    srv.get["/equipos"] = EQUIPOS;
    const { w } = await montar();
    expect(w.vm.equipos).toEqual(EQUIPOS);
    expect(w.vm.cargandoEquipos).toBe(false);
  });

  it("textoTipoEquipo y textoEstacion formatean correctamente", async () => {
    srv.get["/estaciones"] = ESTACIONES;
    const { w } = await montar();
    expect(w.vm.textoTipoEquipo("ANALIZADOR_GASES")).toBe("Analizador de gases");
    expect(w.vm.textoTipoEquipo("DINAMOMETRO")).toBe("Dinamómetro");
    expect(w.vm.textoTipoEquipo("OPACIMETRO")).toBe("Opacímetro");
    expect(w.vm.textoTipoEquipo("ESCANER_OBD")).toBe("Escáner OBD");
    expect(w.vm.textoTipoEquipo("OTRO")).toBe("OTRO");

    expect(w.vm.textoEstacion("e1")).toBe("Línea 1 · Línea 1 Prueba");
    expect(w.vm.textoEstacion("e-desconocida")).toBe("—");
  });

  it("abrirEquipo prepara el formulario para nuevo equipo o para edición", async () => {
    const { w } = await montar();
    w.vm.abrirEquipo();
    expect(w.vm.equipoAbierto).toBe(true);
    expect(w.vm.equipoForm).toEqual({
      id: null,
      workstation_id: null,
      tipo: null,
      marca: "",
      modelo: "",
      numero_serie: "",
      is_active: true,
    });

    w.vm.abrirEquipo(EQUIPOS[0]);
    expect(w.vm.equipoAbierto).toBe(true);
    expect(w.vm.equipoForm).toEqual({
      id: "eq-1",
      workstation_id: "e1",
      tipo: "ANALIZADOR_GASES",
      marca: "Sensors",
      modelo: "AMB II",
      numero_serie: "SN-1001",
      is_active: true,
    });
  });

  it("guardarEquipo crea un nuevo equipo por POST, avisa y recarga", async () => {
    srv.get["/equipos"] = EQUIPOS;
    srv.post["/equipos"] = () =>
      Promise.resolve({ data: { id: "eq-3", numero_serie: "SN-3003" } });
    const { w } = await montar();
    w.vm.abrirEquipo();
    Object.assign(w.vm.equipoForm, {
      workstation_id: "e1",
      tipo: "OPACIMETRO",
      marca: "Capelec",
      modelo: "CAP3200",
      numero_serie: "SN-3003",
    });
    api.get.mockClear();

    await w.vm.guardarEquipo();

    expect(api.post).toHaveBeenCalledWith("/equipos", {
      tipo: "OPACIMETRO",
      marca: "Capelec",
      modelo: "CAP3200",
      numero_serie: "SN-3003",
      workstation_id: "e1",
    });
    expect(w.vm.equipoAbierto).toBe(false);
    expect(w.vm.aviso).toBe("Equipo SN-3003 guardado.");
    expect(api.get).toHaveBeenCalledWith("/equipos");
    expect(w.vm.guardandoEquipo).toBe(false);
  });

  it("guardarEquipo edita un equipo existente por PATCH", async () => {
    srv.patch["/equipos/eq-1"] = () =>
      Promise.resolve({ data: { id: "eq-1", is_active: false } });
    const { w } = await montar();
    w.vm.abrirEquipo(EQUIPOS[0]);
    w.vm.equipoForm.is_active = false;

    await w.vm.guardarEquipo();

    expect(api.patch).toHaveBeenCalledWith("/equipos/eq-1", {
      tipo: "ANALIZADOR_GASES",
      marca: "Sensors",
      modelo: "AMB II",
      numero_serie: "SN-1001",
      is_active: false,
    });
    expect(w.vm.equipoAbierto).toBe(false);
    expect(w.vm.aviso).toBe("Equipo SN-1001 guardado.");
  });

  it("si falla guardarEquipo muestra el error y mantiene abierto el formulario", async () => {
    srv.post["/equipos"] = () => rechazo("Número de serie ya registrado");
    const { w } = await montar();
    w.vm.abrirEquipo();
    Object.assign(w.vm.equipoForm, {
      workstation_id: "e1",
      tipo: "ESCANER_OBD",
      numero_serie: "DUPLICADO",
    });

    await w.vm.guardarEquipo();

    expect(w.vm.error).toBe("Número de serie ya registrado");
    expect(w.vm.equipoAbierto).toBe(true);
    expect(w.vm.guardandoEquipo).toBe(false);
  });

  it("si falla cargarEquipos muestra el error del backend o el genérico", async () => {
    srv.fallas["/equipos"] = "Error al leer equipos";
    const { w } = await montar();
    expect(w.vm.error).toBe("Error al leer equipos");

    srv.fallas["/equipos"] = undefined;
    await w.vm.cargarEquipos();
    expect(w.vm.error).toBe("No se pudo cargar el catálogo de equipos.");
  });
});

describe("SupervisorView - Semestre y prórroga", () => {
  it("carga la configuración del semestre", async () => {
    srv.get["/supervision/semestre"] = { fecha_final: "2026-12-31" };
    const { w } = await montar();
    expect(w.vm.semestreInfo).toEqual({ fecha_final: "2026-12-31" });
  });

  it("guardar prórroga envía el formulario, reemplaza el semestre, avisa y limpia el formulario", async () => {
    srv.post["/supervision/semestre/prorroga"] = () =>
      Promise.resolve({ data: { fecha_final: "2027-01-31", prorroga: true } });
    const { w } = await montar();
    w.vm.prorrogaForm.fecha_final = "2027-01-31";
    w.vm.prorrogaForm.motivo = "Contingencia";

    await w.vm.guardarProrroga();

    expect(api.post).toHaveBeenCalledWith("/supervision/semestre/prorroga", {
      fecha_final: "2027-01-31",
      motivo: "Contingencia",
    });
    expect(w.vm.semestreInfo).toEqual({ fecha_final: "2027-01-31", prorroga: true });
    expect(w.vm.aviso).toBe("Prórroga configurada.");
    expect(w.vm.prorrogaForm).toEqual({ fecha_final: null, motivo: "" });
    expect(w.vm.guardandoProrroga).toBe(false);
  });

  it("si falla la prórroga conserva el formulario y muestra el error", async () => {
    srv.post["/supervision/semestre/prorroga"] = () => rechazo("La prórroga no puede ser anterior al cierre");
    const { w } = await montar();
    w.vm.prorrogaForm.fecha_final = "2020-01-01";
    w.vm.prorrogaForm.motivo = "x";
    await w.vm.guardarProrroga();
    expect(w.vm.error).toBe("La prórroga no puede ser anterior al cierre");
    expect(w.vm.prorrogaForm.fecha_final).toBe("2020-01-01");
    expect(w.vm.guardandoProrroga).toBe(false);
  });
});

describe("SupervisorView - Reimpresión por daño y corrección de tipo", () => {
  const IMPRESO = { id: "exp-9", placa: "ZZZ-900", estado: "IMPRESO", certificado_tipo: "PARTICULAR" };

  it("buscar con placa vacía o en blanco no consulta", async () => {
    const { w } = await montar();
    api.get.mockClear();
    w.vm.busquedaPlaca = "   ";
    await w.vm.buscarExpediente();
    expect(api.get).not.toHaveBeenCalled();
  });

  it("buscar recorta la placa y guarda los resultados", async () => {
    srv.get["/supervision/expedientes/buscar"] = [IMPRESO];
    const { w } = await montar();
    w.vm.busquedaPlaca = "  ZZZ-900 ";
    await w.vm.buscarExpediente();
    expect(api.get).toHaveBeenCalledWith("/supervision/expedientes/buscar", {
      params: { placa: "ZZZ-900" },
    });
    expect(w.vm.resultadosBusqueda).toEqual([IMPRESO]);
    expect(w.vm.buscandoExpediente).toBe(false);
  });

  it("si falla la búsqueda vacía los resultados y muestra el error", async () => {
    srv.fallas["/supervision/expedientes/buscar"] = "Placa inválida";
    const { w } = await montar();
    w.vm.resultadosBusqueda = [IMPRESO];
    w.vm.busquedaPlaca = "X";
    await w.vm.buscarExpediente();
    expect(w.vm.resultadosBusqueda).toEqual([]);
    expect(w.vm.error).toBe("Placa inválida");
  });

  it("solo se reimprime en IMPRESO, CERRADO_APROBADO o CERRADO_RECHAZADO", async () => {
    const { w } = await montar();
    expect(w.vm.puedeReimprimir).toBeFalsy();
    for (const estado of ["IMPRESO", "CERRADO_APROBADO", "CERRADO_RECHAZADO"]) {
      w.vm.abrirExpedienteReimpresion({ ...IMPRESO, estado });
      expect(w.vm.puedeReimprimir).toBe(true);
    }
    for (const estado of ["FOLIO_ASIGNADO", "PRUEBA_EN_PROCESO", "PENDIENTE_IMPRESION"]) {
      w.vm.abrirExpedienteReimpresion({ ...IMPRESO, estado });
      expect(w.vm.puedeReimprimir).toBe(false);
    }
  });

  it("el tipo RECHAZO nunca admite corrección manual", async () => {
    const { w } = await montar();
    w.vm.abrirExpedienteReimpresion({ ...IMPRESO, certificado_tipo: "RECHAZO", estado: "CERRADO_RECHAZADO" });
    expect(w.vm.puedeReimprimir).toBe(true);
    expect(w.vm.puedeCorregirTipo).toBe(false);

    w.vm.abrirExpedienteReimpresion(IMPRESO);
    expect(w.vm.puedeCorregirTipo).toBe(true);
  });

  it("abrir un expediente limpia motivo y tipo previos; cerrar lo quita", async () => {
    const { w } = await montar();
    w.vm.motivoReimpresion = "viejo";
    w.vm.nuevoTipoCorreccion = "INTENSIVO";
    w.vm.abrirExpedienteReimpresion(IMPRESO);
    expect(w.vm.motivoReimpresion).toBe("");
    expect(w.vm.nuevoTipoCorreccion).toBeNull();
    w.vm.cerrarExpedienteReimpresion();
    expect(w.vm.expedienteReimpresion).toBeNull();
  });

  it("reimprimir por daño: éxito avisa el folio y actualiza el estado del expediente", async () => {
    srv.post["/impresion/folio/reimprimir-por-dano/"] = () =>
      Promise.resolve({ data: { impreso: true, folio: "F-200", estado_expediente: "IMPRESO" } });
    const { w } = await montar();
    w.vm.abrirExpedienteReimpresion({ ...IMPRESO });
    w.vm.motivoReimpresion = "Papel rasgado";

    await w.vm.reimprimirPorDano();

    expect(api.post).toHaveBeenCalledWith("/impresion/folio/reimprimir-por-dano/exp-9", {
      motivo: "Papel rasgado",
    });
    expect(w.vm.aviso).toBe("Reimpreso con folio F-200.");
    expect(w.vm.expedienteReimpresion.estado).toBe("IMPRESO");
    expect(w.vm.motivoReimpresion).toBe("");
    expect(w.vm.reimprimiendoPorDano).toBe(false);
  });

  it("reimprimir por daño: si la impresora no responde avisa que el folio ya se canjeó", async () => {
    srv.post["/impresion/folio/reimprimir-por-dano/"] = () =>
      Promise.resolve({ data: { impreso: false, folio: "F-201", estado_expediente: "IMPRESION_FALLIDA" } });
    const { w } = await montar();
    w.vm.abrirExpedienteReimpresion({ ...IMPRESO });
    await w.vm.reimprimirPorDano();
    expect(w.vm.aviso).toBe("Folio F-201 canjeado, pero la impresora no respondió — reintentar.");
    expect(w.vm.expedienteReimpresion.estado).toBe("IMPRESION_FALLIDA");
  });

  it("reimprimir por daño: el error conserva el motivo capturado", async () => {
    srv.post["/impresion/folio/reimprimir-por-dano/"] = () => rechazo("Sin folios disponibles");
    const { w } = await montar();
    w.vm.abrirExpedienteReimpresion({ ...IMPRESO });
    w.vm.motivoReimpresion = "Papel rasgado";
    await w.vm.reimprimirPorDano();
    expect(w.vm.error).toBe("Sin folios disponibles");
    expect(w.vm.motivoReimpresion).toBe("Papel rasgado");
    expect(w.vm.reimprimiendoPorDano).toBe(false);
  });

  it("corregir tipo: envía el tipo nuevo como param y actualiza tipo y estado", async () => {
    srv.post["/impresion/tipo-certificado-post-impresion/"] = () =>
      Promise.resolve({
        data: { impreso: true, certificado_tipo: "INTENSIVO", folio: "F-300", estado_expediente: "IMPRESO" },
      });
    const { w } = await montar();
    w.vm.abrirExpedienteReimpresion({ ...IMPRESO });
    w.vm.nuevoTipoCorreccion = "INTENSIVO";

    await w.vm.corregirTipoPostImpresion();

    expect(api.post).toHaveBeenCalledWith(
      "/impresion/tipo-certificado-post-impresion/exp-9",
      null,
      { params: { nuevo_tipo: "INTENSIVO" } }
    );
    expect(w.vm.aviso).toBe("Tipo corregido a INTENSIVO, folio nuevo F-300.");
    expect(w.vm.expedienteReimpresion.certificado_tipo).toBe("INTENSIVO");
    expect(w.vm.nuevoTipoCorreccion).toBeNull();
    expect(w.vm.corrigiendoTipoPost).toBe(false);
  });

  it("corregir tipo: si la impresora no responde avisa el folio canjeado", async () => {
    srv.post["/impresion/tipo-certificado-post-impresion/"] = () =>
      Promise.resolve({
        data: { impreso: false, certificado_tipo: "DOBLE_CERO", folio: "F-301", estado_expediente: "IMPRESION_FALLIDA" },
      });
    const { w } = await montar();
    w.vm.abrirExpedienteReimpresion({ ...IMPRESO });
    w.vm.nuevoTipoCorreccion = "DOBLE_CERO";
    await w.vm.corregirTipoPostImpresion();
    expect(w.vm.aviso).toBe(
      "Tipo corregido a DOBLE_CERO, folio F-301 canjeado, pero la impresora no respondió — reintentar."
    );
  });

  it("corregir tipo: el error no cambia el tipo del expediente", async () => {
    srv.post["/impresion/tipo-certificado-post-impresion/"] = () => rechazo("Tipo no permitido");
    const { w } = await montar();
    w.vm.abrirExpedienteReimpresion({ ...IMPRESO });
    w.vm.nuevoTipoCorreccion = "RECHAZO";
    await w.vm.corregirTipoPostImpresion();
    expect(w.vm.error).toBe("Tipo no permitido");
    expect(w.vm.expedienteReimpresion.certificado_tipo).toBe("PARTICULAR");
  });
});

describe("SupervisorView - Auditoría (N4)", () => {
  it("la primera consulta pagina de 50 en 50 sin filtros", async () => {
    await montar();
    expect(api.get).toHaveBeenCalledWith("/supervision/auditoria", {
      params: { limite: 50, desplazamiento: 0 },
    });
  });

  it("los filtros con valor viajan y los vacíos se omiten", async () => {
    const { w } = await montar();
    api.get.mockClear();
    Object.assign(w.vm.filtrosAuditoria, {
      desde: "2026-10-01",
      hasta: "",
      usuario_id: "u1",
      placa: "AAA-001",
      modulo: null,
    });
    await w.vm.cargarAuditoria();
    expect(api.get).toHaveBeenCalledWith("/supervision/auditoria", {
      params: { limite: 50, desplazamiento: 0, desde: "2026-10-01", usuario_id: "u1", placa: "AAA-001" },
    });
  });

  it("el desplazamiento sigue la página actual", async () => {
    const { w } = await montar();
    api.get.mockClear();
    w.vm.paginaAuditoria = 3;
    await w.vm.cargarAuditoria();
    expect(api.get).toHaveBeenCalledWith("/supervision/auditoria", {
      params: { limite: 50, desplazamiento: 100 },
    });
  });

  it("filtrar regresa a la página 1", async () => {
    const { w } = await montar();
    w.vm.paginaAuditoria = 4;
    api.get.mockClear();
    w.vm.filtrarAuditoria();
    await flushPromises();
    expect(w.vm.paginaAuditoria).toBe(1);
    expect(api.get).toHaveBeenCalledWith("/supervision/auditoria", {
      params: { limite: 50, desplazamiento: 0 },
    });
  });

  it("limpiar filtros los restablece y consulta desde la página 1", async () => {
    const { w } = await montar();
    Object.assign(w.vm.filtrosAuditoria, { desde: "2026-10-01", placa: "X", modulo: "folios", usuario_id: "u1" });
    w.vm.paginaAuditoria = 2;
    api.get.mockClear();
    w.vm.limpiarFiltrosAuditoria();
    await flushPromises();
    expect(w.vm.filtrosAuditoria).toEqual({ desde: "", hasta: "", usuario_id: null, placa: "", modulo: null });
    expect(w.vm.paginaAuditoria).toBe(1);
    expect(api.get).toHaveBeenCalledWith("/supervision/auditoria", {
      params: { limite: 50, desplazamiento: 0 },
    });
  });

  it("paginasAuditoria redondea hacia arriba y nunca baja de 1", async () => {
    const { w } = await montar();
    w.vm.auditoria = { total: 0, items: [] };
    expect(w.vm.paginasAuditoria).toBe(1);
    w.vm.auditoria = { total: 50, items: [] };
    expect(w.vm.paginasAuditoria).toBe(1);
    w.vm.auditoria = { total: 51, items: [] };
    expect(w.vm.paginasAuditoria).toBe(2);
    w.vm.auditoria = { total: 230, items: [] };
    expect(w.vm.paginasAuditoria).toBe(5);
  });

  it("una respuesta vieja que llega tarde no pisa a la consulta más reciente", async () => {
    const { w } = await montar();
    let resolverLenta;
    srv.diferidos["/supervision/auditoria"] = () =>
      new Promise((r) => {
        resolverLenta = r;
      });
    const lenta = w.vm.cargarAuditoria();

    delete srv.diferidos["/supervision/auditoria"];
    srv.get["/supervision/auditoria"] = { total: 1, items: [{ id: "reciente" }] };
    await w.vm.cargarAuditoria();
    expect(w.vm.auditoria.items[0].id).toBe("reciente");

    resolverLenta({ data: { total: 99, items: [{ id: "vieja" }] } });
    await lenta;
    expect(w.vm.auditoria.items[0].id).toBe("reciente");
    expect(w.vm.cargandoAuditoria).toBe(false);
  });

  it("una consulta vieja que falla tarde tampoco pisa el estado de error", async () => {
    const { w } = await montar();
    let rechazarLenta;
    srv.diferidos["/supervision/auditoria"] = () =>
      new Promise((_, rej) => {
        rechazarLenta = rej;
      });
    const lenta = w.vm.cargarAuditoria();

    delete srv.diferidos["/supervision/auditoria"];
    w.vm.error = null;
    await w.vm.cargarAuditoria();

    rechazarLenta({ response: { data: { detail: "Error de consulta vieja" } } });
    await lenta;
    expect(w.vm.error).toBeNull();
  });
});
