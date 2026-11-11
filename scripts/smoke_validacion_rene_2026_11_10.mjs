import fs from "node:fs";
import path from "node:path";
import puppeteer from "../frontend/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js";

const ARTIFACTS_DIR = "C:\\Users\\LENOVO 330s\\.gemini\\antigravity\\brain\\36ef5aa2-68ed-4e45-8857-5b27e903c963";

function esRutaApi(url) {
  return url.startsWith("http://localhost:5173/api/") && !url.includes("/src/");
}

function buscarNavegador() {
  const rutas = [
    process.env.CHROME_BIN,
    process.env.PUPPETEER_EXECUTABLE_PATH,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  ].filter(Boolean);

  for (const r of rutas) {
    if (fs.existsSync(r)) return r;
  }
  throw new Error("No se encontró ningún ejecutable de Chromium.");
}

const CHECKLIST_NOM047 = [
  { clave: "revision_componentes", etiqueta: "Revisión visual de componentes de control de emisiones" },
  { clave: "tapon_combustible", etiqueta: "Tapón del tanque de combustible" },
  { clave: "tapon_aceite", etiqueta: "Tapón del depósito de aceite" },
  { clave: "varilla_aceite", etiqueta: "Varilla de medición de nivel de aceite" },
  { clave: "filtro_aire", etiqueta: "Filtro de aire" },
  { clave: "fuga_escape", etiqueta: "Fugas en el sistema de escape" },
  { clave: "fuga_fluidos", etiqueta: "Fuga de fluidos (aceite, refrigerante, combustible)" },
  { clave: "neumaticos", etiqueta: "Neumáticos en mal estado o inadecuados" },
];

const USUARIOS_MOCK = [
  {
    id: "u-101",
    username: "tecnico.reforma",
    nombre_completo: "Carlos Mendoza Silva",
    clave_tecnico: "TEC-REF-01",
    is_active: true,
    must_change_password: true,
  },
  {
    id: "u-102",
    username: "supervisor.general",
    nombre_completo: "René García",
    clave_tecnico: null,
    is_active: true,
    must_change_password: false,
  },
];

const EXPEDIENTE_MOCK = {
  id: "exp-01",
  placa: "TLX-789-A",
  vin: "3VW12345678901234",
  marca: "VOLKSWAGEN",
  submarca: "VENTO",
  modelo: 2021,
  estado: "INSPECCION_VISUAL_PENDIENTE",
  center_id: "reforma",
  line_id: 1,
  vehiculo: {
    niv: "3VW12345678901234",
    marca: "VOLKSWAGEN",
    linea: "VENTO",
    modelo: 2021,
  },
};

