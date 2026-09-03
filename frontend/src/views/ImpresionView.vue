<script setup>
import { computed, onMounted, ref } from "vue";
import { api } from "../api/client";
import ExpedienteHeader from "../components/ExpedienteHeader.vue";
import { useSessionStore } from "../stores/session";
import { formatearFecha } from "../utils/format";

const session = useSessionStore();

// PENDIENTE_DE_IMPRESION_RECHAZO: cola propia de rechazo que agregó René
// (backend etapa1-y-siox) — mismo tratamiento que PENDIENTE_IMPRESION para
// esta vista, la diferencia solo importa del lado del backend.
const ESTADOS_SOLICITABLES = [
  "PENDIENTE_IMPRESION",
  "PENDIENTE_DE_IMPRESION_RECHAZO",
  "FOLIO_ERROR",
];
const ESTADOS_IMPRIMIBLES = ["FOLIO_ASIGNADO", "IMPRESION_FALLIDA"];

// Tipos reales de certificado para un resultado APROBADO (RECHAZADO se
// infiere solo — RECHAZO es el único tipo posible ahí, ver
// backend/app/api/routers/impresion.py: calcular_tipo_certificado).
const TIPOS_CERTIFICADO_APROBADO = ["PARTICULAR", "DOBLE_CERO", "INTENSIVO"];

const expedientes = ref([]);
const cargandoLista = ref(false);
const error = ref(null);
const aviso = ref(null);

const expediente = ref(null);
const cargandoExpediente = ref(false);

const calculandoTipo = ref(false);
const solicitandoFolio = ref(false);
const cargandoVistaPrevia = ref(false);
const imprimiendo = ref(false);
const cerrando = ref(false);
const marcandoDanado = ref(false);

const tipoCertificadoSeleccionado = ref(null);

const requiereSeleccionManual = computed(
  () => expediente.value?.resultado_final === "APROBADO"
);

// Concatenan solo las partes presentes (los campos de propietario son
// opcionales a nivel de esquema, ver comentario en el template) sin dejar
// separadores sueltos cuando falta alguna.
const domicilioCompleto = computed(() => {
  const v = expediente.value?.vehiculo;
  if (!v) return "—";
  const calleNumero = [v.propietario_calle, v.propietario_numero_exterior]
    .filter(Boolean)
    .join(" ");
  const partes = [calleNumero, v.propietario_colonia].filter(Boolean);
  return partes.length ? partes.join(", ") : "—";
});
const municipioEstado = computed(() => {
  const v = expediente.value?.vehiculo;
  if (!v) return "—";
  const partes = [v.propietario_municipio, v.propietario_estado].filter(Boolean);
  return partes.length ? partes.join(", ") : "—";
});

// Sección 7 del handoff: estos campos del vehículo son obligatorios para
// imprimir (el backend responde 409 con el detalle si faltan) — aquí solo
// se anticipa la advertencia; la validación real es del servidor.
const CAMPOS_CERTIFICADO_OBLIGATORIOS = [
  "tarjeta_circulacion",
  "propietario_estado",
  "propietario_municipio",
  "propietario_codigo_postal",
  "propietario_colonia",
  "propietario_calle",
  "propietario_numero_exterior",
  "pbv",
  "traccion",
];
const faltanDatosCertificado = computed(() => {
  const v = expediente.value?.vehiculo;
  if (!v) return false;
  return CAMPOS_CERTIFICADO_OBLIGATORIOS.some((campo) => !v[campo]);
});

const puedeCalcularTipo = computed(
  () =>
    expediente.value && ESTADOS_SOLICITABLES.includes(expediente.value.estado)
);
const puedeSolicitarFolio = computed(
  () =>
    expediente.value &&
    !expediente.value.folio_externo &&
    ESTADOS_SOLICITABLES.includes(expediente.value.estado)
);
const puedeImprimir = computed(
  () =>
    expediente.value &&
    expediente.value.folio_externo &&
    ESTADOS_IMPRIMIBLES.includes(expediente.value.estado)
);
const puedeCerrar = computed(
  () =>
    expediente.value &&
    expediente.value.estado === "IMPRESO" &&
    !expediente.value.cerrado_at
);
// Sección 3 del handoff: folio dañado ANTES de imprimir — solo aplica con
// un folio ya asignado y sin haber impreso todavía (no cuenta como
// reimpresión). Después de imprimir es otra operación, exclusiva de
// Supervisor (ver pestaña "Reimpresión" en SupervisorView.vue).
const puedeMarcarDanado = computed(() => expediente.value?.estado === "FOLIO_ASIGNADO");

