import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import * as directives from "vuetify/directives";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/api/client", () => ({ api: { get: vi.fn() } }));
import { api } from "../src/api/client";
import ExpedienteHeader from "../src/components/ExpedienteHeader.vue";

const EXPEDIENTE = {
  id: "abcdef12-0000-0000-0000-000000000000",
  placa: "ABC123",
  estado: "CERRADO_RECHAZADO",
  centro_id: "OAX-01",
  linea_id: 2,
  combustible_validado: "GASOLINA",
  certificado_tipo: "RECHAZO",
  operador_nombre: "Operador Con Un Nombre Muy Largo Y Sin Fin",
  updated_at: "2026-10-20T15:00:00Z",
  vehiculo: { marca: "NISSAN", linea: "TSURU", modelo: 2010, tipo_vehiculo: "AUTOMOVIL" },
};

function montar(expediente = EXPEDIENTE) {
  return mount(ExpedienteHeader, {
    props: { expediente },
    global: { plugins: [createPinia(), createVuetify({ components, directives })] },
  });
}

beforeEach(() => {
  setActivePinia(createPinia());
  api.get.mockReset();
  api.get.mockResolvedValue({ data: { estado: "SINCRONIZADO", pendientes: 0, en_error: 0, sincronizados: 4 } });
});

describe("ExpedienteHeader (HU-020, HU-037, HU-105)", () => {
  it("muestra los datos mínimos del expediente", async () => {
    const w = montar();
    await flushPromises();
    const t = w.text();
    for (const v of ["ABC123", "NISSAN TSURU", "2010", "GASOLINA", "AUTOMOVIL", "RECHAZO", "OAX-01", "Operador Con Un Nombre"])
      expect(t).toContain(v);
    expect(t).toContain("Expediente #abcdef12");
  });

  it("estado terminal muestra su etiqueta, no el enum crudo", async () => {
    const w = montar();
    await flushPromises();
    expect(w.text()).toContain("Cerrado — rechazado");
    expect(w.text()).not.toContain("CERRADO_RECHAZADO");
  });

  it("campos vacíos se muestran con guion y valores largos se parten", async () => {
    const w = montar({ ...EXPEDIENTE, combustible_validado: null, certificado_tipo: null, vehiculo: null });
    await flushPromises();
    expect(w.text()).toContain("—");
    expect(w.findAll(".text-break").length).toBe(9);
  });

  it.each([
    ["SINCRONIZADO", "Sincronizado"],
    ["PENDIENTE", "Pendiente de sincronizar"],
    ["ERROR", "Error de sincronización"],
    ["SIN_REGISTROS", "Sin sincronizar"],
  ])("sync %s -> %s", async (estado, texto) => {
    api.get.mockResolvedValue({ data: { estado, pendientes: 1, en_error: 0, sincronizados: 0 } });
    const w = montar();
    await flushPromises();
    expect(w.text()).toContain(texto);
    expect(api.get).toHaveBeenCalledWith(`/sync/expediente/${EXPEDIENTE.id}`);
  });

  it("si falla la consulta de sync no muestra chip ni rompe", async () => {
    api.get.mockRejectedValue(new Error("offline"));
    const w = montar();
    await flushPromises();
    expect(w.text()).not.toContain("sincroniz");
    expect(w.text()).toContain("ABC123");
  });

  it("vuelve a consultar sync cuando cambia updated_at", async () => {
    const w = montar();
    await flushPromises();
    await w.setProps({ expediente: { ...EXPEDIENTE, updated_at: "2026-10-20T16:00:00Z" } });
    await flushPromises();
    expect(api.get).toHaveBeenCalledTimes(2);
  });
});
