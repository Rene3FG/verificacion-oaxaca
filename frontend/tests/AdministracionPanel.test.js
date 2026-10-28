import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import * as directives from "vuetify/directives";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
  },
}));

import { api } from "../src/api/client";
import AdministracionPanel from "../src/components/AdministracionPanel.vue";
import { useSessionStore } from "../src/stores/session";

const USUARIOS = [
  { id: "u1", username: "operador1", nombre_completo: "Ana Pérez", is_active: true },
  { id: "u2", username: "supervisor1", nombre_completo: "Luis Gómez", is_active: false },
];

const ESTACIONES = [
  { id: "e1", name: "Caseta 1", station_type: "captura", center_id: "OAX-01", line_id: 1, device_identifier: "PC-01" },
  { id: "e2", name: "Impresión 1", station_type: "impresion", center_id: "OAX-01", line_id: null, device_identifier: null },
];

const PARAMETROS = [
  { clave: "certificado_offset_x_mm", valor: "0", descripcion: "Desplazamiento horizontal", origen: "default" },
  { clave: "certificado_rechazo_dias_vigencia", valor: "30", descripcion: "Vigencia del rechazo", origen: "sistema" },
];

// Servidor simulado: cada prueba ajusta srv antes de montar.
let srv;
let montados = [];

function reiniciarServidor() {
  srv = {
    get: { "/usuarios": USUARIOS, "/estaciones": ESTACIONES, "/parametros": PARAMETROS },
    fallas: {}, // url -> detail (undefined = sin detail)
    post: {}, // url -> handler
    patch: {}, // prefijo -> handler
  };
}

function rechazo(detail) {
  return Promise.reject({ response: { status: 422, data: detail === undefined ? {} : { detail } } });
}

function instalarApi() {
  api.get.mockImplementation((url) => {
    if (url in srv.fallas) return rechazo(srv.fallas[url]);
    if (url in srv.get) return Promise.resolve({ data: srv.get[url] });
    return Promise.reject(new Error(`GET no simulado: ${url}`));
  });
  api.post.mockImplementation((url, body) => {
    if (url in srv.post) return srv.post[url](url, body);
    return Promise.resolve({ data: {} });
  });
  api.patch.mockImplementation((url, body) => {
    const hit = Object.entries(srv.patch).find(([prefijo]) => url.startsWith(prefijo));
    if (hit) return hit[1](url, body);
    return Promise.resolve({ data: {} });
  });
}

const SLOTS = {
  permisos: '<p data-test="slot-permisos">Contenido de permisos</p>',
  limites: '<p data-test="slot-limites">Contenido de límites</p>',
  equipos: '<p data-test="slot-equipos">Contenido de equipos</p>',
  folios: '<p data-test="slot-folios">Contenido de folios</p>',
  semestre: '<p data-test="slot-semestre">Contenido de semestre</p>',
};

async function montar({ destino, estacion = { center_id: "OAX-01" } } = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore();
  session.estacion = estacion;
  instalarApi();

  const vuetify = createVuetify({ components, directives });
  const w = mount(AdministracionPanel, {
    props: destino === undefined ? {} : { destino },
    slots: SLOTS,
    global: { plugins: [pinia, vuetify] },
  });
  montados.push(w);
  await flushPromises();
  return w;
}

function boton(w, texto) {
  return w.findAll("button").find((b) => b.text() === texto);
}

async function ir(w, texto) {
  await boton(w, texto).trigger("click");
  await flushPromises();
}

function slot(w, nombre) {
  return w.find(`[data-test="slot-${nombre}"]`).exists();
}

beforeEach(() => {
  vi.clearAllMocks();
  reiniciarServidor();
});

afterEach(() => {
  montados.forEach((w) => w.unmount());
  montados = [];
});

