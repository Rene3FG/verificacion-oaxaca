import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import * as directives from "vuetify/directives";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/api/client", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

import { api } from "../src/api/client";
import CapturaView from "../src/views/CapturaView.vue";
import { useSessionStore } from "../src/stores/session";

const MOCK_ENTIDADES = [{ nombre: "OAXACA" }, { nombre: "PUEBLA" }];
const MOCK_MUNICIPIOS = [{ nombre: "OAXACA DE JUAREZ" }, { nombre: "SANTA CRUZ XOXOCOTLAN" }];
const MOCK_CARROCERIAS = [
  { clave: "SED", nombre: "SEDAN" },
  { clave: "SUV", nombre: "UTILITARIO" },
];

const MOCK_LISTA_EXPEDIENTES = [
  {
    id: "exp-001",
    placa: "TLX-101",
    estado: "CREADO",
    linea_id: 1,
    centro_id: "OAX-01",
  },
  {
    id: "exp-002",
    placa: "OAX-202",
    estado: "DATOS_SIOX_IMPORTADOS",
    linea_id: 1,
    centro_id: "OAX-01",
  },
  {
    id: "exp-003",
    placa: "MEX-303",
    estado: "EN_PRUEBA", // Estado posterior a Captura -> debe ser filtrado
    linea_id: 1,
    centro_id: "OAX-01",
  },
];

const MOCK_EXPEDIENTE_DETALLE = {
  id: "exp-001",
  placa: "TLX-101",
  estado: "CREADO",
  linea_id: 1,
  centro_id: "OAX-01",
  folio_multa: null,
  certificado_anterior: null,
  vehiculo: {
    niv: "3N1AB7AP1MY111111",
    marca: "NISSAN",
    linea: "VERSA",
    modelo: 2021,
    tipo_vehiculo: "SEDAN",
    combustible: "GASOLINA",
    pbv: "1500 KG",
    peso_bruto_vehicular_kg: 1500,
    traccion: "4X2",
    numero_cilindros: 4,
    clasificacion_carroceria: "SED",
    razon_social: "JUAN PEREZ",
    entidad_federativa: "OAXACA",
    tarjeta_circulacion: "TC-998877",
    propietario_estado: "OAXACA",
    propietario_municipio: "OAXACA DE JUAREZ",
    propietario_codigo_postal: "68000",
    propietario_colonia: "CENTRO",
    propietario_calle: "INDEPENDENCIA",
    propietario_numero_exterior: "123",
    propietario_poblacion: "OAXACA",
    fuente_datos: "MANUAL",
  },
};

const MOCK_HISTORIAL_SIOX = [
  {
    id: "siox-01",
    created_at: "2026-10-22T10:00:00Z",
    status: "EXITOSA",
    consultado_por: "usr-captura-01",
    response_normalized: {
      marca: "NISSAN",
      modelo: 2021,
    },
  },
];

