<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { api } from "../api/client";
import ExpedienteHeader from "../components/ExpedienteHeader.vue";
import { estadoColors } from "../plugins/vuetify";
import { useSessionStore } from "../stores/session";

const session = useSessionStore();

// Estados en los que el expediente sigue siendo "de Captura". A partir de
// DATOS_NORMALIZADOS pasa a Inspección Visual, que corre en la estación de
// Prueba (decisión de negocio 2026-08-07, ver CLAUDE.md) — esta vista solo
// cubre el paso de Registro.
const ESTADOS_CAPTURA = [
  "CREADO",
  "DATOS_SIOX_CONSULTADOS",
  "DATOS_SIOX_IMPORTADOS",
  "DATOS_CAPTURADOS_MANUALMENTE",
];
const ESTADOS_NORMALIZABLES = ["DATOS_SIOX_IMPORTADOS", "DATOS_CAPTURADOS_MANUALMENTE"];
const ESTADOS_CONSULTABLES_SIOX = ["CREADO", "DATOS_SIOX_CONSULTADOS"];

const VEHICULO_CAMPOS = [
  "niv",
  "marca",
  "linea",
  "modelo",
  "tipo_vehiculo",
  "combustible",
  "razon_social",
];

const pasos = [
  { title: "Registro", subtitle: "Captura" },
  { title: "Inspección visual", subtitle: "Estación de Prueba" },
  { title: "OBD/SBD", subtitle: "Estación de Prueba" },
  { title: "Enviar", subtitle: "Prueba dinámica/estática" },
];

const expedientesEnCurso = ref([]);
const cargandoLista = ref(false);
const placaNueva = ref("");
const creando = ref(false);

const expediente = ref(null);
const cargandoExpediente = ref(false);

const historialSiox = ref([]);
const cargandoHistorial = ref(false);
const consultandoSiox = ref(false);

const vehiculoForm = reactive({
  niv: null,
  marca: null,
  linea: null,
  modelo: null,
  tipo_vehiculo: null,
  combustible: null,
  razon_social: null,
});
const vehiculoOriginal = ref({});
const guardandoVehiculo = ref(false);
const confirmando = ref(false);

const error = ref(null);
const aviso = ref(null);

const pasoActual = computed(() => {
  if (!expediente.value) return 1;
  if (ESTADOS_CAPTURA.includes(expediente.value.estado)) return 1;
  return 2;
});

const puedeConsultarSiox = computed(
  () => expediente.value && ESTADOS_CONSULTABLES_SIOX.includes(expediente.value.estado)
);
const puedeEditarVehiculo = computed(
  () => expediente.value && ESTADOS_CAPTURA.includes(expediente.value.estado)
);
const puedeNormalizar = computed(
  () => expediente.value && ESTADOS_NORMALIZABLES.includes(expediente.value.estado)
);
const faltaCombustible = computed(() => !vehiculoForm.combustible);
const motivoNormalizarDeshabilitado = computed(() => {
  if (!puedeNormalizar.value) {
    return "Aún no hay datos importados de SIOX ni capturados manualmente.";
  }
  if (faltaCombustible.value) {
    return "El combustible es obligatorio para confirmar.";
  }
  return null;
});

const estadoSiox = computed(() => {
  if (consultandoSiox.value) return "CONSULTANDO";
  return historialSiox.value[0]?.status ?? "NO_CONSULTADO";
});
const SIOX_ESTADO_COLOR = {
  NO_CONSULTADO: estadoColors.pendiente,
  CONSULTANDO: estadoColors.proceso,
  EXITOSA: estadoColors.aprobado,
  SIN_DATOS: estadoColors.pendiente,
  ERROR: estadoColors.error,
};
const SIOX_ESTADO_TEXTO = {
  NO_CONSULTADO: "No consultado",
  CONSULTANDO: "Consultando…",
  EXITOSA: "Datos encontrados",
  SIN_DATOS: "Sin datos en SIOX",
  ERROR: "Error de conexión",
};

function esCampoEditado(campo) {
  return vehiculoForm[campo] !== (vehiculoOriginal.value[campo] ?? null);
}