describe("AdministracionPanel - Carga inicial", () => {
  it("al montar consulta usuarios, estaciones del centro y parámetros del sistema", async () => {
    await montar();
    expect(api.get).toHaveBeenCalledWith("/usuarios");
    expect(api.get).toHaveBeenCalledWith("/estaciones", { params: { center_id: "OAX-01" } });
    expect(api.get).toHaveBeenCalledWith("/parametros");
  });

  it("arranca en la subpestaña Usuarios y lista a los usuarios con su estado", async () => {
    const w = await montar();
    expect(w.vm.sub).toBe("usuarios");
    const t = w.text();
    expect(t).toContain("operador1");
    expect(t).toContain("Ana Pérez");
    expect(t).toContain("supervisor1");
    expect(t).toContain("Activo");
    expect(t).toContain("Inactivo");
    expect(t).toContain("Desactivar");
    expect(t).toContain("Reactivar");
  });

  it("sin estación en sesión consulta estaciones sin centro", async () => {
    await montar({ estacion: null });
    expect(api.get).toHaveBeenCalledWith("/estaciones", { params: { center_id: undefined } });
  });

  it.each([
    ["/usuarios", "No se pudo cargar la lista de usuarios."],
    ["/estaciones", "No se pudo cargar el listado de estaciones."],
    ["/parametros", "No se pudo cargar los parámetros de sistema."],
  ])("falla de %s: muestra el detail del backend y, sin detail, el mensaje genérico", async (url, generico) => {
    srv.fallas[url] = `Falla en ${url}`;
    const w1 = await montar();
    expect(w1.text()).toContain(`Falla en ${url}`);

    srv.fallas[url] = undefined;
    const w2 = await montar();
    expect(w2.text()).toContain(generico);
  });

  it("los indicadores de carga se apagan aunque la consulta falle", async () => {
    srv.fallas["/usuarios"] = "x";
    srv.fallas["/estaciones"] = "x";
    srv.fallas["/parametros"] = "x";
    const w = await montar();
    expect(w.vm.cargandoUsuarios).toBe(false);
    expect(w.vm.cargandoEstaciones).toBe(false);
    expect(w.vm.cargandoParametros).toBe(false);
  });
});

describe("AdministracionPanel - Navegación entre subpestañas", () => {
  it("muestra una sola sección a la vez", async () => {
    const w = await montar();
    expect(w.text()).toContain("Nuevo usuario");
    expect(w.text()).not.toContain("Nueva estación");

    await ir(w, "Estaciones");
    expect(w.vm.sub).toBe("estaciones");
    expect(w.text()).toContain("Nueva estación");
    expect(w.text()).not.toContain("Nuevo usuario");
  });

  it("Estaciones lista nombre, tipo, línea y dispositivo, con guion cuando faltan", async () => {
    const w = await montar();
    await ir(w, "Estaciones");
    const t = w.text();
    expect(t).toContain("Caseta 1");
    expect(t).toContain("captura");
    expect(t).toContain("PC-01");
    expect(t).toContain("Impresión 1");
    const filas = w.findAll("tbody tr");
    expect(filas[1].text()).toContain("—");
  });

  it("Estaciones sin registros muestra el mensaje vacío", async () => {
    srv.get["/estaciones"] = [];
    const w = await montar();
    await ir(w, "Estaciones");
    expect(w.text()).toContain("Sin estaciones activas en este centro.");
  });

  it("Roles y permisos renderiza el slot permisos", async () => {
    const w = await montar();
    expect(slot(w, "permisos")).toBe(false);
    await ir(w, "Roles y permisos");
    expect(w.vm.sub).toBe("permisos");
    expect(slot(w, "permisos")).toBe(true);
    expect(w.text()).not.toContain("Nuevo usuario");
  });

  it("Parámetros y catálogos abre el selector de catálogos con Parámetros del sistema por defecto", async () => {
    const w = await montar();
    await ir(w, "Parámetros y catálogos");
    expect(w.vm.sub).toBe("catalogos");
    expect(w.vm.catalogo).toBe("parametros");
    const t = w.text();
    expect(t).toContain("Parámetros del sistema");
    expect(t).toContain("Límites de emisión");
    expect(t).toContain("Equipos");
    expect(t).toContain("Folios");
    expect(t).toContain("Periodos y prórrogas");
    expect(t).toContain("certificado_rechazo_dias_vigencia");
  });

  it("el selector de catálogos solo aparece dentro de Parámetros y catálogos", async () => {
    const w = await montar();
    expect(w.text()).not.toContain("Periodos y prórrogas");
    await ir(w, "Estaciones");
    expect(w.text()).not.toContain("Periodos y prórrogas");
  });

  it.each([
    ["Límites de emisión", "limites"],
    ["Equipos", "equipos"],
    ["Folios", "folios"],
    ["Periodos y prórrogas", "semestre"],
  ])("el catálogo %s renderiza su slot %s y oculta los demás", async (texto, nombre) => {
    const w = await montar();
    await ir(w, "Parámetros y catálogos");
    await ir(w, texto);
    expect(w.vm.catalogo).toBe(nombre);
    for (const otro of ["limites", "equipos", "folios", "semestre"]) {
      expect(slot(w, otro)).toBe(otro === nombre);
    }
    expect(w.text()).not.toContain("certificado_rechazo_dias_vigencia");
  });

  it("los parámetros marcan los valores por defecto sin configurar", async () => {
    const w = await montar();
    await ir(w, "Parámetros y catálogos");
    const filas = w.findAll("tbody tr");
    expect(filas[0].text()).toContain("sin configurar, valor por defecto");
    expect(filas[1].text()).not.toContain("sin configurar");
  });
});