async function cargarCola() {
  cargandoLista.value = true;
  error.value = null;
  try {
    const { data } = await api.get("/impresion/cola");
    expedientes.value = data;
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cargar la cola de impresión.";
  } finally {
    cargandoLista.value = false;
  }
}

function abrirExpediente(exp) {
  error.value = null;
  aviso.value = null;
  expediente.value = exp;
}

function cerrarDetalle() {
  expediente.value = null;
  aviso.value = null;
  cargarCola();
}

async function calcularTipoCertificado() {
  if (requiereSeleccionManual.value && !tipoCertificadoSeleccionado.value) {
    error.value = "Selecciona el tipo de certificado (Particular/Doble Cero/Intensivo).";
    return;
  }
  calculandoTipo.value = true;
  error.value = null;
  try {
    // Un expediente APROBADO no tiene un único tipo posible (Particular/
    // Doble Cero/Intensivo) — el backend exige `tipo_certificado` para ese
    // caso (422 si se omite, ver calcular_tipo_certificado). RECHAZADO
    // sigue infiriéndose solo, sin parámetro.
    const params = requiereSeleccionManual.value
      ? { tipo_certificado: tipoCertificadoSeleccionado.value }
      : {};
    const { data } = await api.post(
      `/impresion/tipo-certificado/${expediente.value.id}`,
      null,
      { params }
    );
    expediente.value.certificado_tipo = data.certificado_tipo;
    aviso.value = `Tipo de certificado: ${data.certificado_tipo}`;
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo determinar el tipo de certificado.";
  } finally {
    calculandoTipo.value = false;
  }
}

async function solicitarFolio() {
  if (!expediente.value.certificado_tipo) {
    error.value = "Calcula el tipo de certificado antes de solicitar el folio.";
    return;
  }
  solicitandoFolio.value = true;
  error.value = null;
  try {
    // El backend ya no es un sistema externo simulado (René, inventario
    // local de folios): en éxito siempre devuelve un folio real; si el
    // inventario de ese tipo está agotado, tira 409 con motivo — lo
    // maneja el catch de abajo, no hay rama de "folio nulo" que revisar.
    const { data } = await api.post(
      `/folios/solicitar/${expediente.value.id}`,
      null,
      { params: { tipo_certificado: expediente.value.certificado_tipo } }
    );
    expediente.value.estado = data.estado_expediente;
    expediente.value.folio_externo = data.folio;
    // El endpoint no devuelve folio_asignado_at (solo folio/estado_expediente);
    // el backend lo fija a "ahora" al momento de asignar, así que lo
    // aproximamos aquí mismo para no tener que recargar el expediente
    // solo para ver el timestamp.
    expediente.value.folio_asignado_at = new Date().toISOString();
    aviso.value = `Folio asignado: ${data.folio}`;
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo solicitar el folio.";
  } finally {
    solicitandoFolio.value = false;
  }
}

async function verVistaPrevia() {
  cargandoVistaPrevia.value = true;
  error.value = null;
  try {
    const { data } = await api.get(`/impresion/vista-previa/${expediente.value.id}`, {
      responseType: "blob",
    });
    const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
    window.open(url, "_blank");
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo generar la vista previa.";
  } finally {
    cargandoVistaPrevia.value = false;
  }
}

async function imprimir() {
  imprimiendo.value = true;
  error.value = null;
  try {
    const { data } = await api.post(`/impresion/imprimir/${expediente.value.id}`);
    expediente.value.estado = data.estado_expediente;
    if (data.estado_expediente === "IMPRESO") {
      aviso.value = "Certificado impreso correctamente.";
    } else {
      error.value = `La impresora no respondió. Intento número ${data.intentos}.`;
    }
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo imprimir el certificado.";
  } finally {
    imprimiendo.value = false;
  }
}

