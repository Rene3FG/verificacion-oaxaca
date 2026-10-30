import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/api/client", () => ({ api: { get: vi.fn(), post: vi.fn() } }));
import { api } from "../src/api/client";
import { useSessionStore } from "../src/stores/session";

let s;
beforeEach(() => {
  setActivePinia(createPinia());
  api.get.mockReset();
  api.post.mockReset();
  s = useSessionStore();
});

describe("conexión (HU-104)", () => {
  it.each([
    [null, "desconocido"],
    [{ central: "EN_LINEA", pendientes: 0, sincronizando: 0 }, "en_linea"],
    [{ central: "EN_LINEA", pendientes: 3, sincronizando: 0 }, "pendientes"],
    [{ central: "EN_LINEA", pendientes: 3, sincronizando: 1 }, "sincronizando"],
    [{ central: "SIN_CONEXION", pendientes: 3, sincronizando: 0 }, "sin_internet"],
    [{ central: "SIN_CONEXION", pendientes: 0, sincronizando: 1 }, "sin_internet"],
  ])("%j -> %s", (estadoSync, esperado) => {
    s.estadoSync = estadoSync;
    expect(s.conexion).toBe(esperado);
  });

  it("sin sesión no consulta /sync/estado; con falla vuelve a desconocido", async () => {
    await s.actualizarEstadoSync();
    expect(api.get).not.toHaveBeenCalled();
    s.sesion = { id: "x" };
    api.get.mockRejectedValue(new Error("down"));
    s.estadoSync = { central: "EN_LINEA", pendientes: 0, sincronizando: 0 };
    await s.actualizarEstadoSync();
    expect(s.conexion).toBe("desconocido");
  });
});

describe("acceso (HU-007)", () => {
  beforeEach(() => {
    s.estacion = { id: "w1" };
  });

  it("403 es sin_permiso y conserva el usuario tecleado", async () => {
    api.post.mockRejectedValue({ response: { status: 403, data: { detail: "No tienes permiso para operar esta estación." } } });
    await expect(s.iniciarSesion("ana", "x")).rejects.toBeTruthy();
    expect(s.errorTipo).toBe("sin_permiso");
    expect(s.usuarioDenegado).toBe("ana");
    expect(s.error).toBe("No tienes permiso para operar esta estación.");
    expect(s.tieneSesionActiva).toBe(false);
  });

  it("401 es credenciales y no guarda usuarioDenegado", async () => {
    api.post.mockRejectedValue({ response: { status: 401, data: { detail: "Credenciales inválidas" } } });
    await expect(s.iniciarSesion("ana", "x")).rejects.toBeTruthy();
    expect(s.errorTipo).toBe("credenciales");
    expect(s.usuarioDenegado).toBeNull();
  });

  it("sin detalle del servidor usa el texto estándar de HU-007", async () => {
    api.post.mockRejectedValue({ response: { status: 403, data: {} } });
    await expect(s.iniciarSesion("ana", "x")).rejects.toBeTruthy();
    expect(s.error).toBe("No tienes permiso para operar esta estación.");
  });

  it("login correcto guarda sesión y usuario", async () => {
    api.post.mockResolvedValue({ data: { id: "s1", can_supervise: true } });
    await s.iniciarSesion("ana", "x");
    expect(s.tieneSesionActiva).toBe(true);
    expect(s.usuario).toBe("ana");
    expect(s.puedeSupervisar).toBe(true);
  });
});

describe("estación", () => {
  it("404 -> estacion_no_configurada con mensaje propio", async () => {
    api.get.mockRejectedValue({ response: { status: 404 } });
    await expect(s.detectarEstacion()).rejects.toBeTruthy();
    expect(s.errorTipo).toBe("estacion_no_configurada");
    expect(s.error).toContain("no está configurada");
  });

  it("sin respuesta del servidor da mensaje distinto al 404", async () => {
    api.get.mockRejectedValue(new Error("network"));
    await expect(s.detectarEstacion()).rejects.toBeTruthy();
    expect(s.error).toContain("No se pudo consultar");
  });
});

describe("cierre de sesión", () => {
  it("limpia el estado local aunque el servidor ya la diera por inválida", async () => {
    s.sesion = { id: "s1" };
    s.usuario = "ana";
    s.estadoSync = { central: "EN_LINEA" };
    api.post.mockRejectedValue({ response: { status: 401 } });
    await s.cerrarSesion();
    expect(s.sesion).toBeNull();
    expect(s.usuario).toBeNull();
    expect(s.estadoSync).toBeNull();
    expect(api.post).toHaveBeenCalledWith("/estaciones/logout/s1");
  });
});