describe("AdministracionPanel - Prop destino (salto desde Errores y reintentos)", () => {
  it("con destino inicial abre directamente la sección y el catálogo indicados", async () => {
    const w = await montar({ destino: { seccion: "catalogos", catalogo: "folios" } });
    expect(w.vm.sub).toBe("catalogos");
    expect(w.vm.catalogo).toBe("folios");
    expect(slot(w, "folios")).toBe(true);
    expect(w.text()).not.toContain("Nuevo usuario");
  });

  it("destino sin catálogo conserva el catálogo por defecto", async () => {
    const w = await montar({ destino: { seccion: "catalogos" } });
    expect(w.vm.sub).toBe("catalogos");
    expect(w.vm.catalogo).toBe("parametros");
  });

  it("destino a otra sección no toca el catálogo", async () => {
    const w = await montar({ destino: { seccion: "estaciones" } });
    expect(w.vm.sub).toBe("estaciones");
    expect(w.vm.catalogo).toBe("parametros");
    expect(w.text()).toContain("Nueva estación");
  });

  it("sin destino (null) se queda en Usuarios", async () => {
    const w = await montar({ destino: null });
    expect(w.vm.sub).toBe("usuarios");
  });

  it("si el destino llega después del montaje, salta a la sección indicada", async () => {
    const w = await montar({ destino: null });
    await w.setProps({ destino: { seccion: "catalogos", catalogo: "folios" } });
    await flushPromises();
    expect(w.vm.sub).toBe("catalogos");
    expect(slot(w, "folios")).toBe(true);
  });

  it("un destino nuevo vuelve a saltar aunque el supervisor haya navegado a otra parte", async () => {
    const w = await montar({ destino: { seccion: "catalogos", catalogo: "folios" } });
    await ir(w, "Usuarios");
    expect(w.vm.sub).toBe("usuarios");

    await w.setProps({ destino: { seccion: "catalogos", catalogo: "folios" } });
    await flushPromises();
    expect(w.vm.sub).toBe("catalogos");
    expect(w.vm.catalogo).toBe("folios");
  });

  it("la misma referencia de destino no vuelve a disparar el salto", async () => {
    const destino = { seccion: "catalogos", catalogo: "folios" };
    const w = await montar({ destino });
    await ir(w, "Usuarios");
    await w.setProps({ destino });
    await flushPromises();
    expect(w.vm.sub).toBe("usuarios");
  });

  it("volver a poner el destino en null no cambia la sección actual", async () => {
    const w = await montar({ destino: { seccion: "estaciones" } });
    await w.setProps({ destino: null });
    await flushPromises();
    expect(w.vm.sub).toBe("estaciones");
  });

  it("el salto cambia de catálogo cuando ya estaba en catálogos", async () => {
    const w = await montar({ destino: { seccion: "catalogos", catalogo: "limites" } });
    expect(slot(w, "limites")).toBe(true);
    await w.setProps({ destino: { seccion: "catalogos", catalogo: "semestre" } });
    await flushPromises();
    expect(slot(w, "semestre")).toBe(true);
    expect(slot(w, "limites")).toBe(false);
  });
});

