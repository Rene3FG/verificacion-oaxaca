import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import * as directives from "vuetify/directives";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/api/client", () => ({ api: { get: vi.fn().mockResolvedValue({ data: {} }), post: vi.fn() } }));
const ruta = { name: "prueba" };
vi.mock("vue-router", () => ({ useRoute: () => ruta, useRouter: () => ({ push: vi.fn() }) }));
import { api } from "../src/api/client";
import TopAppBar from "../src/components/TopAppBar.vue";
import { useSessionStore } from "../src/stores/session";

function montar(prep) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const s = useSessionStore();
  s.estacion = { station_type: "PRUEBA", center_id: "OAX-01", line_id: 1 };
  s.sesion = { id: "s1", can_supervise: false };
  s.usuario = "ana";
  prep?.(s);
  // El componente consulta /sync/estado al montar: la respuesta fija el estado.
  api.get.mockResolvedValue({ data: s.estadoSync ?? {} });
  const vuetify = createVuetify({ components, directives });
  return mount(
    { template: "<v-layout><TopAppBar /></v-layout>", components: { TopAppBar } },
    { global: { plugins: [pinia, vuetify] } },
  );
}

beforeEach(() => {
  ruta.name = "prueba";
});

describe("TopAppBar (HU-004, HU-104)", () => {
  it("muestra sistema, estación, centro, línea, usuario y fecha/hora", async () => {
    const w = montar((s) => (s.estadoSync = { central: "EN_LINEA", pendientes: 0, sincronizando: 0 }));
    await flushPromises();
    const t = w.text();
    expect(t).toContain("Sistema de Verificación Vehicular Oaxaca");
    expect(t).toContain("PRUEBA · OAX-01");
    expect(t).toContain("Línea 1");
    expect(t).toContain("ana");
    expect(t).toMatch(/\d{2}\/\d{2}\/\d{4}/);
    expect(t).toContain("Todo sincronizado");
  });

  it.each([
    [{ central: "SIN_CONEXION", pendientes: 1, sincronizando: 0 }, "Operando sin internet · 1 pendiente"],
    [{ central: "SIN_CONEXION", pendientes: 4, sincronizando: 0 }, "Operando sin internet · 4 pendientes"],
    [{ central: "SIN_CONEXION", pendientes: 0, sincronizando: 0 }, "Operando sin internet"],
    [{ central: "EN_LINEA", pendientes: 2, en_error: 1, sincronizando: 0 }, "2 pendientes (1 con error)"],
    [{ central: "EN_LINEA", pendientes: 2, sincronizando: 1 }, "Sincronizando…"],
  ])("indicador %j", async (estado, texto) => {
    const w = montar((s) => (s.estadoSync = estado));
    await flushPromises();
    expect(w.text()).toContain(texto);
  });

  it("en el login la barra queda limpia", async () => {
    ruta.name = "login";
    const w = montar();
    await flushPromises();
    expect(w.text()).toContain("Acceso operativo");
    expect(w.text()).not.toContain("OAX-01");
    expect(w.text()).not.toContain("ana");
  });

  it("el botón Supervisor solo aparece con permiso de supervisión", async () => {
    expect(montar().text()).not.toContain("Supervisor");
    const w = montar((s) => (s.sesion.can_supervise = true));
    expect(w.text()).toContain("Supervisor");
  });
});
