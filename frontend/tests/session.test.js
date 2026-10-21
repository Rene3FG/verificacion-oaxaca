import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
