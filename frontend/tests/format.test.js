import { describe, expect, it } from "vitest";
import { formatearFecha } from "../src/utils/format";
import { esOaxaca, limpiarPayload } from "../src/utils/catalogos";

describe("format.js - formatearFecha", () => {
  it("devuelve null si se proporciona un valor nulo, indefinido o vacío", () => {
    expect(formatearFecha(null)).toBeNull();
    expect(formatearFecha(undefined)).toBeNull();
    expect(formatearFecha("")).toBeNull();
  });

  it("formatea correctamente una fecha ISO a la configuración regional es-MX", () => {
    const iso = "2026-10-21T15:30:00Z";
    const resultado = formatearFecha(iso);
    expect(resultado).toBeTruthy();
    // En es-MX debe contener día/mes/año o dígitos con separadores
    expect(resultado).toMatch(/\d{1,2}\/\d{1,2}\/\d{2,4}/);
  });
});

describe("catalogos.js - utilerías síncronas", () => {
  describe("esOaxaca", () => {
    it("reconoce valores vacíos o nulos como pertenecientes por defecto a Oaxaca", () => {
      expect(esOaxaca(null)).toBe(true);
      expect(esOaxaca(undefined)).toBe(true);
      expect(esOaxaca("")).toBe(true);
      expect(esOaxaca("   ")).toBe(true);
    });

    it("reconoce variaciones de texto de OAXACA y clave 20", () => {
      expect(esOaxaca("Oaxaca")).toBe(true);
      expect(esOaxaca("OAXACA")).toBe(true);
      expect(esOaxaca("  oaxaca  ")).toBe(true);
      expect(esOaxaca("20")).toBe(true);
    });

    it("rechaza estados diferentes a Oaxaca", () => {
      expect(esOaxaca("Puebla")).toBe(false);
      expect(esOaxaca("CDMX")).toBe(false);
      expect(esOaxaca("Veracruz")).toBe(false);
      expect(esOaxaca("15")).toBe(false);
    });
  });

  describe("limpiarPayload", () => {
    it("convierte cadenas vacías a null para campos numéricos y texto", () => {
      const entrada = {
        placa: "ABC1234",
        modelo: "",
        cilindros: "",
        kilometraje: 45000,
        combustible: "GASOLINA",
        observaciones: "",
      };

      const esperado = {
        placa: "ABC1234",
        modelo: null,
        cilindros: null,
        kilometraje: 45000,
        combustible: "GASOLINA",
        observaciones: null,
      };

      expect(limpiarPayload(entrada)).toEqual(esperado);
    });

    it("conserva valores cero, booleanos y nulos existentes", () => {
      const entrada = {
        reintentos: 0,
        aprobado: false,
        folio: null,
      };

      expect(limpiarPayload(entrada)).toEqual(entrada);
    });
  });
});