function montar(options = {}) {
  const {
    prepSession,
    customExpediente = MOCK_EXPEDIENTE_DETALLE,
    listaExpedientes = MOCK_LISTA_EXPEDIENTES,
    apiGetHandler,
    apiPostHandler,
    apiPatchHandler,
  } = options;

  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore();
  session.estacion = {
    id: "ws-cap-01",
    name: "Caseta Captura 01",
    station_type: "captura",
    center_id: "OAX-01",
    line_id: 1,
  };
  session.sesion = { id: "ses-1", can_supervise: false };
  session.usuario = "capturista1";
  prepSession?.(session);

  api.get.mockImplementation((url, config) => {
    if (apiGetHandler) {
      const customRes = apiGetHandler(url, config);
      if (customRes !== undefined) return customRes;
    }
    if (url === "/catalogos/entidades") return Promise.resolve({ data: MOCK_ENTIDADES });
    if (url === "/catalogos/municipios") return Promise.resolve({ data: MOCK_MUNICIPIOS });
    if (url === "/catalogos/carrocerias") return Promise.resolve({ data: MOCK_CARROCERIAS });
    if (url === "/expedientes") {
      return Promise.resolve({ data: JSON.parse(JSON.stringify(listaExpedientes)) });
    }
    if (url.startsWith("/expedientes/")) {
      const expId = url.replace("/expedientes/", "");
      return Promise.resolve({
        data: {
          ...JSON.parse(JSON.stringify(customExpediente)),
          id: expId,
        },
      });
    }
    if (url.startsWith("/siox/consultas/")) {
      return Promise.resolve({ data: JSON.parse(JSON.stringify(MOCK_HISTORIAL_SIOX)) });
    }
    return Promise.resolve({ data: {} });
  });

  api.post.mockImplementation((url, payload) => {
    if (apiPostHandler) {
      const customRes = apiPostHandler(url, payload);
      if (customRes !== undefined) return customRes;
    }
    if (url === "/expedientes") {
      return Promise.resolve({
        data: { id: "exp-nuevo", placa: payload?.placa || "PUE-999", estado: "CREADO", vehiculo: {} },
      });
    }
    if (url.startsWith("/siox/consultar/")) {
      return Promise.resolve({ data: { intento: 1, status: "EXITOSA" } });
    }
    if (url.startsWith("/siox/captura-manual/")) {
      return Promise.resolve({ data: { ok: true } });
    }
    if (url.endsWith("/normalizar")) {
      return Promise.resolve({ data: { estado: "INSPECCION_VISUAL_PENDIENTE" } });
    }
    return Promise.resolve({ data: {} });
  });

  api.patch.mockImplementation((url, payload) => {
    if (apiPatchHandler) {
      const customRes = apiPatchHandler(url, payload);
      if (customRes !== undefined) return customRes;
    }
    return Promise.resolve({ data: { ok: true } });
  });

  const vuetify = createVuetify({ components, directives });
  return mount(CapturaView, {
    global: {
      plugins: [pinia, vuetify],
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("CapturaView - Carga Inicial y Listado de Expedientes", () => {
  it("consulta /expedientes al montar con center_id y line_id y filtra por estados de captura", async () => {
    const w = montar();
    await flushPromises();

    expect(api.get).toHaveBeenCalledWith("/expedientes", {
      params: { centro_id: "OAX-01", linea_id: 1 },
    });

    const t = w.text();
    expect(t).toContain("Estación de Captura · Centro OAX-01 · Línea 1");
    expect(t).toContain("Nuevo expediente");
    expect(t).toContain("Expedientes en curso en esta línea");
    expect(t).toContain("Placa TLX-101");
    expect(t).toContain("Placa OAX-202");
    // El expediente exp-003 está en EN_PRUEBA (no en estados de captura), por lo que no debe aparecer
    expect(t).not.toContain("Placa MEX-303");
  });

  it("muestra mensaje adecuado cuando no hay expedientes en curso", async () => {
    const w = montar({ listaExpedientes: [] });
    await flushPromises();

    const t = w.text();
    expect(t).toContain("No hay expedientes pendientes de registro en esta línea.");
  });

  it("no consulta la API de expedientes si no hay centro_id o line_id en la sesión", async () => {
    montar({
      prepSession: (s) => {
        s.estacion = null;
      },
    });
    await flushPromises();

    expect(api.get).not.toHaveBeenCalledWith("/expedientes", expect.anything());
  });

  it("muestra alerta de error si falla la consulta inicial de expedientes", async () => {
    const w = montar({
      apiGetHandler: (url) => {
        if (url === "/expedientes") {
          return Promise.reject({ response: { data: { detail: "Falla de conexión al centro" } } });
        }
      },
    });
    await flushPromises();

    expect(w.text()).toContain("Falla de conexión al centro");
  });
});

describe("CapturaView - Creación de Expediente (HU-010)", () => {
  it("no llama a POST /expedientes si la placa está vacía", async () => {
    const w = montar();
    await flushPromises();

    const btnCrear = w.findAllComponents({ name: "VBtn" }).find((b) => b.text().includes("Crear expediente"));
    expect(btnCrear).toBeDefined();
    await btnCrear.trigger("click");
    await flushPromises();

    expect(api.post).not.toHaveBeenCalledWith("/expedientes", expect.anything());
  });

  it("crea un expediente con éxito, limpia el input y abre el nuevo expediente", async () => {
    const w = montar();
    await flushPromises();

    const inputPlaca = w.findComponent({ name: "VTextField" });
    await inputPlaca.setValue("PUE-999");

    const btnCrear = w.findAllComponents({ name: "VBtn" }).find((b) => b.text().includes("Crear expediente"));
    await btnCrear.trigger("click");
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith("/expedientes", { placa: "PUE-999" });
    // Se abre el expediente recién retornado ("exp-nuevo")
    expect(api.get).toHaveBeenCalledWith("/expedientes/exp-nuevo");
    expect(api.get).toHaveBeenCalledWith("/siox/consultas/exp-nuevo");
  });

  it("muestra error 422 con formato de validación Pydantic", async () => {
    const w = montar({
      apiPostHandler: (url) => {
        if (url === "/expedientes") {
          return Promise.reject({
            response: {
              data: {
                detail: [{ msg: "Value error, Formato de placa inválido (debe cumplir patrón oficial)" }],
              },
            },
          });
        }
      },
    });
    await flushPromises();

    const inputPlaca = w.findComponent({ name: "VTextField" });
    await inputPlaca.setValue("INVALIDA_$$$");

    const btnCrear = w.findAllComponents({ name: "VBtn" }).find((b) => b.text().includes("Crear expediente"));
    await btnCrear.trigger("click");
    await flushPromises();

    expect(w.text()).toContain("Formato de placa inválido (debe cumplir patrón oficial)");
    expect(w.text()).not.toContain("Value error, ");
  });
});

describe("CapturaView - Detalle del Expediente y Navegación", () => {
  it("abre un expediente existente al hacer clic en un elemento de la lista y carga sus datos", async () => {
    const w = montar();
    await flushPromises();

    const item = w.findComponent({ name: "VListItem" });
    expect(item.exists()).toBe(true);
    await item.trigger("click");
    await flushPromises();

    expect(api.get).toHaveBeenCalledWith("/expedientes/exp-001");
    expect(api.get).toHaveBeenCalledWith("/siox/consultas/exp-001");

    const t = w.text();
    expect(t).toContain("Volver a la lista");
    expect(t).toContain("Consulta SIOX");
    expect(t).toContain("Datos del vehículo");
    expect(t).toContain("Propietario y domicilio");
  });

  it("permite cerrar el expediente y volver a la lista de expedientes en curso", async () => {
    const w = montar();
    await flushPromises();

    // Abrir expediente
    const item = w.findComponent({ name: "VListItem" });
    await item.trigger("click");
    await flushPromises();
    expect(w.text()).toContain("Volver a la lista");

    // Click en volver a la lista
    const btnVolver = w.findAllComponents({ name: "VBtn" }).find((b) => b.text().includes("Volver a la lista"));
    await btnVolver.trigger("click");
    await flushPromises();

    expect(w.text()).toContain("Nuevo expediente");
    expect(w.text()).toContain("Expedientes en curso en esta línea");
  });
});

describe("CapturaView - Integración y Flujo SIOX", () => {
  it("ejecuta consulta SIOX y muestra mensaje de intento exitoso", async () => {
    const w = montar();
    await flushPromises();

    // Abrir expediente
    const item = w.findComponent({ name: "VListItem" });
    await item.trigger("click");
    await flushPromises();

    const btnConsultar = w.findAllComponents({ name: "VBtn" }).find((b) => b.text().includes("Reintentar") || b.text().includes("Consultar"));
    expect(btnConsultar).toBeDefined();
    await btnConsultar.trigger("click");
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith("/siox/consultar/exp-001");
    expect(w.text()).toContain("Intento 1: Datos encontrados");
  });

  it("muestra error al fallar consulta SIOX y no recarga si el código no es 409", async () => {
    const w = montar({
      apiPostHandler: (url) => {
        if (url.startsWith("/siox/consultar/")) {
          return Promise.reject({
            response: {
              status: 500,
              data: { detail: "Timeout en el servicio estatal SIOX" },
            },
          });
        }
      },
    });
    await flushPromises();

    const item = w.findComponent({ name: "VListItem" });
    await item.trigger("click");
    await flushPromises();

    const btnConsultar = w.findAllComponents({ name: "VBtn" }).find((b) => b.text().includes("Reintentar") || b.text().includes("Consultar"));
    await btnConsultar.trigger("click");
    await flushPromises();

    expect(w.text()).toContain("Timeout en el servicio estatal SIOX");
  });

  it("recarga el expediente si la consulta SIOX responde con HTTP 409 (expediente avanzó)", async () => {
    const w = montar({
      apiPostHandler: (url) => {
        if (url.startsWith("/siox/consultar/")) {
          return Promise.reject({
            response: {
              status: 409,
              data: { detail: "El expediente ya fue actualizado por otra estación" },
            },
          });
        }
      },
    });
    await flushPromises();

    const item = w.findComponent({ name: "VListItem" });
    await item.trigger("click");
    await flushPromises();

    const btnConsultar = w.findAllComponents({ name: "VBtn" }).find((b) => b.text().includes("Reintentar") || b.text().includes("Consultar"));
    await btnConsultar.trigger("click");
    await flushPromises();

    // Al recibir 409, abrirExpediente se invoca nuevamente para actualizar el estado real del expediente
    const calls = api.get.mock.calls.filter((c) => c[0] === "/expedientes/exp-001");
    expect(calls.length).toBeGreaterThanOrEqual(2);
  });

  it("permite registrar captura manual con POST /siox/captura-manual/{id}", async () => {
    const w = montar();
    await flushPromises();

    const item = w.findComponent({ name: "VListItem" });
    await item.trigger("click");
    await flushPromises();

    const btnCapturaManual = w.findAllComponents({ name: "VBtn" }).find((b) => b.text().includes("Captura manual"));
    expect(btnCapturaManual).toBeDefined();
    await btnCapturaManual.trigger("click");
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith(
      "/siox/captura-manual/exp-001",
      expect.objectContaining({
        niv: "3N1AB7AP1MY111111",
        marca: "NISSAN",
        combustible: "GASOLINA",
      })
    );
    expect(w.text()).toContain("Captura manual registrada.");
  });
});

describe("CapturaView - Edición y Guardado de Datos", () => {
  it("guarda datos del vehículo con PATCH /expedientes/{id}/vehiculo", async () => {
    const w = montar();
    await flushPromises();

    const item = w.findComponent({ name: "VListItem" });
    await item.trigger("click");
    await flushPromises();

    const btnGuardarVehiculo = w
      .findAllComponents({ name: "VBtn" })
      .find((b) => b.text().includes("Guardar datos del vehículo"));
    expect(btnGuardarVehiculo).toBeDefined();
    await btnGuardarVehiculo.trigger("click");
    await flushPromises();

    expect(api.patch).toHaveBeenCalledWith(
      "/expedientes/exp-001/vehiculo",
      expect.objectContaining({
        marca: "NISSAN",
        linea: "VERSA",
        modelo: 2021,
      })
    );
    expect(w.text()).toContain("Datos del vehículo guardados.");
  });

  it("guarda datos del certificado (folio multa y certificado anterior) con PATCH /expedientes/{id}/datos-certificado", async () => {
    const w = montar();
    await flushPromises();

    const item = w.findComponent({ name: "VListItem" });
    await item.trigger("click");
    await flushPromises();

    const btnGuardarCert = w
      .findAllComponents({ name: "VBtn" })
      .find((b) => b.text().includes("Guardar datos del certificado"));
    expect(btnGuardarCert).toBeDefined();
    await btnGuardarCert.trigger("click");
    await flushPromises();

    expect(api.patch).toHaveBeenCalledWith("/expedientes/exp-001/datos-certificado", {
      folio_multa: null,
      certificado_anterior: null,
    });
    expect(w.text()).toContain("Datos del certificado guardados.");
  });
});

describe("CapturaView - Reglas de Negocio de Normalización (HU-010 / HU-020)", () => {
  it("bloquea la normalización si el expediente está en estado CREADO", async () => {
    const expCreado = { ...MOCK_EXPEDIENTE_DETALLE, estado: "CREADO" };
    const w = montar({ customExpediente: expCreado });
    await flushPromises();

    const item = w.findComponent({ name: "VListItem" });
    await item.trigger("click");
    await flushPromises();

    expect(w.text()).toContain("Aún no hay datos importados de SIOX ni capturados manualmente.");
    const btnConfirmar = w.findAllComponents({ name: "VBtn" }).find((b) => b.text().includes("Confirmar datos"));
    expect(btnConfirmar.attributes("disabled")).toBeDefined();
  });

  it("bloquea la normalización si falta el tipo de combustible", async () => {
    const expSinCombustible = {
      ...MOCK_EXPEDIENTE_DETALLE,
      estado: "DATOS_SIOX_IMPORTADOS",
      vehiculo: { ...MOCK_EXPEDIENTE_DETALLE.vehiculo, combustible: null },
    };
    const w = montar({ customExpediente: expSinCombustible });
    await flushPromises();

    const item = w.findComponent({ name: "VListItem" });
    await item.trigger("click");
    await flushPromises();

    expect(w.text()).toContain("El combustible es obligatorio para confirmar.");
    const btnConfirmar = w.findAllComponents({ name: "VBtn" }).find((b) => b.text().includes("Confirmar datos"));
    expect(btnConfirmar.attributes("disabled")).toBeDefined();
  });

  it("permite confirmar normalización cuando el estado es normalizable y cuenta con combustible", async () => {
    const expListo = {
      ...MOCK_EXPEDIENTE_DETALLE,
      estado: "DATOS_SIOX_IMPORTADOS",
      vehiculo: { ...MOCK_EXPEDIENTE_DETALLE.vehiculo, combustible: "GASOLINA" },
    };
    const w = montar({ customExpediente: expListo });
    await flushPromises();

    const item = w.findComponent({ name: "VListItem" });
    await item.trigger("click");
    await flushPromises();

    // No debe haber mensaje de deshabilitado
    expect(w.text()).not.toContain("El combustible es obligatorio para confirmar.");
    expect(w.text()).not.toContain("Aún no hay datos importados de SIOX ni capturados manualmente.");

    const btnConfirmar = w.findAllComponents({ name: "VBtn" }).find((b) => b.text().includes("Confirmar datos"));
    expect(btnConfirmar.attributes("disabled")).toBeUndefined();

    await btnConfirmar.trigger("click");
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith("/expedientes/exp-001/normalizar");
    // Al confirmar, se invoca cerrarExpediente() y vuelve a la lista de expedientes
    expect(w.text()).toContain("Nuevo expediente");
    expect(w.text()).toContain("Expedientes en curso en esta línea");
  });
});