// resolverDeviceIdentifier() se evalúa al importar el módulo: cada caso
// reinicia los módulos, prepara URL/localStorage/entorno y reimporta el store.
describe("identificador de estación del equipo (?estacion=)", () => {
  const CLAVE = "device_identifier";

  async function detectarCon({ search = "", guardado, env = "", storage } = {}) {
    vi.resetModules();
    window.history.replaceState({}, "", `/${search}`);
    localStorage.clear();
    if (guardado !== undefined) localStorage.setItem(CLAVE, guardado);
    vi.stubEnv("VITE_DEVICE_IDENTIFIER", env);
    storage?.();

    const { createPinia: crearPinia, setActivePinia: activarPinia } = await import("pinia");
    const { api: apiFresca } = await import("../src/api/client");
    const { useSessionStore: usarStore } = await import("../src/stores/session");
    activarPinia(crearPinia());
    apiFresca.get.mockResolvedValue({ data: { id: "w1" } });

    await usarStore().detectarEstacion();
    return apiFresca.get.mock.calls[0][0];
  }

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    localStorage.clear();
    window.history.replaceState({}, "", "/");
  });

  it("?estacion=NOMBRE gana sobre lo guardado y se persiste en localStorage", async () => {
    const url = await detectarCon({ search: "?estacion=CAPTURA-L2", guardado: "OTRO-EQUIPO", env: "DEV" });
    expect(url).toBe("/estaciones/CAPTURA-L2");
    expect(localStorage.getItem(CLAVE)).toBe("CAPTURA-L2");
  });

  it("sin parámetro en la URL usa el identificador guardado y no lo modifica", async () => {
    const url = await detectarCon({ guardado: "PRUEBA-L1", env: "DEV" });
    expect(url).toBe("/estaciones/PRUEBA-L1");
    expect(localStorage.getItem(CLAVE)).toBe("PRUEBA-L1");
  });

  it("lo guardado se conserva entre cargas aunque la URL ya no traiga el parámetro", async () => {
    await detectarCon({ search: "?estacion=IMPRESION-01" });
    vi.resetModules();
    window.history.replaceState({}, "", "/");
    vi.stubEnv("VITE_DEVICE_IDENTIFIER", "");
    const { createPinia: crearPinia, setActivePinia: activarPinia } = await import("pinia");
    const { api: apiFresca } = await import("../src/api/client");
    const { useSessionStore: usarStore } = await import("../src/stores/session");
    activarPinia(crearPinia());
    apiFresca.get.mockResolvedValue({ data: {} });
    await usarStore().detectarEstacion();
    expect(apiFresca.get).toHaveBeenCalledWith("/estaciones/IMPRESION-01");
  });

  it("sin URL ni guardado usa VITE_DEVICE_IDENTIFIER de build", async () => {
    const url = await detectarCon({ env: "DEV-LOCAL-07" });
    expect(url).toBe("/estaciones/DEV-LOCAL-07");
    expect(localStorage.getItem(CLAVE)).toBeNull();
  });

  it("sin URL, guardado ni variable de build usa el valor de ejemplo", async () => {
    const url = await detectarCon({ env: "" });
    expect(url).toBe("/estaciones/CAPTURA-REFORMA-L1");
  });

  it("?estacion= vacío se ignora y no pisa lo guardado", async () => {
    const url = await detectarCon({ search: "?estacion=", guardado: "PRUEBA-L1" });
    expect(url).toBe("/estaciones/PRUEBA-L1");
    expect(localStorage.getItem(CLAVE)).toBe("PRUEBA-L1");
  });

  it("otros parámetros de la URL no afectan la resolución", async () => {
    const url = await detectarCon({ search: "?foo=1&debug=true", guardado: "PRUEBA-L1" });
    expect(url).toBe("/estaciones/PRUEBA-L1");
  });

  it("si localStorage lanza al leer (modo privado) cae al valor de build", async () => {
    const url = await detectarCon({
      env: "DEV-LOCAL-07",
      storage: () => vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
        throw new Error("SecurityError");
      }),
    });
    expect(url).toBe("/estaciones/DEV-LOCAL-07");
  });

  it("si localStorage lanza al leer y no hay variable de build cae al valor de ejemplo", async () => {
    const url = await detectarCon({
      env: "",
      storage: () => vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
        throw new Error("SecurityError");
      }),
    });
    expect(url).toBe("/estaciones/CAPTURA-REFORMA-L1");
  });

  it("la resolución con localStorage roto no lanza excepción al importar el store", async () => {
    await expect(
      detectarCon({
        search: "?estacion=CAPTURA-L2",
        storage: () => vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
          throw new Error("QuotaExceededError");
        }),
      })
    ).resolves.toBeTypeOf("string");
  });

  // DEFECTO CONOCIDO (session.js, de René): si el equipo se abre con
  // ?estacion=NOMBRE pero localStorage.setItem lanza (modo privado, cuota), la
  // excepción salta el `return delUrl` y el identificador de la URL se descarta
  // en silencio: el equipo se identifica con el valor de build o el de ejemplo
  // (otra estación). Debería usar el de la URL aunque no pueda guardarlo.
  // it.fails pasa mientras el defecto exista; quitar .fails al corregirlo.
  it.fails("con ?estacion=NOMBRE y localStorage no disponible usa igualmente el valor de la URL", async () => {
    const url = await detectarCon({
      search: "?estacion=CAPTURA-L2",
      env: "DEV-LOCAL-07",
      storage: () => vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        throw new Error("QuotaExceededError");
      }),
    });
    expect(url).toBe("/estaciones/CAPTURA-L2");
  });
});