function sincronizarVehiculoForm(vehiculo) {
  for (const campo of VEHICULO_CAMPOS) {
    vehiculoForm[campo] = vehiculo?.[campo] ?? null;
  }
  vehiculoOriginal.value = { ...vehiculoForm };
}

async function cargarExpedientesEnCurso() {
  if (!session.estacion?.center_id || !session.estacion?.line_id) return;
  cargandoLista.value = true;
  error.value = null;
  try {
    const { data } = await api.get("/expedientes", {
      params: {
        centro_id: session.estacion.center_id,
        linea_id: session.estacion.line_id,
      },
    });
    expedientesEnCurso.value = data.filter((exp) => ESTADOS_CAPTURA.includes(exp.estado));
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cargar la lista de expedientes.";
  } finally {
    cargandoLista.value = false;
  }
}

async function cargarHistorialSiox() {
  if (!expediente.value) return;
  cargandoHistorial.value = true;
  try {
    const { data } = await api.get(`/siox/consultas/${expediente.value.id}`);
    historialSiox.value = data;
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cargar el historial de SIOX.";
  } finally {
    cargandoHistorial.value = false;
  }
}

async function abrirExpediente(id) {
  cargandoExpediente.value = true;
  error.value = null;
  try {
    const { data } = await api.get(`/expedientes/${id}`);
    expediente.value = data;
    sincronizarVehiculoForm(data.vehiculo);
    await cargarHistorialSiox();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo abrir el expediente.";
  } finally {
    cargandoExpediente.value = false;
  }
}

async function crearExpediente() {
  if (!placaNueva.value.trim()) return;
  creando.value = true;
  error.value = null;
  try {
    const { data } = await api.post("/expedientes", { placa: placaNueva.value.trim() });
    placaNueva.value = "";
    await abrirExpediente(data.id);
    await cargarExpedientesEnCurso();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo crear el expediente.";
  } finally {
    creando.value = false;
  }
}

function cerrarExpediente() {
  expediente.value = null;
  historialSiox.value = [];
  aviso.value = null;
  cargarExpedientesEnCurso();
}

async function consultarSiox() {
  consultandoSiox.value = true;
  error.value = null;
  aviso.value = null;
  try {
    const { data } = await api.post(`/siox/consultar/${expediente.value.id}`);
    aviso.value = `Intento ${data.intento}: ${SIOX_ESTADO_TEXTO[data.status] ?? data.status}`;
    await abrirExpediente(expediente.value.id);
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo consultar SIOX.";
  } finally {
    consultandoSiox.value = false;
  }
}

async function capturaManual() {
  guardandoVehiculo.value = true;
  error.value = null;
  try {
    await api.post(`/siox/captura-manual/${expediente.value.id}`, { ...vehiculoForm });
    aviso.value = "Captura manual registrada.";
    await abrirExpediente(expediente.value.id);
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo registrar la captura manual.";
  } finally {
    guardandoVehiculo.value = false;
  }
}

async function guardarVehiculo() {
  guardandoVehiculo.value = true;
  error.value = null;
  try {
    await api.patch(`/expedientes/${expediente.value.id}/vehiculo`, { ...vehiculoForm });
    aviso.value = "Datos del vehículo guardados.";
    await abrirExpediente(expediente.value.id);
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudieron guardar los datos.";
  } finally {
    guardandoVehiculo.value = false;
  }
}

async function confirmarNormalizacion() {
  confirmando.value = true;
  error.value = null;
  try {
    await api.post(`/expedientes/${expediente.value.id}/normalizar`);
    aviso.value = "Expediente enviado a Inspección Visual.";
    cerrarExpediente();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo confirmar la normalización.";
  } finally {
    confirmando.value = false;
  }
}

onMounted(cargarExpedientesEnCurso);
</script>