describe("AdministracionPanel - Usuarios (alta y edición)", () => {
  it("'Nuevo usuario' abre el diálogo de alta con el formulario vacío", async () => {
    const w = await montar();
    await boton(w, "Nuevo usuario").trigger("click");
    expect(w.vm.usuarioAbierto).toBe(true);
    expect(w.vm.usuarioEditandoId).toBeNull();
    expect(w.vm.usuarioForm).toEqual({ username: "", nombre_completo: "", password: "" });
  });

  it("'Editar' precarga el usuario y deja la contraseña vacía", async () => {
    const w = await montar();
    w.vm.usuarioForm.password = "residuo";
    const editar = w.findAll("tbody tr")[0].findAll("button").find((b) => b.text() === "Editar");
    await editar.trigger("click");
    expect(w.vm.usuarioAbierto).toBe(true);
    expect(w.vm.usuarioEditandoId).toBe("u1");
    expect(w.vm.usuarioForm).toEqual({
      username: "operador1",
      nombre_completo: "Ana Pérez",
      password: "",
    });
  });

  it("alta: crea el usuario con el formulario completo, avisa, cierra y recarga la lista", async () => {
    const w = await montar();
    w.vm.abrirUsuario();
    Object.assign(w.vm.usuarioForm, {
      username: "nuevo1",
      nombre_completo: "Nuevo Usuario",
      password: "Segura123",
    });
    api.get.mockClear();

    await w.vm.guardarUsuario();
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith("/usuarios", {
      username: "nuevo1",
      nombre_completo: "Nuevo Usuario",
      password: "Segura123",
    });
    expect(api.patch).not.toHaveBeenCalled();
    expect(w.vm.aviso).toBe("Usuario nuevo1 creado. Asígnale permisos en la pestaña Permisos.");
    expect(w.vm.usuarioAbierto).toBe(false);
    expect(api.get).toHaveBeenCalledWith("/usuarios");
    expect(w.vm.guardandoUsuario).toBe(false);
  });

  it("edición: solo envía nombre_completo cuando no se cambia la contraseña", async () => {
    const w = await montar();
    w.vm.abrirUsuario(USUARIOS[0]);
    w.vm.usuarioForm.nombre_completo = "Ana María Pérez";

    await w.vm.guardarUsuario();
    await flushPromises();

    expect(api.patch).toHaveBeenCalledWith("/usuarios/u1", { nombre_completo: "Ana María Pérez" });
    expect(api.post).not.toHaveBeenCalled();
    expect(w.vm.aviso).toBe("Usuario actualizado.");
    expect(w.vm.usuarioAbierto).toBe(false);
  });

  it("edición: incluye la contraseña nueva cuando se captura y nunca reenvía el usuario", async () => {
    const w = await montar();
    w.vm.abrirUsuario(USUARIOS[0]);
    w.vm.usuarioForm.password = "Nueva12345";

    await w.vm.guardarUsuario();

    const [, cuerpo] = api.patch.mock.calls.find(([u]) => u === "/usuarios/u1");
    expect(cuerpo).toEqual({ nombre_completo: "Ana Pérez", password: "Nueva12345" });
    expect(cuerpo).not.toHaveProperty("username");
  });

  it("un error de validación (detail como lista) muestra el primer msg y conserva el diálogo", async () => {
    srv.post["/usuarios"] = () =>
      rechazo([{ loc: ["body", "password"], msg: "La contraseña no cumple la política" }]);
    const w = await montar();
    w.vm.abrirUsuario();
    await w.vm.guardarUsuario();
    await flushPromises();

    expect(w.vm.error).toBe("La contraseña no cumple la política");
    expect(w.text()).toContain("La contraseña no cumple la política");
    expect(w.vm.usuarioAbierto).toBe(true);
    expect(w.vm.guardandoUsuario).toBe(false);
  });

  it("un error con detail de texto se muestra tal cual", async () => {
    srv.post["/usuarios"] = () => rechazo("El usuario ya existe");
    const w = await montar();
    w.vm.abrirUsuario();
    await w.vm.guardarUsuario();
    expect(w.vm.error).toBe("El usuario ya existe");
  });

  it("sin detail usa el mensaje genérico de guardado", async () => {
    srv.post["/usuarios"] = () => rechazo(undefined);
    const w = await montar();
    w.vm.abrirUsuario();
    await w.vm.guardarUsuario();
    expect(w.vm.error).toBe("No se pudo guardar el usuario.");
  });

  it("guardar limpia el error anterior antes de intentar", async () => {
    const w = await montar();
    w.vm.error = "error viejo";
    w.vm.abrirUsuario();
    await w.vm.guardarUsuario();
    expect(w.vm.error).toBeNull();
  });
});

