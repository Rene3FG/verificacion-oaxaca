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
import ImpresionView from "../src/views/ImpresionView.vue";
import { useSessionStore } from "../src/stores/session";

const MOCK_COLA = [
  {
    id: "exp-001",
    placa: "TLX-101",
    estado: "PENDIENTE_IMPRESION",
    resultado_final: "APROBADO",
    resultado_tecnico: "APROBADO",
    certificado_tipo: null,
    tipo_certificado_sugerido: "PARTICULAR",
    folio_externo: null,
    linea_id: 1,
    tipo_verificacion: "ORDINARIA",
    vehiculo: { marca: "NISSAN", linea: "VERSA", modelo: 2021, niv: "3N1AB7AP1MY111111" },
  },
  {
    id: "exp-002",
    placa: "OAX-202",
    estado: "PENDIENTE_DE_IMPRESION_RECHAZO",
    resultado_final: "RECHAZADO",
    resultado_tecnico: "RECHAZADO_PRUEBA",
    certificado_tipo: "RECHAZO",
    tipo_certificado_sugerido: "RECHAZO",
    folio_externo: null,
    linea_id: 2,
    tipo_verificacion: "ORDINARIA",
    vehiculo: { marca: "CHEVROLET", linea: "AVEO", modelo: 2018, niv: "3G1JA5PH8JL222222" },
  },
  {
    id: "exp-003",
    placa: "MEX-303",
    estado: "PENDIENTE_DE_IMPRESION_RECHAZO",
    resultado_final: "RECHAZADO",
    resultado_tecnico: "RECHAZADO_VISUAL",
    certificado_tipo: "RECHAZO",
    tipo_certificado_sugerido: "RECHAZO",
    folio_externo: null,
    linea_id: 1,
    tipo_verificacion: null,
    vehiculo: { marca: "VOLKSWAGEN", linea: "JETTA", modelo: 2012, niv: "3VW2K7AJ0CM333333" },
  },
  {
    id: "exp-004",
    placa: "PUE-404",
    estado: "FOLIO_ASIGNADO",
    resultado_final: "RECHAZADO",
    resultado_tecnico: "RECHAZADO_VISUAL",
    certificado_tipo: "RECHAZO",
    tipo_certificado_sugerido: "RECHAZO",
    folio_externo: "FOL-VIS-004",
    linea_id: 1,
    tipo_verificacion: "ORDINARIA",
    vehiculo: { marca: "FORD", linea: "FIESTA", modelo: 2015, niv: "3FADP4BJ8FM444444" },
  },
  {
    id: "exp-005",
    placa: "VER-505",
    estado: "IMPRESO",
    resultado_final: "APROBADO",
    resultado_tecnico: "APROBADO",
    certificado_tipo: "DOBLE_CERO",
    tipo_certificado_sugerido: "DOBLE_CERO",
    folio_externo: "FOL-00-505",
    linea_id: 2,
    tipo_verificacion: "ORDINARIA",
    hora_salida: "2026-10-21T10:00:00Z",
    cerrado_at: null,
    vehiculo: { marca: "TOYOTA", linea: "PRIUS", modelo: 2024, niv: "JTDKN3DU0E1555555" },
  },
  {
    id: "exp-006",
    placa: "GTO-606",
    estado: "FOLIO_ERROR",
    resultado_final: "APROBADO",
    resultado_tecnico: "APROBADO",
    certificado_tipo: "INTENSIVO",
    tipo_certificado_sugerido: "INTENSIVO",
    folio_externo: null,
    linea_id: 1,
    tipo_verificacion: "ORDINARIA",
    vehiculo: { marca: "HONDA", linea: "CR-V", modelo: 2017, niv: "3HKRM4H74HG666666" },
  },
  {
    id: "exp-007",
    placa: "QRO-707",
    estado: "IMPRESION_FALLIDA",
    resultado_final: "APROBADO",
    resultado_tecnico: "APROBADO",
    certificado_tipo: "PARTICULAR",
    tipo_certificado_sugerido: "PARTICULAR",
    folio_externo: "FOL-PAR-707",
    linea_id: 2,
    tipo_verificacion: "ORDINARIA",
    vehiculo: { marca: "MAZDA", linea: "3", modelo: 2019, niv: "3MZBN1V72KM777777" },
  },
];

