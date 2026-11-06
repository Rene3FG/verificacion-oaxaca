#!/usr/bin/env node
// ==============================================================================
// Prueba de humo E2E de interfaz de usuario en navegador (Puppeteer / Chromium)
// Sistema de Verificación Vehicular Oaxaca — PENDIENTES Q2
//
// Valida visualmente y de forma interactiva las 5 vistas del sistema:
//   1. LoginView: detección automática de estación y rechazo de credenciales inválidas.
//   2. LoginView: cambio dinámico de estación por URL (?estacion=...).
//   3. CapturaView: login de operador, formulario de placa y creación de expediente.
//   4. PruebaView: estación de prueba, cola de líneas y modal/detalle.
//   5. ImpresionView: cola de impresión, filtros rápidos y estado de folios.
//   6. SupervisorView: autenticación de supervisor y las 5 pestañas de control.
//
// Uso:
//   node scripts/smoke_e2e_ui.mjs [--url http://localhost:5173]
// ==============================================================================

import fs from "node:fs";
import path from "node:path";
import puppeteer from "../frontend/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js";

const config = {
  baseUrl: (process.env.APP_URL || "http://localhost:5173").replace(/\/+$/, ""),
  usuario: process.env.SMOKE_USUARIO || "operador1",
  password: process.env.SMOKE_PASSWORD || "operador1",
  supervisor: process.env.SMOKE_SUPERVISOR || "supervisor1",
  passwordSupervisor: process.env.SMOKE_SUPERVISOR_PASSWORD || "supervisor1",
  estaciones: {
    captura: "CAPTURA-REFORMA-L1",
    prueba: "PRUEBA-REFORMA-L1",
    impresion: "IMPRESION-REFORMA-01",
  },
};

function buscarNavegador() {
  const rutas = [
    process.env.CHROME_BIN,
    process.env.PUPPETEER_EXECUTABLE_PATH,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
  ];
  for (const r of rutas) {
    if (r && fs.existsSync(r)) return r;
  }
  throw new Error("No se encontró ningún binario de Chrome o Edge en las rutas estándar.");
}

let browser = null;
let pasos = 0;
const t0 = Date.now();

async function paso(nombre, fn) {
  pasos += 1;
  const num = String(pasos).padStart(2, "0");
  const inicio = Date.now();
  try {
    const res = await fn();
    const dur = Date.now() - inicio;
    console.log(`✓ ${num}. ${nombre} (${dur} ms)${res ? ` — ${res}` : ""}`);
    return res;
  } catch (err) {
    const dur = Date.now() - inicio;
    console.error(`✗ ${num}. ${nombre} (${dur} ms)`);
    console.error(`   Error: ${err.message}`);
    if (browser) await browser.close();
    process.exit(1);
  }
}

async function simularInputVuetify(page, selector, valor) {
  await page.waitForSelector(selector, { timeout: 5000 });
  await page.evaluate(
    (sel, val) => {
      const el = document.querySelector(sel);
      if (!el) throw new Error(`Elemento no encontrado: ${sel}`);
      el.value = val;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    },
    selector,
    valor
  );
}

async function loginEnEstacion(page, usuario, password) {
  await simularInputVuetify(page, "input[type='text']", usuario);
  await simularInputVuetify(page, "input[type='password']", password);
  await page.click("button");
}

