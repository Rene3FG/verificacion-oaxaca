import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import * as directives from "vuetify/directives";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockPush = vi.fn();
vi.mock("vue-router", () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ name: "login" }),
}));

vi.mock("../src/api/client", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { api } from "../src/api/client";
import LoginView from "../src/views/LoginView.vue";
import { useSessionStore } from "../src/stores/session";

const ESTACION_IMPRESION = {
  id: "ws-imp-01",
  name: "Impresión Reforma 01",
  station_type: "impresion",
  center_id: "reforma",
  allowed_line_ids: [1, 2],
};

const ESTACION_PRUEBA = {
  id: "ws-pru-01",
  name: "Prueba Línea 1",
  station_type: "prueba",
  center_id: "reforma",
  line_id: 1,
};

const ESTACION_CAPTURA = {
  id: "ws-cap-01",
  name: "Caseta Captura",
  station_type: "captura",
  center_id: "reforma",
  allowed_line_ids: [],
};

function montar(prepSession) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore();
  prepSession?.(session);

  const vuetify = createVuetify({ components, directives });
  return mount(LoginView, {
    global: {
      plugins: [pinia, vuetify],
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("LoginView - Detección de Estación y Estados de Carga", () => {
  it("detecta la estación correctamente al montar y muestra metadatos", async () => {
    api.get.mockResolvedValueOnce({ data: ESTACION_IMPRESION });

    const w = montar();
    await flushPromises();

    expect(api.get).toHaveBeenCalledWith(expect.stringContaining("/estaciones/"));
    const t = w.text();
    expect(t).toContain("Iniciar sesión");
    expect(t).toContain("Impresión Reforma 01");
    expect(t).toContain("Reforma");
    expect(t).toContain("Líneas 1 y 2");
    expect(t).toContain("Impresión");
  });

  it("renderiza correctamente líneas singulares o vacías", async () => {
    api.get.mockResolvedValueOnce({ data: ESTACION_PRUEBA });

    const w1 = montar();
    await flushPromises();
    expect(w1.text()).toContain("Línea 1");

    api.get.mockResolvedValueOnce({ data: ESTACION_CAPTURA });
    const w2 = montar();
    await flushPromises();
    expect(w2.text()).toContain("Todas");
  });

  it("muestra Estado A (Estación no configurada) ante 404 o falla de red", async () => {
    api.get.mockRejectedValueOnce({
      response: { status: 404 },
    });

    const w = montar();
    await flushPromises();

    const t = w.text();
    expect(t).toContain("No es posible iniciar sesión");
    expect(t).toContain("Estación no configurada");
    expect(t).toContain("Esta computadora no está configurada como estación.");
    expect(t).toContain("Reintentar detección");
  });

  it("permite reintentar la detección de estación tras fallo", async () => {
    api.get.mockRejectedValueOnce({ response: { status: 500 } });

    const w = montar();
    await flushPromises();

    expect(w.text()).toContain("No es posible iniciar sesión");

    // En el segundo intento responde con éxito
    api.get.mockResolvedValueOnce({ data: ESTACION_IMPRESION });
    const btn = w.find("button");
    await btn.trigger("click");
    await flushPromises();

    expect(w.text()).toContain("Iniciar sesión");
    expect(w.text()).toContain("Impresión Reforma 01");
  });
});

describe("LoginView - Flujo de Autenticación y Redirección", () => {
  it("inicia sesión exitosamente y redirige según el tipo de estación", async () => {
    api.get.mockResolvedValueOnce({ data: ESTACION_PRUEBA });
    api.post.mockResolvedValueOnce({
      data: {
        id: "ses-100",
        user_id: "u-1",
        can_supervise: false,
      },
    });

    const w = montar();
    await flushPromises();

    w.vm.username = "tecnico1";
    w.vm.password = "ValidPass123";
    await w.vm.entrar();
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith("/estaciones/login", {
      username: "tecnico1",
      password: "ValidPass123",
      workstation_id: "ws-pru-01",
    });

    expect(mockPush).toHaveBeenCalledWith({ name: "prueba" });
  });

  it("redirige a ruta de impresion para estación de tipo impresion", async () => {
    api.get.mockResolvedValueOnce({ data: ESTACION_IMPRESION });
    api.post.mockResolvedValueOnce({
      data: { id: "ses-200", user_id: "u-2", can_supervise: true },
    });

    const w = montar();
    await flushPromises();

    w.vm.username = "operador_imp";
    w.vm.password = "Pass12345";
    await w.vm.entrar();
    await flushPromises();

    expect(mockPush).toHaveBeenCalledWith({ name: "impresion" });
  });

  it("redirige a ruta de captura para estación de tipo captura", async () => {
    api.get.mockResolvedValueOnce({ data: ESTACION_CAPTURA });
    api.post.mockResolvedValueOnce({
      data: { id: "ses-300", user_id: "u-3", can_supervise: false },
    });

    const w = montar();
    await flushPromises();

    w.vm.username = "operador_cap";
    w.vm.password = "Pass12345";
    await w.vm.entrar();
    await flushPromises();

    expect(mockPush).toHaveBeenCalledWith({ name: "captura" });
  });
});

describe("LoginView - Manejo de Errores: 401 Credenciales y X1 Bloqueo 429", () => {
  it("muestra alerta de error de credenciales ante HTTP 401", async () => {
    api.get.mockResolvedValueOnce({ data: ESTACION_IMPRESION });
    api.post.mockRejectedValueOnce({
      response: {
        status: 401,
        data: { detail: "Contraseña incorrecta." },
      },
    });

    const w = montar();
    await flushPromises();

    w.vm.username = "operador1";
    w.vm.password = "MalPassword";
    await w.vm.entrar();
    await flushPromises();

    expect(w.text()).toContain("Contraseña incorrecta.");
    expect(w.text()).toContain("Iniciar sesión"); // Permanece en el formulario
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("muestra alerta de bloqueo por intentos fallidos ante HTTP 429 (X1)", async () => {
    api.get.mockResolvedValueOnce({ data: ESTACION_IMPRESION });
    api.post.mockRejectedValueOnce({
      response: {
        status: 429,
        data: { detail: "Demasiados intentos fallidos. Usuario bloqueado por 15 minutos." },
      },
    });

    const w = montar();
    await flushPromises();

    w.vm.username = "operador1";
    w.vm.password = "QuintoError";
    await w.vm.entrar();
    await flushPromises();

    expect(w.text()).toContain("Demasiados intentos fallidos. Usuario bloqueado por 15 minutos.");
    expect(w.text()).toContain("Iniciar sesión");
    expect(mockPush).not.toHaveBeenCalled();
  });
});

describe("LoginView - Estado B: Acceso Denegado (HTTP 403)", () => {
  it("muestra pantalla de acceso denegado cuando el usuario no tiene permisos en la estación", async () => {
    api.get.mockResolvedValueOnce({ data: ESTACION_PRUEBA });
    api.post.mockRejectedValueOnce({
      response: {
        status: 403,
        data: { detail: "El usuario no tiene asignado rol en esta estación." },
      },
    });

    const w = montar();
    await flushPromises();

    w.vm.username = "operador_ajeno";
    w.vm.password = "PasswordValido1";
    await w.vm.entrar();
    await flushPromises();

    const t = w.text();
    expect(t).toContain("Acceso denegado");
    expect(t).toContain("operador_ajeno");
    expect(t).toContain("Prueba Línea 1");
    expect(t).toContain("Sin permiso para esta estación");
    expect(t).toContain("El usuario no tiene asignado rol en esta estación.");
    expect(t).toContain("Cambiar usuario");
  });

  it("botón 'Cambiar usuario' limpia el formulario y regresa a Iniciar Sesión", async () => {
    api.get.mockResolvedValueOnce({ data: ESTACION_PRUEBA });
    api.post.mockRejectedValueOnce({
      response: {
        status: 403,
        data: { detail: "Sin permiso." },
      },
    });

    const w = montar();
    await flushPromises();

    w.vm.username = "operador_ajeno";
    w.vm.password = "PasswordValido1";
    await w.vm.entrar();
    await flushPromises();

    expect(w.text()).toContain("Acceso denegado");

    // Click en cambiar usuario
    w.vm.cambiarUsuario();
    await flushPromises();

    expect(w.vm.username).toBe("");
    expect(w.vm.password).toBe("");
    expect(w.text()).toContain("Iniciar sesión");
    expect(w.text()).not.toContain("Acceso denegado");
  });

  async function denegar403(data) {
    api.get.mockResolvedValueOnce({ data: ESTACION_PRUEBA });
    api.post.mockRejectedValueOnce({ response: { status: 403, data } });

    const w = montar();
    await flushPromises();

    w.vm.username = "operador_ajeno";
    w.vm.password = "PasswordValido1";
    await w.vm.entrar();
    await flushPromises();
    return w;
  }

  it("HU-007: muestra las estaciones asignadas devueltas en el 403", async () => {
    const w = await denegar403({
      detail: "Sin permiso.",
      permisos_asignados: [
        { station_type: "captura", center_id: "reforma", line_id: null },
        { station_type: "prueba", center_id: "reforma", line_id: 2 },
      ],
    });

    const t = w.text();
    expect(t).toContain("Estaciones asignadas");
    expect(t).toContain("Captura · reforma · todas las líneas");
    expect(t).toContain("Prueba · reforma · línea 2");
    expect(useSessionStore().permisosAsignados).toHaveLength(2);
  });

  it("HU-007: muestra 'Ninguna' si el 403 no trae permisos o la lista viene vacía", async () => {
    const sinCampo = await denegar403({ detail: "Sin permiso." });
    expect(sinCampo.text()).toContain("Estaciones asignadas");
    expect(sinCampo.text()).toContain("Ninguna");

    vi.clearAllMocks();
    const vacia = await denegar403({ detail: "Sin permiso.", permisos_asignados: [] });
    expect(vacia.text()).toContain("Ninguna");
  });

  it("HU-007: conserva el tipo crudo si no está en el catálogo de estaciones", async () => {
    const w = await denegar403({
      detail: "Sin permiso.",
      permisos_asignados: [{ station_type: "supervision", center_id: "reforma", line_id: 1 }],
    });
    expect(w.text()).toContain("supervision · reforma · línea 1");
  });

  it("HU-007: un 401 no expone permisos asignados y cambiarUsuario los limpia", async () => {
    api.get.mockResolvedValueOnce({ data: ESTACION_PRUEBA });
    api.post.mockRejectedValueOnce({
      response: { status: 401, data: { detail: "Credenciales inválidas." } },
    });
    const w = montar();
    await flushPromises();
    w.vm.username = "x";
    w.vm.password = "y";
    await w.vm.entrar();
    await flushPromises();
    expect(useSessionStore().permisosAsignados).toEqual([]);

    const w2 = await denegar403({
      detail: "Sin permiso.",
      permisos_asignados: [{ station_type: "captura", center_id: "reforma", line_id: null }],
    });
    w2.vm.cambiarUsuario();
    await flushPromises();
    expect(useSessionStore().permisosAsignados).toEqual([]);
  });
});

// HU-005 / HU-006: antes de iniciar sesión el panel de estación detectada
// muestra tipo, centro y línea(s) de la estación configurada.
describe("LoginView - HU-005 / HU-006: contexto de la estación en la pantalla inicial", () => {
  function fila(w, etiqueta) {
    const f = w
      .findAll(".fila-meta")
      .find((el) => el.find("span").text() === etiqueta);
    return f ? f.find("strong").text() : null;
  }

  it("HU-005: estación de Prueba muestra nombre, centro, línea y tipo", async () => {
    api.get.mockResolvedValueOnce({ data: ESTACION_PRUEBA });
    const w = montar();
    await flushPromises();
    expect(fila(w, "Estación")).toBe("Prueba Línea 1");
    expect(fila(w, "Centro")).toBe("Reforma");
    expect(fila(w, "Línea")).toBe("Línea 1");
    expect(fila(w, "Tipo")).toBe("Prueba");
  });

  it("HU-006: estación de Impresión muestra nombre, centro y todas sus líneas", async () => {
    api.get.mockResolvedValueOnce({ data: ESTACION_IMPRESION });
    const w = montar();
    await flushPromises();
    expect(fila(w, "Estación")).toBe("Impresión Reforma 01");
    expect(fila(w, "Centro")).toBe("Reforma");
    expect(fila(w, "Línea")).toBe("Líneas 1 y 2");
    expect(fila(w, "Tipo")).toBe("Impresión");
  });

  it("HU-006: con tres o más líneas las lista separadas por comas y la última con 'y'", async () => {
    api.get.mockResolvedValueOnce({
      data: { ...ESTACION_IMPRESION, allowed_line_ids: [1, 2, 3] },
    });
    const w = montar();
    await flushPromises();
    expect(fila(w, "Línea")).toBe("Líneas 1, 2 y 3");
  });

  it("HU-006: con una sola línea permitida usa singular", async () => {
    api.get.mockResolvedValueOnce({
      data: { ...ESTACION_IMPRESION, allowed_line_ids: [2] },
    });
    const w = montar();
    await flushPromises();
    expect(fila(w, "Línea")).toBe("Línea 2");
  });
});