function montar(prepSession, cola = MOCK_COLA) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore();
  session.estacion = {
    id: "est-impresion-01",
    station_type: "IMPRESION",
    center_id: "OAX-01",
    allowed_line_ids: [1, 2],
  };
  session.sesion = { id: "ses-1", can_supervise: false };
  session.usuario = "sebas";
  prepSession?.(session);

  api.get.mockImplementation((url) => {
    if (url === "/impresion/cola") {
      return Promise.resolve({ data: JSON.parse(JSON.stringify(cola)) });
    }
    if (url.startsWith("/sync/expediente")) {
      return Promise.resolve({ data: { estado: "SINCRONIZADO" } });
    }
    return Promise.resolve({ data: {} });
  });

  const vuetify = createVuetify({ components, directives });
  return mount(ImpresionView, {
    global: {
      plugins: [pinia, vuetify],
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ImpresionView - Carga Inicial y Renderizado", () => {
  it("consulta /impresion/cola al montar y muestra la cabecera y conteos", async () => {
    const w = montar();
    await flushPromises();

    expect(api.get).toHaveBeenCalledWith("/impresion/cola");
    const t = w.text();
    expect(t).toContain("Cola de Impresión Central");
    expect(t).toContain("Centro OAX-01");
    expect(t).toContain("Líneas 1, 2");
    expect(t).toContain("Mostrando 7 de 7 expedientes en cola");
    expect(t).toContain("TLX-101");
    expect(t).toContain("OAX-202");
    expect(t).toContain("MEX-303");
  });

  it("muestra mensaje adecuado cuando la cola está vacía", async () => {
    const w = montar(null, []);
    await flushPromises();

    expect(w.text()).toContain(
      "No hay expedientes pendientes de impresión en las líneas de este centro."
    );
  });
});

describe("ImpresionView - HU-057: Filtro por Resultado Técnico", () => {
  it("filtra rechazos por prueba técnica (dinamómetro/estática)", async () => {
    const w = montar();
    await flushPromises();

    w.vm.filtroResultadoCola = "RECHAZADO_PRUEBA";
    await flushPromises();

    const filtrados = w.vm.expedientesFiltrados;
    expect(filtrados.length).toBe(1);
    expect(filtrados[0].placa).toBe("OAX-202");
    expect(filtrados[0].resultado_tecnico).toBe("RECHAZADO_PRUEBA");
  });

  it("filtra rechazos visuales tanto antes como después de asignarles folio", async () => {
    const w = montar();
    await flushPromises();

    w.vm.filtroResultadoCola = "RECHAZADO_VISUAL";
    await flushPromises();

    const filtrados = w.vm.expedientesFiltrados;
    // Deben aparecer exp-003 (sin folio) y exp-004 (con folio FOL-VIS-004)
    expect(filtrados.length).toBe(2);
    const placas = filtrados.map((e) => e.placa);
    expect(placas).toContain("MEX-303");
    expect(placas).toContain("PUE-404");

    // Verificar que uno está pendiente de folio y el otro ya tiene folio asignado
    const sinFolio = filtrados.find((e) => e.placa === "MEX-303");
    const conFolio = filtrados.find((e) => e.placa === "PUE-404");
    expect(sinFolio.folio_externo).toBeNull();
    expect(sinFolio.estado).toBe("PENDIENTE_DE_IMPRESION_RECHAZO");
    expect(conFolio.folio_externo).toBe("FOL-VIS-004");
    expect(conFolio.estado).toBe("FOLIO_ASIGNADO");
  });

  it("filtra únicamente los expedientes aprobados", async () => {
    const w = montar();
    await flushPromises();

    w.vm.filtroResultadoCola = "APROBADO";
    await flushPromises();

    const filtrados = w.vm.expedientesFiltrados;
    expect(filtrados.length).toBe(4);
    for (const exp of filtrados) {
      expect(exp.resultado_tecnico).toBe("APROBADO");
    }
    const placas = filtrados.map((e) => e.placa);
    expect(placas).toContain("TLX-101");
    expect(placas).toContain("VER-505");
    expect(placas).toContain("GTO-606");
    expect(placas).toContain("QRO-707");
  });
});

describe("ImpresionView - HU-058 / HU-059 / HU-090: Filtro por Estado y Chips Rápidos", () => {
  it("calcula correctamente los conteos para los chips rápidos", async () => {
    const w = montar();
    await flushPromises();

    const c = w.vm.conteosPorEstado;
    expect(c.todos).toBe(7);
    expect(c.pendientes).toBe(3); // exp-001, exp-002, exp-003
    expect(c.asignados).toBe(1); // exp-004
    expect(c.impresos).toBe(1); // exp-005
    expect(c.incidencias).toBe(2); // exp-006 (FOLIO_ERROR), exp-007 (IMPRESION_FALLIDA)
  });

  it("filtra expedientes pendientes de folio (PENDIENTE_IMPRESION y PENDIENTE_DE_IMPRESION_RECHAZO)", async () => {
    const w = montar();
    await flushPromises();

    w.vm.filtroEstadoCola = "PENDIENTE";
    await flushPromises();

    const filtrados = w.vm.expedientesFiltrados;
    expect(filtrados.length).toBe(3);
    const placas = filtrados.map((e) => e.placa);
    expect(placas).toEqual(["TLX-101", "OAX-202", "MEX-303"]);
  });

  it("filtra expedientes con folio asignado", async () => {
    const w = montar();
    await flushPromises();

    w.vm.filtroEstadoCola = "FOLIO_ASIGNADO";
    await flushPromises();

    const filtrados = w.vm.expedientesFiltrados;
    expect(filtrados.length).toBe(1);
    expect(filtrados[0].placa).toBe("PUE-404");
  });

  it("filtra expedientes impresos físicamente pendientes de cierre formal", async () => {
    const w = montar();
    await flushPromises();

    w.vm.filtroEstadoCola = "IMPRESO";
    await flushPromises();

    const filtrados = w.vm.expedientesFiltrados;
    expect(filtrados.length).toBe(1);
    expect(filtrados[0].placa).toBe("VER-505");
    expect(filtrados[0].estado).toBe("IMPRESO");
  });

  it("filtra incidencias y errores de folio o impresión", async () => {
    const w = montar();
    await flushPromises();

    w.vm.filtroEstadoCola = "INCIDENCIAS";
    await flushPromises();

    const filtrados = w.vm.expedientesFiltrados;
    expect(filtrados.length).toBe(2);
    const placas = filtrados.map((e) => e.placa);
    expect(placas).toContain("GTO-606");
    expect(placas).toContain("QRO-707");
  });
});

describe("ImpresionView - HU-056 y HU-060: Filtro por Línea y Búsqueda Reactiva", () => {
  it("filtra por línea autorizada en la estación", async () => {
    const w = montar();
    await flushPromises();

    w.vm.filtroLineaCola = "1";
    await flushPromises();

    const linea1 = w.vm.expedientesFiltrados;
    expect(linea1.length).toBe(4);
    for (const exp of linea1) expect(exp.linea_id).toBe(1);

    w.vm.filtroLineaCola = "2";
    await flushPromises();

    const linea2 = w.vm.expedientesFiltrados;
    expect(linea2.length).toBe(3);
    for (const exp of linea2) expect(exp.linea_id).toBe(2);
  });

  it("busca reactivamente por placa, NIV, marca, línea o folio", async () => {
    const w = montar();
    await flushPromises();

    // Búsqueda por placa parcial
    w.vm.busquedaCola = "oax";
    expect(w.vm.expedientesFiltrados.length).toBe(1);
    expect(w.vm.expedientesFiltrados[0].placa).toBe("OAX-202");

    // Búsqueda por NIV
    w.vm.busquedaCola = "3HKRM";
    expect(w.vm.expedientesFiltrados.length).toBe(1);
    expect(w.vm.expedientesFiltrados[0].placa).toBe("GTO-606");

    // Búsqueda por folio
    w.vm.busquedaCola = "FOL-00-505";
    expect(w.vm.expedientesFiltrados.length).toBe(1);
    expect(w.vm.expedientesFiltrados[0].placa).toBe("VER-505");

    // Búsqueda por marca
    w.vm.busquedaCola = "toyota";
    expect(w.vm.expedientesFiltrados.length).toBe(1);
    expect(w.vm.expedientesFiltrados[0].placa).toBe("VER-505");
  });

  it("limpia todos los filtros con limpiarFiltros()", async () => {
    const w = montar();
    await flushPromises();

    w.vm.busquedaCola = "prueba";
    w.vm.filtroEstadoCola = "IMPRESO";
    w.vm.filtroResultadoCola = "APROBADO";
    w.vm.filtroLineaCola = "2";

    w.vm.limpiarFiltros();

    expect(w.vm.busquedaCola).toBe("");
    expect(w.vm.filtroEstadoCola).toBe("TODOS");
    expect(w.vm.filtroResultadoCola).toBe("TODOS");
    expect(w.vm.filtroLineaCola).toBe("TODAS");
    expect(w.vm.expedientesFiltrados.length).toBe(7);
  });
});

describe("ImpresionView - HU-053: Tipos de Certificado Sugeridos", () => {
  it("calcula sugerencias y colores de certificados correctamente", async () => {
    const w = montar();
    await flushPromises();

    expect(w.vm.tipoCertificadoSugerido(MOCK_COLA[1])).toBe("RECHAZO");
    expect(w.vm.colorCertificado("RECHAZO")).toBe("error");

    expect(w.vm.tipoCertificadoSugerido(MOCK_COLA[4])).toBe("DOBLE_CERO");
    expect(w.vm.colorCertificado("DOBLE_CERO")).toBe("success");

    expect(w.vm.tipoCertificadoSugerido(MOCK_COLA[5])).toBe("INTENSIVO");
    expect(w.vm.colorCertificado("INTENSIVO")).toBe("warning");

    expect(w.vm.colorCertificado("PARTICULAR")).toBe("primary");
  });
});

describe("ImpresionView - Regla N2 y Guardias de Impresión", () => {
  it("bloquea la impresión si el tipo de verificación no está definido", async () => {
    const w = montar();
    await flushPromises();

    // Abrir exp-004 (FOLIO_ASIGNADO) pero forzar tipo de verificación nulo
    const exp = JSON.parse(JSON.stringify(MOCK_COLA[3]));
    exp.tipo_verificacion = null;
    w.vm.abrirExpediente(exp);
    w.vm.tipoVerificacionSeleccionado = null;
    await flushPromises();

    expect(w.vm.tipoVerificacionActivo).toBeFalsy();
    expect(w.vm.puedeImprimir).toBe(false);

    // Si intenta invocar imprimir directamente, arroja error
    await w.vm.imprimir();
    expect(w.vm.error).toBe("Selecciona el tipo de verificación antes de imprimir.");

    // Al asignar tipo de verificación, puedeImprimir se habilita
    w.vm.tipoVerificacionSeleccionado = "ORDINARIA";
    await flushPromises();
    expect(w.vm.puedeImprimir).toBe(true);
  });

  it("requiere permiso de supervisor para reintentar una impresión fallida", async () => {
    // Sesión de operador regular
    const w = montar((s) => {
      s.sesion = { id: "s1", can_supervise: false };
    });
    await flushPromises();

    // exp-007 tiene estado IMPRESION_FALLIDA
    w.vm.abrirExpediente(MOCK_COLA[6]);
    await flushPromises();

    expect(w.vm.reintentoRequiereSupervisor).toBe(true);
    expect(w.vm.puedeImprimir).toBe(false);
    expect(w.text()).toContain(
      "La impresora falló antes; reintentar requiere una sesión de Supervisor."
    );

    // Cambiar a sesión con permiso de supervisión
    const session = useSessionStore();
    session.sesion = { id: "s1", can_supervise: true };
    await flushPromises();

    expect(w.vm.reintentoRequiereSupervisor).toBe(false);
    expect(w.vm.puedeImprimir).toBe(true);
  });
});

describe("ImpresionView - Flujos Operativos y Llamadas a la API", () => {
  it("solicita folio correctamente cuando el expediente no tiene folio", async () => {
    const w = montar();
    await flushPromises();

    const exp = JSON.parse(JSON.stringify(MOCK_COLA[1])); // exp-002 (RECHAZO, sin folio)
    w.vm.abrirExpediente(exp);
    await flushPromises();

    expect(w.vm.puedeSolicitarFolio).toBe(true);

    api.post.mockResolvedValueOnce({
      data: {
        folio: "FOL-REC-999",
        estado_expediente: "FOLIO_ASIGNADO",
      },
    });

    await w.vm.solicitarFolio();

    expect(api.post).toHaveBeenCalledWith(
      "/folios/solicitar/exp-002",
      null,
      { params: { tipo_certificado: "RECHAZO" } }
    );
    expect(w.vm.expediente.folio_externo).toBe("FOL-REC-999");
    expect(w.vm.expediente.estado).toBe("FOLIO_ASIGNADO");
    expect(w.vm.aviso).toContain("Folio asignado: FOL-REC-999");
  });

  it("permite marcar un folio como dañado antes de imprimir", async () => {
    const w = montar();
    await flushPromises();

    const exp = JSON.parse(JSON.stringify(MOCK_COLA[3])); // exp-004 (FOLIO_ASIGNADO)
    w.vm.abrirExpediente(exp);
    await flushPromises();

    expect(w.vm.puedeMarcarFolioDanado).toBe(true);

    api.post.mockResolvedValueOnce({
      data: {
        folio_danado: "FOL-VIS-004",
        folio_externo: "FOL-VIS-005",
      },
    });

    await w.vm.marcarFolioDanado();

    expect(api.post).toHaveBeenCalledWith("/impresion/folio/marcar-danado/exp-004");
    expect(w.vm.expediente.folio_externo).toBe("FOL-VIS-005");
    expect(w.vm.aviso).toContain("Folio nuevo: FOL-VIS-005");
  });

  it("ejecuta impresión exitosa y actualiza el estado a IMPRESO", async () => {
    const w = montar();
    await flushPromises();

    const exp = JSON.parse(JSON.stringify(MOCK_COLA[3])); // exp-004 (FOLIO_ASIGNADO)
    w.vm.abrirExpediente(exp);
    await flushPromises();

    api.post.mockResolvedValueOnce({
      data: {
        estado_expediente: "IMPRESO",
        intentos: 1,
      },
    });

    await w.vm.imprimir();

    expect(api.post).toHaveBeenCalledWith("/impresion/imprimir/exp-004");
    expect(w.vm.expediente.estado).toBe("IMPRESO");
    expect(w.vm.aviso).toBe("Certificado impreso correctamente.");
  });

  it("permite cerrar el expediente una vez impreso", async () => {
    const w = montar();
    await flushPromises();

    const exp = JSON.parse(JSON.stringify(MOCK_COLA[4])); // exp-005 (IMPRESO)
    w.vm.abrirExpediente(exp);
    await flushPromises();

    expect(w.vm.puedeCerrar).toBe(true);

    api.post.mockResolvedValueOnce({
      data: {
        estado_expediente: "CERRADO_APROBADO",
      },
    });

    await w.vm.cerrarExpediente();

    expect(api.post).toHaveBeenCalledWith("/impresion/cerrar/exp-005");
    expect(w.vm.expediente.estado).toBe("CERRADO_APROBADO");
    expect(w.vm.aviso).toBe("Expediente cerrado.");
  });
});

describe("ImpresionView - HU-006: estación Impresión Central, centro y líneas visibles", () => {
  it("la cabecera identifica la estación como Impresión Central con su centro y sus líneas", async () => {
    const w = montar();
    await flushPromises();
    const cabecera = w.find("h1").element.parentElement.textContent.replace(/\s+/g, " ");
    expect(w.find("h1").text()).toBe("Cola de Impresión Central");
    expect(cabecera).toContain("Centro OAX-01");
    expect(cabecera).toContain("Líneas 1, 2");
  });

  it("las líneas y el centro visibles salen de la estación configurada, no de valores fijos", async () => {
    const w = montar((s) => {
      s.estacion = {
        id: "est-impresion-02",
        station_type: "impresion",
        center_id: "REFORMA",
        allowed_line_ids: [2, 3],
      };
    });
    await flushPromises();
    const t = w.text();
    expect(t).toContain("Centro REFORMA");
    expect(t).toContain("Líneas 2, 3");
    expect(t).not.toContain("Centro OAX-01");
    expect(t).not.toContain("Líneas 1, 2");
  });

  it("muestra la estación por su identificador de workstation cuando existe", async () => {
    const w = montar((s) => {
      s.estacion = { ...s.estacion, workstation_id: "IMPRESION-07" };
    });
    await flushPromises();
    expect(w.text()).toContain("Estación IMPRESION-07");
  });

  it("sin allowed_line_ids (ausente o vacío) la cabecera dice 'Ninguna' y el filtro solo ofrece 'Todas las líneas'", async () => {
    for (const lineas of [undefined, []]) {
      const w = montar((s) => {
        s.estacion = {
          id: "est-impresion-03",
          station_type: "impresion",
          center_id: "OAX-01",
          allowed_line_ids: lineas,
        };
      });
      await flushPromises();

      const cabecera = w.find("h1").element.parentElement.textContent.replace(/\s+/g, " ");
      expect(cabecera).toContain("Líneas Ninguna");
      expect(cabecera).not.toContain("1, 2");
      expect(w.vm.opcionesFiltroLinea).toEqual([{ title: "Todas las líneas", value: "TODAS" }]);
    }
  });

  it("sin workstation_id ni id la cabecera muestra 'Estación —'; con solo id usa el id", async () => {
    const sinNada = montar((s) => {
      s.estacion = { station_type: "impresion", center_id: "OAX-01", allowed_line_ids: [1, 2] };
    });
    await flushPromises();
    const cabecera = sinNada.find("h1").element.parentElement.textContent.replace(/\s+/g, " ");
    expect(cabecera).toContain("Estación —");
    expect(cabecera).not.toContain("IMPRESION-01");

    const soloId = montar((s) => {
      s.estacion = { id: "est-impresion-09", station_type: "impresion", center_id: "OAX-01", allowed_line_ids: [1, 2] };
    });
    await flushPromises();
    expect(soloId.text()).toContain("Estación est-impresion-09");
  });
});