async function recargarExpediente() {
  try {
    const { data } = await api.get(`/expedientes/${expediente.value.id}`);
    expediente.value = data;
  } catch {
    // Si falla el refresco se deja el estado local tal cual — no es un
    // error nuevo que reportar, la operación que lo disparó ya reportó
    // el suyo si falló.
  }
}

async function marcarFolioDanado() {
  marcandoDanado.value = true;
  error.value = null;
  try {
    const { data } = await api.post(`/impresion/folio/marcar-danado/${expediente.value.id}`);
    aviso.value = `Folio ${data.folio_danado} marcado como dañado. Nuevo folio: ${data.folio_externo}.`;
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo marcar el folio dañado.";
  } finally {
    marcandoDanado.value = false;
    // Refresca siempre: si el inventario del tipo se agotó, el backend ya
    // transicionó el expediente a FOLIO_ERROR antes de devolver el 409.
    await recargarExpediente();
  }
}

async function cerrarExpediente() {
  cerrando.value = true;
  error.value = null;
  try {
    const { data } = await api.post(`/impresion/cerrar/${expediente.value.id}`);
    expediente.value.estado = data.estado_expediente;
    // Igual que folio_asignado_at: el endpoint no devuelve cerrado_at, se
    // aproxima aquí para mostrarlo en el brevísimo momento antes de volver
    // a la cola (ver setTimeout abajo).
    expediente.value.cerrado_at = new Date().toISOString();
    aviso.value = "Expediente cerrado.";
    setTimeout(cerrarDetalle, 1200);
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cerrar el expediente.";
  } finally {
    cerrando.value = false;
  }
}

onMounted(cargarCola);
</script>