<template>
  <v-container>
    <template v-if="!expediente">
      <p class="mb-4">
        Estación de Captura · Centro {{ session.estacion?.center_id }} · Línea
        {{ session.estacion?.line_id }}
      </p>

      <v-alert v-if="error" type="error" class="mb-4" closable @click:close="error = null">
        {{ error }}
      </v-alert>

      <v-card class="mb-4" variant="outlined">
        <v-card-title>Nuevo expediente</v-card-title>
        <v-card-text class="d-flex ga-3 align-center flex-wrap">
          <v-text-field
            v-model="placaNueva"
            label="Placa"
            variant="outlined"
            density="comfortable"
            hide-details
            style="max-width: 240px"
            @keyup.enter="crearExpediente"
          />
          <v-btn color="primary" :loading="creando" @click="crearExpediente">
            Crear expediente
          </v-btn>
        </v-card-text>
      </v-card>

      <v-card variant="outlined">
        <v-card-title>Expedientes en curso en esta línea</v-card-title>
        <v-card-text>
          <v-progress-circular v-if="cargandoLista" indeterminate />
          <p v-else-if="expedientesEnCurso.length === 0" class="text-medium-emphasis">
            No hay expedientes pendientes de registro en esta línea.
          </p>
          <v-list v-else>
            <v-list-item
              v-for="exp in expedientesEnCurso"
              :key="exp.id"
              :title="`Placa ${exp.placa}`"
              :subtitle="exp.estado"
              @click="abrirExpediente(exp.id)"
            />
          </v-list>
        </v-card-text>
      </v-card>
    </template>

    <template v-else>
      <div class="d-flex align-center mb-2">
        <v-btn variant="text" prepend-icon="mdi-arrow-left" @click="cerrarExpediente">
          Volver a la lista
        </v-btn>
      </div>

      <div class="expediente-fijo mb-4">
        <ExpedienteHeader :expediente="expediente" />
      </div>

      <v-stepper v-model="pasoActual" flat class="mb-4" :items="pasos.map((p) => p.title)" />

      <v-alert v-if="error" type="error" class="mb-4" closable @click:close="error = null">
        {{ error }}
      </v-alert>
      <v-alert v-if="aviso" type="success" class="mb-4" closable @click:close="aviso = null">
        {{ aviso }}
      </v-alert>

      <v-progress-linear v-if="cargandoExpediente" indeterminate class="mb-4" />

      <v-card class="mb-4" variant="outlined">
        <v-card-title class="d-flex align-center ga-2">
          Consulta SIOX
          <v-chip :color="SIOX_ESTADO_COLOR[estadoSiox]" variant="flat" size="small">
            {{ SIOX_ESTADO_TEXTO[estadoSiox] ?? estadoSiox }}
          </v-chip>
        </v-card-title>
        <v-card-text>
          <v-text-field
            :model-value="expediente.placa"
            label="Placa"
            variant="outlined"
            density="comfortable"
            readonly
            hint="La placa se fija al crear el expediente."
            persistent-hint
            class="mb-3"
            style="max-width: 240px"
          />

          <div class="d-flex ga-3 flex-wrap mb-4">
            <v-btn
              color="primary"
              :disabled="!puedeConsultarSiox"
              :loading="consultandoSiox"
              @click="consultarSiox"
            >
              {{ historialSiox.length === 0 ? "Consultar" : "Reintentar" }}
            </v-btn>
            <v-btn
              variant="outlined"
              :disabled="!puedeConsultarSiox"
              :loading="guardandoVehiculo"
              @click="capturaManual"
            >
              Captura manual
            </v-btn>
          </div>

          <v-divider class="mb-3" />

          <p class="text-subtitle-2 mb-2">Historial de consultas</p>
          <v-progress-circular v-if="cargandoHistorial" indeterminate size="24" />
          <p v-else-if="historialSiox.length === 0" class="text-medium-emphasis">
            Sin consultas todavía.
          </p>
          <v-table v-else density="compact">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Estado</th>
                <th>Marca / modelo</th>
                <th>Usuario</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="consulta in historialSiox" :key="consulta.id">
                <td>{{ new Date(consulta.created_at).toLocaleString() }}</td>
                <td>
                  <v-chip :color="SIOX_ESTADO_COLOR[consulta.status]" size="small" variant="flat">
                    {{ SIOX_ESTADO_TEXTO[consulta.status] ?? consulta.status }}
                  </v-chip>
                </td>
                <td>
                  {{ consulta.response_normalized?.marca ?? "—" }}
                  {{ consulta.response_normalized?.modelo ?? "" }}
                </td>
                <td>{{ consulta.consultado_por?.slice(0, 8) ?? "—" }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
      </v-card>

      <v-card class="mb-4" variant="outlined">
        <v-card-title class="d-flex align-center ga-2">
          Datos del vehículo
          <v-chip size="small" variant="tonal">
            Fuente: {{ expediente.vehiculo.fuente_datos }}
          </v-chip>
        </v-card-title>
        <v-card-text>
          <v-row dense>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="vehiculoForm.niv"
                label="NIV"
                variant="outlined"
                density="comfortable"
                :disabled="!puedeEditarVehiculo"
                :append-inner-icon="esCampoEditado('niv') ? 'mdi-pencil' : undefined"
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="vehiculoForm.marca"
                label="Marca"
                variant="outlined"
                density="comfortable"
                :disabled="!puedeEditarVehiculo"
                :append-inner-icon="esCampoEditado('marca') ? 'mdi-pencil' : undefined"
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="vehiculoForm.linea"
                label="Línea/Modelo comercial"
                variant="outlined"
                density="comfortable"
                :disabled="!puedeEditarVehiculo"
                :append-inner-icon="esCampoEditado('linea') ? 'mdi-pencil' : undefined"
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model.number="vehiculoForm.modelo"
                label="Modelo (año)"
                type="number"
                variant="outlined"
                density="comfortable"
                :disabled="!puedeEditarVehiculo"
                :append-inner-icon="esCampoEditado('modelo') ? 'mdi-pencil' : undefined"
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="vehiculoForm.tipo_vehiculo"
                label="Tipo de vehículo"
                variant="outlined"
                density="comfortable"
                :disabled="!puedeEditarVehiculo"
                :append-inner-icon="esCampoEditado('tipo_vehiculo') ? 'mdi-pencil' : undefined"
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="vehiculoForm.combustible"
                label="Combustible *"
                variant="outlined"
                density="comfortable"
                :disabled="!puedeEditarVehiculo"
                :hint="faltaCombustible ? 'Obligatorio para confirmar' : undefined"
                persistent-hint
                :append-inner-icon="esCampoEditado('combustible') ? 'mdi-pencil' : undefined"
              />
            </v-col>
          </v-row>
          <v-btn
            class="mt-2"
            variant="outlined"
            :disabled="!puedeEditarVehiculo"
            :loading="guardandoVehiculo"
            @click="guardarVehiculo"
          >
            Guardar datos del vehículo
          </v-btn>
        </v-card-text>
      </v-card>

      <v-card class="mb-4" variant="outlined">
        <v-card-title>Propietario</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="vehiculoForm.razon_social"
            label="Razón social"
            variant="outlined"
            density="comfortable"
            :disabled="!puedeEditarVehiculo"
            :append-inner-icon="esCampoEditado('razon_social') ? 'mdi-pencil' : undefined"
          />
          <v-alert type="info" variant="tonal" density="compact">
            La tarjeta de circulación no tiene campo propio en el backend todavía
            (ver Vehiculo/VehiculoUpdate) — pendiente de agregar si se necesita.
          </v-alert>
        </v-card-text>
      </v-card>

      <v-card variant="outlined">
        <v-card-text class="d-flex align-center ga-3 flex-wrap">
          <v-btn
            color="primary"
            size="large"
            :disabled="!!motivoNormalizarDeshabilitado"
            :loading="confirmando"
            @click="confirmarNormalizacion"
          >
            Confirmar datos
          </v-btn>
          <span v-if="motivoNormalizarDeshabilitado" class="text-medium-emphasis text-body-2">
            {{ motivoNormalizarDeshabilitado }}
          </span>
        </v-card-text>
      </v-card>
    </template>
  </v-container>
</template>

<style scoped>
.expediente-fijo {
  position: sticky;
  top: 0;
  z-index: 1;
  background: rgb(var(--v-theme-background));
}
</style>