describe("AdministracionPanel - Usuarios (activar y desactivar)", () => {
  it("desactiva a un usuario activo y recarga la lista", async () => {
    const w = await montar();
    api.get.mockClear();
    await w.vm.alternarUsuario(USUARIOS[0]);
    expect(api.patch).toHaveBeenCalledWith("/usuarios/u1", { is_active: false });
    expect(api.get).toHaveBeenCalledWith("/usuarios");
  });

  it("reactiva a un usuario inactivo", async () => {
    const w = await montar();
    await w.vm.alternarUsuario(USUARIOS[1]);
    expect(api.patch).toHaveBeenCalledWith("/usuarios/u2", { is_active: true });
  });

  it("los botones Desactivar y Reactivar de la tabla disparan el cambio de estado", async () => {
    const w = await montar();
    const filas = w.findAll("tbody tr");
    await filas[0].findAll("button").find((b) => b.text() === "Desactivar").trigger("click");
    await flushPromises();
    expect(api.patch).toHaveBeenCalledWith("/usuarios/u1", { is_active: false });

    await filas[1].findAll("button").find((b) => b.text() === "Reactivar").trigger("click");
    await flushPromises();
    expect(api.patch).toHaveBeenCalledWith("/usuarios/u2", { is_active: true });
  });

  it("si falla muestra el error y no recarga", async () => {
    srv.patch["/usuarios/"] = () => rechazo("No puedes desactivarte a ti mismo");
    const w = await montar();
    api.get.mockClear();
    await w.vm.alternarUsuario(USUARIOS[0]);
    expect(w.vm.error).toBe("No puedes desactivarte a ti mismo");
    expect(api.get).not.toHaveBeenCalled();
  });

  it("sin detail usa el mensaje genérico del cambio de estado", async () => {
    srv.patch["/usuarios/"] = () => rechazo(undefined);
    const w = await montar();
    await w.vm.alternarUsuario(USUARIOS[0]);
    expect(w.vm.error).toBe("No se pudo cambiar el estado del usuario.");
  });
});