<template>
  <v-container>
    <template v-if="!expediente">
      <p class="mb-4">
        Impresión Central · Centro {{ session.estacion?.center_id }} · Líneas
        {{ session.estacion?.allowed_line_ids }}
      </p>

      <v-alert v-if="error" type="error" class="mb-4" closable @click:close="error = null">
        {{ error }}
      </v-alert>

      <v-progress-circular v-if="cargandoLista" indeterminate class="mb-4" />
      <template v-else>
        <p v-if="expedientes.length === 0" class="text-medium-emphasis">
          No hay expedientes pendientes de impresión en las líneas de este centro.
        </p>
        <ExpedienteHeader
          v-for="exp in expedientes"
          :key="exp.id"
          :expediente="exp"
          style="cursor: pointer"
          @click="abrirExpediente(exp)"
        />
      </template>
    </template>

    <template v-else>
      <v-btn variant="text" prepend-icon="mdi-arrow-left" class="mb-2" @click="cerrarDetalle">
        Volver a la cola
      </v-btn>

      <ExpedienteHeader :expediente="expediente" class="mb-4" />

      <v-alert v-if="error" type="error" class="mb-4" closable @click:close="error = null">
        {{ error }}
      </v-alert>
      <v-alert v-if="aviso" type="success" class="mb-4" closable @click:close="aviso = null">
        {{ aviso }}
      </v-alert>

      <v-row>
        <v-col cols="12" md="6">
          <!-- "Expediente completo" según Figma: Resultado, Tipo de
          certificado, Placa, NIV/Serie, Modelo, Combustible, Propietario,
          Línea origen, domicilio, municipio/estado, código postal, tarjeta
          de circulación, PBV y tracción — mismo orden que el diseño.
          Domicilio/tarjeta de circulación/PBV/tracción (pendiente #5 que
          René levantó tras revisar el Figma) ya existen en el backend desde
          su actualización del 2026-08-29 (`vehiculo.tarjeta_circulacion`,
          `.propietario_*`, `.pbv`, `.traccion`) — se muestran igual que el
          resto de los campos ahora. "Propietario" en el diseño es el
          nombre del dueño; lo único que tenemos en el backend es razón
          social (`vehiculo.razon_social`), que es lo que se muestra. Estos
          campos son opcionales a nivel de esquema (el backend los exige
          recién al imprimir, ver 409 "Faltan datos obligatorios del
          certificado" en `calcularTipoCertificado`/`imprimir`), así que
          pueden venir vacíos si Captura todavía no los llenó. -->
          <v-card class="mb-4" variant="outlined">
            <v-card-title>Expediente completo</v-card-title>
            <v-card-subtitle class="text-wrap">
              Resultado y placas visibles para selección manual del tipo de certificado
            </v-card-subtitle>
            <v-card-text>
              <v-row dense>
                <v-col cols="6">
                  <span class="text-caption text-medium-emphasis d-block">Resultado</span>
                  <span>{{ expediente.resultado_final ?? "—" }}</span>
                </v-col>
                <v-col cols="6">
                  <span class="text-caption text-medium-emphasis d-block">Tipo de certificado</span>
                  <span>{{ expediente.certificado_tipo ?? "sin determinar" }}</span>
                </v-col>
                <v-col cols="6">
                  <span class="text-caption text-medium-emphasis d-block">Placa</span>
                  <span>{{ expediente.placa }}</span>
                </v-col>
                <v-col cols="6">
                  <span class="text-caption text-medium-emphasis d-block">NIV / Serie</span>
                  <span>{{ expediente.vehiculo?.niv ?? "—" }}</span>
                </v-col>
                <v-col cols="6">
                  <span class="text-caption text-medium-emphasis d-block">Modelo</span>
                  <span>
                    {{ expediente.vehiculo?.marca ?? "—" }}
                    {{ expediente.vehiculo?.linea ?? "" }}
                    <template v-if="expediente.vehiculo?.modelo">
                      ({{ expediente.vehiculo.modelo }})
                    </template>
                  </span>
                </v-col>
                <v-col cols="6">
                  <span class="text-caption text-medium-emphasis d-block">Combustible</span>
                  <span>{{ expediente.combustible_validado ?? "—" }}</span>
                </v-col>
                <v-col cols="6">
                  <span class="text-caption text-medium-emphasis d-block">Propietario</span>
                  <span>{{ expediente.vehiculo?.razon_social ?? "—" }}</span>
                </v-col>
                <v-col cols="6">
                  <span class="text-caption text-medium-emphasis d-block">Línea origen</span>
                  <span>{{ expediente.centro_id }} · Línea {{ expediente.linea_id }}</span>
                </v-col>
                <v-col cols="6">
                  <span class="text-caption text-medium-emphasis d-block">Tarjeta de circulación</span>
                  <span>{{ expediente.vehiculo?.tarjeta_circulacion ?? "—" }}</span>
                </v-col>
                <v-col cols="6">
                  <span class="text-caption text-medium-emphasis d-block">PBV / Tracción</span>
                  <span>
                    {{ expediente.vehiculo?.pbv ?? "—" }}
                    <template v-if="expediente.vehiculo?.traccion">
                      · {{ expediente.vehiculo.traccion }}
                    </template>
                  </span>
                </v-col>
                <v-col cols="12">
                  <span class="text-caption text-medium-emphasis d-block">Domicilio</span>
                  <span>{{ domicilioCompleto }}</span>
                </v-col>
                <v-col cols="8">
                  <span class="text-caption text-medium-emphasis d-block">Municipio / Estado</span>
                  <span>{{ municipioEstado }}</span>
                </v-col>
                <v-col cols="4">
                  <span class="text-caption text-medium-emphasis d-block">Código postal</span>
                  <span>{{ expediente.vehiculo?.propietario_codigo_postal ?? "—" }}</span>
                </v-col>
                <v-col v-if="expediente.hora_salida" cols="6">
                  <span class="text-caption text-medium-emphasis d-block">Hora salida</span>
                  <span>{{ formatearFecha(expediente.hora_salida) }}</span>
                </v-col>
              </v-row>
              <v-alert
                v-if="faltanDatosCertificado"
                type="warning"
                density="compact"
                variant="tonal"
                class="mt-3"
              >
                Faltan datos obligatorios del certificado (domicilio, tarjeta de
                circulación, PBV o tracción) — la impresión será rechazada hasta
                que Captura o Prueba los complete.
              </v-alert>
            </v-card-text>
          </v-card>

          <v-card class="mb-4" variant="outlined">
            <v-card-title>Certificado</v-card-title>
            <v-card-text>
              <!-- Solo APROBADO requiere selección manual (Particular/Doble
              Cero/Intensivo) — RECHAZADO se infiere solo (RECHAZO es el
              único tipo posible ahí), ver calcularTipoCertificado(). -->
              <v-select
                v-if="requiereSeleccionManual"
                v-model="tipoCertificadoSeleccionado"
                :items="TIPOS_CERTIFICADO_APROBADO"
                label="Tipo de certificado"
                :disabled="!!expediente.certificado_tipo"
                class="mb-3"
                density="compact"
              />
              <v-btn
                variant="outlined"
                :disabled="!puedeCalcularTipo"
                :loading="calculandoTipo"
                @click="calcularTipoCertificado"
              >
                Calcular tipo de certificado
              </v-btn>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" md="6">
          <!-- "Folio certificado" según Figma. El diseño también muestra
          "Fuente", "Solicitud enviada", "Siguiente folio" y "Orden de
          lista" — esos no vienen en la respuesta de
          POST /folios/solicitar (solo folio/estado_expediente, ver
          backend/app/api/routers/folios.py) ni en ExpedienteCompleto, así
          que no se fabrican aquí; solo se muestra lo que sí es real. -->
          <v-card class="mb-4" variant="outlined">
            <v-card-title>Folio certificado</v-card-title>
            <v-card-text>
              <p class="mb-1">Folio: {{ expediente.folio_externo ?? "sin asignar" }}</p>
              <p v-if="expediente.folio_asignado_at" class="text-caption text-medium-emphasis mb-2">
                Asignado el {{ formatearFecha(expediente.folio_asignado_at) }}
              </p>
              <p v-else-if="solicitandoFolio" class="text-caption text-medium-emphasis mb-2">
                Asignando siguiente folio disponible…
              </p>
              <p v-else-if="expediente.estado === 'FOLIO_ERROR'" class="text-caption text-medium-emphasis mb-2">
                Sin folio disponible — el inventario local de este tipo de certificado se agotó.
              </p>
              <v-btn
                color="primary"
                :disabled="!puedeSolicitarFolio"
                :loading="solicitandoFolio"
                @click="solicitarFolio"
              >
                {{ expediente.estado === "FOLIO_ERROR" ? "Reintentar" : "Solicitar folio" }}
              </v-btn>
              <v-btn
                v-if="puedeMarcarDanado"
                variant="text"
                color="warning"
                class="ml-2"
                :loading="marcandoDanado"
                @click="marcarFolioDanado"
              >
                Marcar folio dañado
              </v-btn>
            </v-card-text>
          </v-card>

          <v-card class="mb-4" variant="outlined">
            <v-card-title>Vista previa</v-card-title>
            <v-card-subtitle class="text-wrap">Certificado y resultados</v-card-subtitle>
            <v-card-text>
              <p v-if="!expediente.certificado_tipo" class="text-caption text-medium-emphasis mb-2">
                Calcula el tipo de certificado para poder generar la vista previa.
              </p>
              <v-btn
                variant="outlined"
                :disabled="!expediente.certificado_tipo"
                :loading="cargandoVistaPrevia"
                @click="verVistaPrevia"
              >
                Generar vista previa
              </v-btn>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <v-card class="mb-4" variant="outlined">
        <v-card-title>Impresión</v-card-title>
        <v-card-text>
          <v-btn
            color="primary"
            :disabled="!puedeImprimir"
            :loading="imprimiendo"
            @click="imprimir"
          >
            {{ expediente.estado === "IMPRESION_FALLIDA" ? "Reintentar impresión" : "Imprimir" }}
          </v-btn>
        </v-card-text>
      </v-card>

      <v-card variant="outlined">
        <v-card-title>Cierre</v-card-title>
        <v-card-text>
          <p v-if="expediente.cerrado_at" class="text-caption text-medium-emphasis mb-2">
            Cerrado el {{ formatearFecha(expediente.cerrado_at) }}
          </p>
          <v-btn
            color="success"
            :disabled="!puedeCerrar"
            :loading="cerrando"
            @click="cerrarExpediente"
          >
            Cerrar expediente
          </v-btn>
        </v-card-text>
      </v-card>
    </template>
  </v-container>
</template>