// -----------------------------------------------------------------
// CASO 1: Formulario de cambio obligatorio de contraseña (LoginView Estado D)
// -----------------------------------------------------------------
async function probarCaso1(browser) {
  console.log("\n=======================================================");
  console.log("--- [CASO 1] LoginView con must_change_password: true ---");
  console.log("=======================================================");

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 900 });

  const llamadasApi = [];
  await page.setRequestInterception(true);
  page.on("request", (req) => {
    const url = req.url();
    const method = req.method();

    if (!esRutaApi(url)) return req.continue();
    llamadasApi.push({ method, url });

    if (url.includes("/api/sync/estado")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ central: "CONECTADO", sincronizando: 0, pendientes: 0 }),
      });
    }

    if (url.includes("/api/estaciones/login")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "sess-temp-01",
          user_id: "u-101",
          workstation_id: "ws-cap-01",
          must_change_password: true,
          can_supervise: false,
        }),
      });
    }

    if (url.includes("/api/estaciones/")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "ws-cap-01",
          name: "ESTACION-CAPTURA-L1",
          station_type: "captura",
          center_id: "reforma",
          line_id: 1,
          allowed_line_ids: [1],
        }),
      });
    }

    if (url.includes("/api/usuarios/me/password") && method === "POST") {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, detail: "Contraseña actualizada exitosamente." }),
      });
    }

    return req.respond({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.goto("http://localhost:5173/?estacion=CAPTURA-L1", { waitUntil: "networkidle0" });

  await page.waitForSelector("input[type=password]");
  const inputs = await page.$$("input");
  await inputs[0].type("tecnico.reforma");
  await inputs[1].type("Temporal123!");

  const btnEntrar = await page.waitForSelector("button.v-btn--size-large");
  await btnEntrar.click();

  // Esperar a que aparezca la tarjeta "Cambia tu contraseña"
  await page.waitForFunction(() => document.body.innerText.includes("Cambia tu contraseña"));
  console.log("✓ Título 'Cambia tu contraseña' renderizado correctamente.");

  const subtituloVisible = await page.evaluate(() =>
    document.body.innerText.includes("Tu contraseña la asignó un supervisor. Elige una nueva"),
  );
  if (!subtituloVisible) throw new Error("No se encontró el subtítulo normativo");
  console.log("✓ Subtítulo normativo y explicativo visible.");

  const passwordInputs = await page.$$("input[type=password]");
  if (passwordInputs.length < 2) throw new Error("Faltan inputs para nueva contraseña y confirmación");

  // Probar mismatch
  await passwordInputs[0].type("ClaveSegura2026!");
  await passwordInputs[1].type("Mismatch2026!");
  const btnGuardar = await page.waitForFunction(() => {
    const btns = Array.from(document.querySelectorAll("button"));
    return btns.find((b) => b.innerText.includes("Guardar y continuar"));
  });
  await btnGuardar.click();

  await page.waitForFunction(() =>
    document.body.innerText.includes("La confirmación no coincide con la contraseña nueva."),
  );
  console.log("✓ Validación cliente: advertencia de contraseñas no coincidentes funciona.");

  // Limpiar y poner contraseñas iguales
  await page.evaluate(() => {
    const inputs = document.querySelectorAll("input[type=password]");
    for (const input of inputs) {
      input.value = "";
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });
  await passwordInputs[0].type("ClaveSegura2026!");
  await passwordInputs[1].type("ClaveSegura2026!");

  const screenshotPath = path.join(ARTIFACTS_DIR, "evidencia_login_cambio_password.png");
  await page.screenshot({ path: screenshotPath, fullPage: false });
  console.log(`✓ Screenshot guardado: ${screenshotPath}`);

  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll("button"));
    const b = btns.find((x) => x.innerText.includes("Guardar y continuar"));
    if (b) b.click();
  });
  await new Promise((r) => setTimeout(r, 600));

  const passwordLlamada = llamadasApi.find((c) => c.url.includes("/api/usuarios/me/password") && c.method === "POST");
  if (!passwordLlamada) throw new Error("No se realizó la petición POST a /api/usuarios/me/password");
  console.log("✓ Petición POST /api/usuarios/me/password ejecutada exitosamente.");

  await page.close();
}