describe("AdministracionPanel - Estaciones (alta, edición y baja)", () => {
  it("'Nueva estación' abre el diálogo con valores por defecto y el centro de la sesión", async () => {
    const w = await montar();
    await ir(w, "Estaciones");
    w.vm.estacionForm.name = "residuo";
    await boton(w, "Nueva estación").trigger("click");
    expect(w.vm.estacionAbierta).toBe(true);
    expect(w.vm.estacionEditandoId).toBeNull();
    expect(w.vm.estacionForm).toEqual({
      name: "",
      station_type: "captura",
      center_id: "OAX-01",
      line_id: null,
      device_identifier: "",
    });
  });

  it("sin centro en sesión el formulario de alta deja el centro vacío", async () => {
    const w = await montar({ estacion: null });
    w.vm.abrirEstacion();
    expect(w.vm.estacionForm.center_id).toBe("");
  });

  it("editar precarga la estación seleccionada", async () => {
    const w = await montar();
    w.vm.abrirEstacion(ESTACIONES[0]);
    expect(w.vm.estacionEditandoId).toBe("e1");
    expect(w.vm.estacionForm).toEqual({
      name: "Caseta 1",
      station_type: "captura",
      center_id: "OAX-01",
      line_id: 1,
      device_identifier: "PC-01",
    });
  });

  it("editar una estación sin línea ni dispositivo los deja en null y vacío", async () => {
    const w = await montar();
    w.vm.abrirEstacion(ESTACIONES[1]);
    expect(w.vm.estacionForm.line_id).toBeNull();
    expect(w.vm.estacionForm.device_identifier).toBe("");
  });

  it("alta: envía la estación, normaliza dispositivo vacío a null, avisa, cierra y recarga", async () => {
    const w = await montar();
    w.vm.abrirEstacion();
    Object.assign(w.vm.estacionForm, { name: "Prueba L2", station_type: "prueba", line_id: 2 });
    api.get.mockClear();

    await w.vm.guardarEstacion();
    await flushPromises();

    expect(api.post).toHaveBeenCalledWith("/estaciones", {
      name: "Prueba L2",
      station_type: "prueba",
      center_id: "OAX-01",
      line_id: 2,
      device_identifier: null,
    });
    expect(w.vm.aviso).toBe("Estación Prueba L2 creada.");
    expect(w.vm.estacionAbierta).toBe(false);
    expect(api.get).toHaveBeenCalledWith("/estaciones", expect.anything());
    expect(w.vm.guardandoEstacion).toBe(false);
  });

  it("línea vacía ('') viaja como null y la línea 0 se conserva", async () => {
    const w = await montar();
    w.vm.abrirEstacion();
    w.vm.estacionForm.name = "A";
    w.vm.estacionForm.line_id = "";
    await w.vm.guardarEstacion();
    expect(api.post.mock.calls.at(-1)[1].line_id).toBeNull();

    w.vm.abrirEstacion();
    w.vm.estacionForm.name = "B";
    w.vm.estacionForm.line_id = 0;
    await w.vm.guardarEstacion();
    expect(api.post.mock.calls.at(-1)[1].line_id).toBe(0);
  });

  it("el identificador de dispositivo capturado se envía tal cual", async () => {
    const w = await montar();
    w.vm.abrirEstacion();
    Object.assign(w.vm.estacionForm, { name: "C", device_identifier: "IMP-77" });
    await w.vm.guardarEstacion();
    expect(api.post.mock.calls.at(-1)[1].device_identifier).toBe("IMP-77");
  });

  it("edición: actualiza por PATCH y avisa", async () => {
    const w = await montar();
    w.vm.abrirEstacion(ESTACIONES[0]);
    w.vm.estacionForm.name = "Caseta 1 renombrada";

    await w.vm.guardarEstacion();
    await flushPromises();

    expect(api.patch).toHaveBeenCalledWith(
      "/estaciones/e1",
      expect.objectContaining({ name: "Caseta 1 renombrada", device_identifier: "PC-01" })
    );
    expect(api.post).not.toHaveBeenCalled();
    expect(w.vm.aviso).toBe("Estación actualizada.");
  });

  it("un error de validación (detail como lista) muestra el primer msg y conserva el diálogo", async () => {
    srv.post["/estaciones"] = () => rechazo([{ loc: ["body", "name"], msg: "El nombre es obligatorio" }]);
    const w = await montar();
    w.vm.abrirEstacion();
    await w.vm.guardarEstacion();
    expect(w.vm.error).toBe("El nombre es obligatorio");
    expect(w.vm.estacionAbierta).toBe(true);
    expect(w.vm.guardandoEstacion).toBe(false);
  });

  it("sin detail usa el mensaje genérico de guardado de estación", async () => {
    srv.post["/estaciones"] = () => rechazo(undefined);
    const w = await montar();
    w.vm.abrirEstacion();
    await w.vm.guardarEstacion();
    expect(w.vm.error).toBe("No se pudo guardar la estación.");
  });

  it("desactivar marca is_active false, avisa con el nombre y recarga", async () => {
    const w = await montar();
    api.get.mockClear();
    await w.vm.desactivarEstacion(ESTACIONES[0]);
    expect(api.patch).toHaveBeenCalledWith("/estaciones/e1", { is_active: false });
    expect(w.vm.aviso).toBe("Estación Caseta 1 desactivada.");
    expect(api.get).toHaveBeenCalledWith("/estaciones", expect.anything());
  });

  it("el botón Desactivar de la tabla desactiva esa estación", async () => {
    const w = await montar();
    await ir(w, "Estaciones");
    const fila = w.findAll("tbody tr")[1];
    await fila.findAll("button").find((b) => b.text() === "Desactivar").trigger("click");
    await flushPromises();
    expect(api.patch).toHaveBeenCalledWith("/estaciones/e2", { is_active: false });
  });

  it("si falla desactivar muestra el error y no avisa éxito", async () => {
    srv.patch["/estaciones/"] = () => rechazo("La estación tiene una sesión activa");
    const w = await montar();
    await w.vm.desactivarEstacion(ESTACIONES[0]);
    expect(w.vm.error).toBe("La estación tiene una sesión activa");
    expect(w.vm.aviso).toBeNull();
  });
});

