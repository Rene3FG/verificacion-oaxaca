<script setup>
import { computed, onMounted, ref } from "vue";
import { api } from "../api/client";
import ExpedienteHeader from "../components/ExpedienteHeader.vue";
import { useSessionStore } from "../stores/session";

const session = useSessionStore();

const ESTADOS_SOLICITABLES = ["PENDIENTE_IMPRESION", "FOLIO_ERROR"];
const ESTADOS_IMPRIMIBLES = ["FOLIO_ASIGNADO", "IMPRESION_FALLIDA"];

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

function formatearFecha(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleString("es-MX", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

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
  calculandoTipo.value = true;
  error.value = null;
  try {
    const { data } = await api.post(`/impresion/tipo-certificado/${expediente.value.id}`);
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
    const { data } = await api.post(
      `/folios/solicitar/${expediente.value.id}`,
      null,
      { params: { tipo_certificado: expediente.value.certificado_tipo } }
    );
    expediente.value.estado = data.estado_expediente;
    if (data.folio) {
      expediente.value.folio_externo = data.folio;
      // El endpoint no devuelve folio_asignado_at (solo folio/status/estado);
      // el backend lo fija a "ahora" al momento de asignar, así que lo
      // aproximamos aquí mismo para no tener que recargar el expediente
      // solo para ver el timestamp.
      expediente.value.folio_asignado_at = new Date().toISOString();
      aviso.value = `Folio asignado: ${data.folio}`;
    } else {
      error.value = "El sistema externo de folios no respondió. El expediente quedó en FOLIO_ERROR.";
    }
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

      <v-card class="mb-4" variant="outlined">
        <v-card-title>Datos del expediente</v-card-title>
        <v-card-text>
          <v-row dense>
            <v-col cols="12" sm="6" md="4">
              <span class="text-caption text-medium-emphasis d-block">NIV</span>
              <span>{{ expediente.vehiculo?.niv ?? "—" }}</span>
            </v-col>
            <v-col cols="12" sm="6" md="4">
              <span class="text-caption text-medium-emphasis d-block">Marca / Línea</span>
              <span>
                {{ expediente.vehiculo?.marca ?? "—" }}
                {{ expediente.vehiculo?.linea ?? "" }}
              </span>
            </v-col>
            <v-col cols="12" sm="6" md="4">
              <span class="text-caption text-medium-emphasis d-block">Tipo de vehículo</span>
              <span>{{ expediente.vehiculo?.tipo_vehiculo ?? "—" }}</span>
            </v-col>
            <v-col cols="12" sm="6" md="4">
              <span class="text-caption text-medium-emphasis d-block">Razón social</span>
              <span>{{ expediente.vehiculo?.razon_social ?? "—" }}</span>
            </v-col>
            <v-col cols="12" sm="6" md="4">
              <span class="text-caption text-medium-emphasis d-block">Centro / Línea de origen</span>
              <span>{{ expediente.centro_id }} · Línea {{ expediente.linea_id }}</span>
            </v-col>
            <v-col cols="12" sm="6" md="4">
              <span class="text-caption text-medium-emphasis d-block">Resultado final</span>
              <span>{{ expediente.resultado_final ?? "—" }}</span>
            </v-col>
          </v-row>
          <p class="text-caption text-medium-emphasis mt-3 mb-0">
            El diseño (Figma) también pide domicilio, municipio, tarjeta de
            circulación, peso bruto vehicular y tracción — esos campos no
            existen todavía en el backend (pendiente #5 que René levantó tras
            revisar el Figma), así que no se muestran aquí hasta que se
            capturen en algún punto anterior del flujo.
          </p>
        </v-card-text>
      </v-card>

      <v-card class="mb-4" variant="outlined">
        <v-card-title>Certificado</v-card-title>
        <v-card-text>
          <p class="mb-2">
            Tipo: {{ expediente.certificado_tipo ?? "sin determinar" }}
          </p>
          <v-btn
            variant="outlined"
            :disabled="!puedeCalcularTipo"
            :loading="calculandoTipo"
            @click="calcularTipoCertificado"
          >
            Calcular tipo de certificado
          </v-btn>
          <v-btn
            class="ml-2"
            variant="outlined"
            :disabled="!expediente.certificado_tipo"
            :loading="cargandoVistaPrevia"
            @click="verVistaPrevia"
          >
            Vista previa
          </v-btn>
        </v-card-text>
      </v-card>

      <v-card class="mb-4" variant="outlined">
        <v-card-title>Folio</v-card-title>
        <v-card-text>
          <p class="mb-1">Folio: {{ expediente.folio_externo ?? "sin asignar" }}</p>
          <p v-if="expediente.folio_asignado_at" class="text-caption text-medium-emphasis mb-2">
            Asignado el {{ formatearFecha(expediente.folio_asignado_at) }}
          </p>
          <p v-else-if="solicitandoFolio" class="text-caption text-medium-emphasis mb-2">
            Asignando siguiente folio disponible…
          </p>
          <v-btn
            color="primary"
            :disabled="!puedeSolicitarFolio"
            :loading="solicitandoFolio"
            @click="solicitarFolio"
          >
            Solicitar folio
          </v-btn>
        </v-card-text>
      </v-card>

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