// -----------------------------------------------------------------
// CASO 2: Panel de Administración - Botón Desbloquear y Chip must_change_password
// -----------------------------------------------------------------
async function probarCaso2(browser) {
  console.log("\n=======================================================");
  console.log("--- [CASO 2] AdministracionPanel: Desbloqueo y chips ---");
  console.log("=======================================================");

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 900 });

  const llamadasApi = [];
  await page.setRequestInterception(true);
  page.on("request", (req) => {
    const url = req.url();
    const method = req.method();

    if (!esRutaApi(url)) return req.continue();
    llamadasApi.push({ method, url });

    if (url.includes("/api/sync/estado")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ central: "CONECTADO", sincronizando: 0, pendientes: 0 }),
      });
    }

    if (url.includes("/api/estaciones/login")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "sess-sup-01",
          user_id: "u-102",
          workstation_id: "ws-sup-01",
          must_change_password: false,
          can_supervise: true,
        }),
      });
    }

    if (url.includes("/api/estaciones/")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "ws-sup-01",
          name: "ESTACION-SUPERVISOR-L1",
          station_type: "captura",
          center_id: "reforma",
          line_id: 1,
          allowed_line_ids: [1],
        }),
      });
    }

    if (url.includes("/api/usuarios/") && url.includes("/desbloquear") && method === "POST") {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, detail: "Usuario desbloqueado." }),
      });
    }

    if (url.includes("/api/usuarios") && method === "GET") {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(USUARIOS_MOCK),
      });
    }

    if (url.includes("/api/supervision/monitor")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    }

    if (url.includes("/api/catalogos/municipios")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    }

    return req.respond({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.goto("http://localhost:5173/?estacion=SUPERVISOR-L1", { waitUntil: "networkidle0" });

  await page.waitForSelector("input[type=password]");
  await page.evaluate(() => {
    const textInput = document.querySelector("input:not([type=password])");
    const passInput = document.querySelector("input[type=password]");
    if (textInput) {
      textInput.value = "supervisor.general";
      textInput.dispatchEvent(new Event("input", { bubbles: true }));
    }
    if (passInput) {
      passInput.value = "Admin2026!";
      passInput.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });

  const btnSupEntrar = await page.waitForSelector("button.v-btn--size-large");
  await btnSupEntrar.click();

  // Esperar a que la SPA navegue a /captura
  await page.waitForFunction(() => window.location.pathname === "/captura");
  console.log("✓ Redirección a /captura confirmada.");

  await new Promise((r) => setTimeout(r, 1000));
  const botonesInfo = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll("button"));
    return btns.map((b) => ({ text: b.innerText, html: b.innerHTML }));
  });
  console.log("Botones encontrados en /captura:", JSON.stringify(botonesInfo));

  // Esperar a que aparezca el botón "Supervisor" en la barra superior
  const btnSupervisor = await page.waitForFunction(() => {
    const btns = Array.from(document.querySelectorAll("button"));
    return btns.find((b) => b.innerText.toLowerCase().includes("supervisor"));
  });
  console.log("✓ Botón 'Supervisor' detectado en la barra superior.");
  await btnSupervisor.click();

  // Esperar SupervisorView
  await page.waitForSelector(".v-tabs");
  console.log("✓ SupervisorView montada con pestañas operativas.");

  // Click en pestaña Administración
  await page.evaluate(() => {
    const tabs = Array.from(document.querySelectorAll(".v-tab"));
    const tabAdmin = tabs.find((t) => t.innerText.toLowerCase().includes("administración"));
    if (tabAdmin) tabAdmin.click();
  });

  // Esperar tabla de usuarios
  await page.waitForFunction(() => {
    return document.body.innerText.includes("tecnico.reforma") && document.body.innerText.includes("TEC-REF-01");
  });
  console.log("✓ Tabla de usuarios renderizada con columna Clave técnico ('TEC-REF-01').");

  // Verificar chip "Cambio de contraseña pendiente"
  const chipVisible = await page.evaluate(() => document.body.innerText.includes("Cambio de contraseña pendiente"));
  if (!chipVisible) throw new Error("No se encontró el chip 'Cambio de contraseña pendiente'");
  console.log("✓ Chip 'Cambio de contraseña pendiente' visible para tecnico.reforma.");

  // Verificar y pulsar botón "Desbloquear"
  const btnDesbloquear = await page.waitForFunction(() => {
    const btns = Array.from(document.querySelectorAll("button"));
    return btns.find((b) => b.innerText.trim().toLowerCase() === "desbloquear");
  });
  console.log("✓ Botón 'Desbloquear' renderizado.");
  await btnDesbloquear.click();

  // Esperar confirmación
  await page.waitForFunction(() =>
    document.body.innerText.includes("tecnico.reforma puede volver a iniciar sesión."),
  );
  console.log("✓ Aviso de desbloqueo mostrado: 'tecnico.reforma puede volver a iniciar sesión.'");

  const llamadaDesbloqueo = llamadasApi.find((c) => c.url.includes("/desbloquear") && c.method === "POST");
  if (!llamadaDesbloqueo) throw new Error("No se realizó la llamada POST /api/usuarios/u-101/desbloquear");
  console.log("✓ Petición POST /api/usuarios/u-101/desbloquear confirmada exitosamente.");

  const screenshotAdminPath = path.join(ARTIFACTS_DIR, "evidencia_admin_desbloqueo.png");
  await page.screenshot({ path: screenshotAdminPath, fullPage: false });
  console.log(`✓ Screenshot guardado: ${screenshotAdminPath}`);

  await page.close();
}