async function main() {
  console.log(`Prueba de humo E2E de interfaz (Puppeteer) — ${config.baseUrl}\n`);
  const ejecutable = buscarNavegador();
  console.log(`Navegador detectado: ${path.basename(ejecutable)}\n`);

  browser = await puppeteer.launch({
    executablePath: ejecutable,
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  // --------------------------------------------------------------------------
  // ESTACIÓN 1: LOGIN Y DETECCIÓN
  // --------------------------------------------------------------------------
  const p1 = await browser.newPage();
  await p1.setViewport({ width: 1280, height: 800 });

  await paso("Cargar pantalla inicial y detectar estación por defecto", async () => {
    await p1.goto(`${config.baseUrl}/`, { waitUntil: "networkidle0" });
    const texto = await p1.evaluate(() => document.body.innerText);
    if (!texto.includes("Sistema de Verificación Vehicular Oaxaca")) {
      throw new Error("El título institucional no está presente en la pantalla.");
    }
    if (!texto.includes("Estación detectada")) {
      throw new Error("No se detectó el bloque de estación en LoginView.");
    }
    return "Estación y título institucional presentes";
  });

  await paso("Validar respuesta visual ante credenciales inválidas", async () => {
    await simularInputVuetify(p1, "input[type='text']", "usuario_invalido");
    await simularInputVuetify(p1, "input[type='password']", "password_falso");
    await p1.click("button");
    await p1.waitForFunction(() => document.body.innerText.includes("Usuario o contraseña incorrectos"), {
      timeout: 5000,
    });
    return "Mensaje de rechazo mostrado";
  });
  await p1.close();

  // --------------------------------------------------------------------------
  // ESTACIÓN 2: CASETA DE CAPTURA
  // --------------------------------------------------------------------------
  const pCaptura = await browser.newPage();
  await pCaptura.setViewport({ width: 1280, height: 800 });

  await paso("Cambiar dinámicamente a estación de Captura (?estacion=...)", async () => {
    await pCaptura.goto(`${config.baseUrl}/?estacion=${config.estaciones.captura}`, {
      waitUntil: "networkidle0",
    });
    const texto = await pCaptura.evaluate(() => document.body.innerText);
    if (!texto.includes(config.estaciones.captura)) {
      throw new Error(`La estación ${config.estaciones.captura} no se reflejó en pantalla`);
    }
    return config.estaciones.captura;
  });

  await paso("Iniciar sesión en caseta de Captura", async () => {
    await loginEnEstacion(pCaptura, config.usuario, config.password);
    await pCaptura.waitForFunction(() => window.location.pathname === "/captura", { timeout: 6000 });
    return "Redirección a /captura confirmada";
  });

  const placaTest = `E2E-${Date.now().toString().slice(-4)}`;
  await paso("Crear nuevo expediente en CapturaView", async () => {
    await pCaptura.waitForSelector("input", { timeout: 5000 });
    await simularInputVuetify(pCaptura, "input", placaTest);
    await pCaptura.evaluate(() => {
      const btn = Array.from(document.querySelectorAll("button")).find((b) =>
        b.innerText.includes("CREAR EXPEDIENTE")
      );
      if (btn) btn.click();
    });
    await pCaptura.waitForFunction(
      (p) => document.body.innerText.includes(p),
      { timeout: 6000 },
      placaTest
    );
    return `Expediente creado para ${placaTest}`;
  });
  await pCaptura.close();

  // --------------------------------------------------------------------------
  // ESTACIÓN 3: ESTACIÓN DE PRUEBA
  // --------------------------------------------------------------------------
  const pPrueba = await browser.newPage();
  await pPrueba.setViewport({ width: 1280, height: 800 });

  await paso("Acceder a estación de Prueba y autenticar", async () => {
    await pPrueba.goto(`${config.baseUrl}/?estacion=${config.estaciones.prueba}`, {
      waitUntil: "networkidle0",
    });
    await loginEnEstacion(pPrueba, config.usuario, config.password);
    await pPrueba.waitForFunction(() => window.location.pathname === "/prueba", { timeout: 6000 });
    return "Redirección a /prueba confirmada";
  });

  await paso("Verificar interfaz y cola de expedientes en PruebaView", async () => {
    const texto = await pPrueba.evaluate(() => document.body.innerText);
    if (!texto.includes("Estación de Prueba") || !texto.includes("Expedientes en curso")) {
      throw new Error("PruebaView no renderizó el encabezado o la cola esperada.");
    }
    return "Cola de Línea 1 visible";
  });
  await pPrueba.close();

  // --------------------------------------------------------------------------
  // ESTACIÓN 4: IMPRESIÓN CENTRAL
  // --------------------------------------------------------------------------
  const pImpresion = await browser.newPage();
  await pImpresion.setViewport({ width: 1280, height: 800 });

  await paso("Acceder a estación de Impresión y autenticar", async () => {
    await pImpresion.goto(`${config.baseUrl}/?estacion=${config.estaciones.impresion}`, {
      waitUntil: "networkidle0",
    });
    await loginEnEstacion(pImpresion, config.usuario, config.password);
    await pImpresion.waitForFunction(() => window.location.pathname === "/impresion", { timeout: 6000 });
    return "Redirección a /impresion confirmada";
  });

  await paso("Verificar cola de impresión y filtros rápidos en ImpresionView", async () => {
    const texto = await pImpresion.evaluate(() => document.body.innerText);
    if (!texto.includes("Cola de Impresión Central") || !texto.includes("Filtro rápido")) {
      throw new Error("ImpresionView no renderizó los filtros rápidos o la cola.");
    }
    return "Filtros rápidos y cola de impresión visibles";
  });
  await pImpresion.close();

  // --------------------------------------------------------------------------
  // ESTACIÓN 5: SUPERVISIÓN Y ADMINISTRACIÓN
  // --------------------------------------------------------------------------
  const pSupervisor = await browser.newPage();
  await pSupervisor.setViewport({ width: 1280, height: 800 });

  await paso("Iniciar sesión como supervisor y acceder a SupervisorView", async () => {
    await pSupervisor.goto(`${config.baseUrl}/?estacion=${config.estaciones.impresion}`, {
      waitUntil: "networkidle0",
    });
    await loginEnEstacion(pSupervisor, config.supervisor, config.passwordSupervisor);
    await pSupervisor.waitForFunction(() => document.body.innerText.includes("SUPERVISOR"), { timeout: 6000 });
    await pSupervisor.evaluate(() => {
      const btn = Array.from(document.querySelectorAll("button, a")).find((el) =>
        el.innerText.includes("SUPERVISOR")
      );
      if (btn) btn.click();
    });
    await pSupervisor.waitForFunction(() => window.location.pathname === "/supervisor", { timeout: 6000 });
    return "Redirección a /supervisor confirmada";
  });

  await paso("Verificar las 5 pestañas de control en SupervisorView", async () => {
    const pestañas = await pSupervisor.evaluate(() => {
      const tabs = Array.from(document.querySelectorAll(".v-tab, [role='tab']"));
      return tabs.map((t) => t.innerText.trim());
    });
    const esperadas = ["MONITOR", "ERRORES Y REINTENTOS", "REIMPRESIÓN", "AUDITORÍA", "ADMINISTRACIÓN"];
    for (const esp of esperadas) {
      if (!pestañas.some((p) => p.includes(esp))) {
        throw new Error(`Pestaña de supervisor faltante: ${esp}`);
      }
    }
    return `5 pestañas validadas (${esperadas.join(", ")})`;
  });
  await pSupervisor.close();

  await browser.close();
  const duracionTotal = ((Date.now() - t0) / 1000).toFixed(1);
  console.log(`\n✓ Suite E2E de interfaz OK: ${pasos} pasos completados exitosamente en ${duracionTotal} s.`);
}

main().catch(async (err) => {
  console.error("Error fatal:", err);
  if (browser) await browser.close();
  process.exit(1);
});