describe("AdministracionPanel - Parámetros del sistema", () => {
  it("editar precarga el valor actual del parámetro", async () => {
    const w = await montar();
    w.vm.abrirParametro(PARAMETROS[1]);
    expect(w.vm.parametroAbierto).toBe(true);
    expect(w.vm.parametroEditando.clave).toBe("certificado_rechazo_dias_vigencia");
    expect(w.vm.parametroValor).toBe("30");
  });

  it("guardar envía el valor por clave, avisa, cierra y recarga", async () => {
    const w = await montar();
    w.vm.abrirParametro(PARAMETROS[1]);
    w.vm.parametroValor = "45";
    api.get.mockClear();

    await w.vm.guardarParametro();
    await flushPromises();

    expect(api.patch).toHaveBeenCalledWith("/parametros/certificado_rechazo_dias_vigencia", { valor: "45" });
    expect(w.vm.aviso).toBe("Parámetro certificado_rechazo_dias_vigencia actualizado.");
    expect(w.vm.parametroAbierto).toBe(false);
    expect(api.get).toHaveBeenCalledWith("/parametros");
    expect(w.vm.guardandoParametro).toBe(false);
  });

  it("el botón Editar de la tabla abre el parámetro correcto", async () => {
    const w = await montar();
    await ir(w, "Parámetros y catálogos");
    const editar = w.findAll("tbody tr")[0].findAll("button").find((b) => b.text() === "Editar");
    await editar.trigger("click");
    expect(w.vm.parametroEditando.clave).toBe("certificado_offset_x_mm");
    expect(w.vm.parametroValor).toBe("0");
  });

  it("si falla conserva el diálogo y muestra el error del backend", async () => {
    srv.patch["/parametros/"] = () => rechazo("Valor fuera de rango (1-365)");
    const w = await montar();
    w.vm.abrirParametro(PARAMETROS[1]);
    w.vm.parametroValor = "999";
    await w.vm.guardarParametro();
    await flushPromises();
    expect(w.vm.error).toBe("Valor fuera de rango (1-365)");
    expect(w.vm.parametroAbierto).toBe(true);
    expect(w.vm.guardandoParametro).toBe(false);
  });

  it("sin detail usa el mensaje genérico de guardado de parámetro", async () => {
    srv.patch["/parametros/"] = () => rechazo(undefined);
    const w = await montar();
    w.vm.abrirParametro(PARAMETROS[0]);
    await w.vm.guardarParametro();
    expect(w.vm.error).toBe("No se pudo guardar el parámetro.");
  });
});

describe("AdministracionPanel - Alertas", () => {
  it("el aviso y el error se pueden cerrar con la X", async () => {
    const w = await montar();
    w.vm.aviso = "Hecho.";
    w.vm.error = "Falló.";
    await flushPromises();
    expect(w.findAll(".v-alert")).toHaveLength(2);

    for (const cierre of w.findAll(".v-alert .v-alert__close button")) {
      await cierre.trigger("click");
    }
    await flushPromises();

    expect(w.vm.aviso).toBeNull();
    expect(w.vm.error).toBeNull();
    expect(w.find(".v-alert").exists()).toBe(false);
  });

  it("sin mensajes no se dibuja ninguna alerta", async () => {
    const w = await montar();
    expect(w.find(".v-alert").exists()).toBe(false);
  });
});