// -----------------------------------------------------------------
// CASO 3: Captura - Inspección Visual Integrada NOM-047 (InspeccionVisualCard.vue)
// -----------------------------------------------------------------
async function probarCaso3(browser) {
  console.log("\n=======================================================");
  console.log("--- [CASO 3] CapturaView con InspeccionVisualCard (NOM-047) ---");
  console.log("=======================================================");

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 950 });

  const llamadasApi = [];
  await page.setRequestInterception(true);
  page.on("request", (req) => {
    const url = req.url();
    const method = req.method();

    if (!esRutaApi(url)) return req.continue();
    llamadasApi.push({ method, url });

    if (url.includes("/api/sync/estado")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ central: "CONECTADO", sincronizando: 0, pendientes: 0 }),
      });
    }

    if (url.includes("/api/estaciones/login")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "sess-cap-01",
          user_id: "u-101",
          workstation_id: "ws-cap-01",
          must_change_password: false,
          can_supervise: false,
        }),
      });
    }

    if (url.includes("/api/estaciones/")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "ws-cap-01",
          name: "ESTACION-CAPTURA-L1",
          station_type: "captura",
          center_id: "reforma",
          line_id: 1,
          allowed_line_ids: [1],
        }),
      });
    }

    if (url.includes("/api/inspeccion/checklist")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(CHECKLIST_NOM047),
      });
    }

    if (url.includes("/api/inspeccion/") && method === "POST") {
      const postData = JSON.parse(req.postData() || "{}");
      const tieneMalo = Object.values(postData.checklist || {}).includes("MALO");
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "insp-01",
          verificacion_id: "exp-01",
          resultado: tieneMalo ? "RECHAZADA" : "APROBADA",
          observaciones: postData.observaciones || null,
        }),
      });
    }

    if (url.includes("/api/catalogos/municipios")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    }

    if (url.includes("/api/siox/consultas/")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    }

    if (url.includes("/api/expedientes/exp-01")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(EXPEDIENTE_MOCK),
      });
    }

    if (url.includes("/api/expedientes")) {
      return req.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([EXPEDIENTE_MOCK]),
      });
    }

    return req.respond({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.goto("http://localhost:5173/?estacion=CAPTURA-L1", { waitUntil: "networkidle0" });

  await page.waitForSelector("input[type=password]");
  await page.evaluate(() => {
    const textInput = document.querySelector("input:not([type=password])");
    const passInput = document.querySelector("input[type=password]");
    if (textInput) {
      textInput.value = "operador.captura";
      textInput.dispatchEvent(new Event("input", { bubbles: true }));
    }
    if (passInput) {
      passInput.value = "Captura2026!";
      passInput.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });

  const btnEntrar = await page.waitForSelector("button.v-btn--size-large");
  await btnEntrar.click();

  // Esperar a que la SPA navegue a /captura
  await page.waitForFunction(() => window.location.pathname === "/captura");

  // Esperar a que cargue CapturaView con la lista de expedientes
  await page.waitForFunction(() => {
    return document.body.innerText.includes("Expedientes en curso en esta línea") && document.body.innerText.includes("TLX-789-A");
  });
  console.log("✓ Vista CapturaView montada con expedientes en curso.");

  // Abrir el expediente TLX-789-A
  await page.evaluate(() => {
    const items = Array.from(document.querySelectorAll(".v-list-item"));
    const expItem = items.find((i) => i.innerText.includes("TLX-789-A"));
    if (expItem) expItem.click();
  });

  // Esperar a que InspeccionVisualCard se monte
  await page.waitForFunction(() => {
    return document.body.innerText.includes("Inspección visual") && document.body.innerText.includes("Revisión visual de componentes");
  });
  console.log("✓ InspeccionVisualCard montada para expediente TLX-789-A.");

  // Verificar presencia de los 8 puntos normativos NOM-047
  const textoPagina = await page.evaluate(() => document.body.innerText);
  for (const item of CHECKLIST_NOM047) {
    if (!textoPagina.includes(item.etiqueta)) {
      throw new Error(`Falta el punto normativo de inspección: ${item.etiqueta}`);
    }
  }
  console.log("✓ Los 8 puntos normativos NOM-047 están presentes en la tarjeta.");

  // Verificar que el botón Registrar inspección esté deshabilitado inicialmente
  const btnRegistrarInspDisabled = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll("button"));
    const b = btns.find((x) => x.innerText.toLowerCase().includes("registrar inspección"));
    return b ? b.disabled : false;
  });
  if (!btnRegistrarInspDisabled) throw new Error("El botón 'Registrar inspección' debió iniciar deshabilitado.");
  console.log("✓ Botón 'Registrar inspección' inicia deshabilitado correctamente.");

  // Simular selección de todos los puntos en "Bueno"
  await page.evaluate(() => {
    const toggles = document.querySelectorAll(".v-btn-toggle");
    toggles.forEach((t) => {
      const btns = Array.from(t.querySelectorAll("button"));
      const btnBueno = btns.find((b) => b.innerText.trim().toLowerCase() === "bueno");
      if (btnBueno) btnBueno.click();
    });
  });

  await page.waitForFunction(() => document.body.innerText.includes("Resultado: Aprobada"));
  console.log("✓ Calificación completa en Bueno: Banner verde 'Resultado: Aprobada' visible.");

  // Verificar que el botón 'Registrar inspección' se habilite
  const btnRegistrarHabilitado = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll("button"));
    const b = btns.find((x) => x.innerText.toLowerCase().includes("registrar inspección"));
    return b ? !b.disabled : false;
  });
  if (!btnRegistrarHabilitado) throw new Error("El botón 'Registrar inspección' debería estar habilitado.");
  console.log("✓ Botón 'Registrar inspección' se habilitó con éxito.");

  // Probar alternancia a 'Malo' en un punto (Fugas en el sistema de escape)
  await page.evaluate(() => {
    const toggles = document.querySelectorAll(".v-btn-toggle");
    if (toggles[5]) {
      const btns = Array.from(toggles[5].querySelectorAll("button"));
      const btnMalo = btns.find((b) => b.innerText.trim().toLowerCase() === "malo");
      if (btnMalo) btnMalo.click();
    }
  });

  await page.waitForFunction(() => {
    return document.body.innerText.includes("Resultado: Rechazada") && document.body.innerText.includes("Fugas en el sistema de escape");
  });
  console.log("✓ Alternancia a Malo: Banner advertencia 'Resultado: Rechazada — Fugas en el sistema de escape' visible.");

  // Volver a poner todos en 'Bueno'
  await page.evaluate(() => {
    const toggles = document.querySelectorAll(".v-btn-toggle");
    if (toggles[5]) {
      const btns = Array.from(toggles[5].querySelectorAll("button"));
      const btnBueno = btns.find((b) => b.innerText.trim().toLowerCase() === "bueno");
      if (btnBueno) btnBueno.click();
    }
  });

  await page.waitForFunction(() => document.body.innerText.includes("Resultado: Aprobada"));

  const screenshotInspPath = path.join(ARTIFACTS_DIR, "evidencia_captura_inspeccion_visual.png");
  await page.screenshot({ path: screenshotInspPath, fullPage: false });
  console.log(`✓ Screenshot guardado: ${screenshotInspPath}`);

  // Hacer click en Registrar inspección
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll("button"));
    const b = btns.find((x) => x.innerText.toLowerCase().includes("registrar inspección"));
    if (b) b.click();
  });

  // Esperar aviso en CapturaView
  await page.waitForFunction(() =>
    document.body.innerText.includes("Inspección visual aprobada. El expediente pasa a la estación de Prueba."),
  );
  console.log("✓ Transición confirmada en CapturaView: 'Inspección visual aprobada. El expediente pasa a la estación de Prueba.'");

  const llamadaInsp = llamadasApi.find((c) => c.url.includes("/api/inspeccion/exp-01") && c.method === "POST");
  if (!llamadaInsp) throw new Error("No se realizó la llamada POST /api/inspeccion/exp-01");
  console.log("✓ Petición POST /api/inspeccion/exp-01 verificada con éxito.");

  await page.close();
}

async function main() {
  console.log("=== INICIANDO SUITE DE VALIDACIÓN E2E DE CARACTERÍSTICAS DE RENÉ ===");
  const ejecutable = buscarNavegador();
  console.log(`Usando navegador: ${ejecutable}`);

  const browser = await puppeteer.launch({
    executablePath: ejecutable,
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  try {
    await probarCaso1(browser);
    await probarCaso2(browser);
    await probarCaso3(browser);
    console.log("\n=======================================================");
    console.log(">>> TODAS LAS VALIDACIONES PASARON EXITOSAMENTE AL 100% <<<");
    console.log("=======================================================");
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error("\n❌ Error durante la validación:", err);
  process.exit(1);
});
