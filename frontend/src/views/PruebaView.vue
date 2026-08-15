<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { api } from "../api/client";
import ExpedienteHeader from "../components/ExpedienteHeader.vue";
import { useSessionStore } from "../stores/session";

const session = useSessionStore();

// Estados que le corresponden a esta estación (Inspección Visual y OBD/SBD
// corren aquí, decisión de negocio 2026-08-07 — ver CLAUDE.md). Fuera de
// esta lista, el expediente ya salió a Impresión o no ha llegado todavía.
const ESTADOS_PRUEBA = [
  "INSPECCION_VISUAL_PENDIENTE",
  "INSPECCION_VISUAL_APROBADA",
  "OBD_PENDIENTE",
  "OBD_SOLICITADO",
  "OBD_RECIBIDO",
  "LISTO_PARA_PRUEBA",
  "PRUEBA_CONFIGURADA",
  "PRUEBA_EN_PROCESO",
];

// Checklist propuesto a falta del documento de diseño del proyecto (no está
// en el repo, mismo caso que las reglas de impresión en app/services/certificado.py
// — ver CLAUDE.md). A confirmar/corregir con el equipo de Prueba.
const CHECKLIST_ITEMS = [
  { key: "luces_delanteras", label: "Luces delanteras" },
  { key: "luces_traseras", label: "Luces traseras y direccionales" },
  { key: "limpiaparabrisas_claxon", label: "Limpiaparabrisas y claxon" },
  { key: "espejos", label: "Espejos laterales" },
  { key: "llantas", label: "Llantas sin desgaste excesivo" },
  { key: "fugas", label: "Sin fugas visibles de aceite o combustible" },
  { key: "escape", label: "Sistema de escape sin fugas ni modificaciones" },
  { key: "placas", label: "Placas legibles y vigentes" },
];

const expedientesEnCurso = ref([]);
const cargandoLista = ref(false);

const expediente = ref(null);
const cargandoExpediente = ref(false);

const error = ref(null);
const aviso = ref(null);

// --- Corregir datos del vehículo (decisión de producto 2026-08-14: si
// Inspección Visual detecta un error, Prueba debe poder corregirlo sin
// devolver el expediente a Captura). Mismos campos que CapturaView.vue.
const CAMPOS_VEHICULO = ["niv", "marca", "linea", "modelo", "tipo_vehiculo"];
const vehiculoForm = reactive(Object.fromEntries(CAMPOS_VEHICULO.map((c) => [c, null])));
const guardandoVehiculo = ref(false);
const editandoVehiculo = ref(false);

function sincronizarVehiculoForm(vehiculo) {
  for (const campo of CAMPOS_VEHICULO) vehiculoForm[campo] = vehiculo?.[campo] ?? null;
}

async function guardarVehiculo() {
  guardandoVehiculo.value = true;
  error.value = null;
  try {
    await api.patch(`/expedientes/${expediente.value.id}/vehiculo`, { ...vehiculoForm });
    aviso.value = "Datos del vehículo corregidos.";
    editandoVehiculo.value = false;
    await recargarExpediente();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudieron guardar los datos.";
  } finally {
    guardandoVehiculo.value = false;
  }
}

// --- Inspección visual ---
const checklistForm = reactive(
  Object.fromEntries(CHECKLIST_ITEMS.map((item) => [item.key, true]))
);
const causalesRechazo = ref("");
const registrandoInspeccion = ref(false);

const itemsRechazados = computed(() =>
  CHECKLIST_ITEMS.filter((item) => !checklistForm[item.key])
);
const resultadoInspeccion = computed(() =>
  itemsRechazados.value.length === 0 ? "APROBADA" : "RECHAZADA"
);

function reiniciarChecklist() {
  for (const item of CHECKLIST_ITEMS) checklistForm[item.key] = true;
  causalesRechazo.value = "";
}

// --- OBD/SBD ---
const evaluandoObd = ref(false);
const solicitandoObd = ref(false);
const guardandoObd = ref(false);
const resultadoObd = ref("APROBADO");

// --- Prueba ---
const combustible = computed(() => expediente.value?.vehiculo?.combustible ?? "");
const esGasolina = computed(() => combustible.value.toUpperCase() === "GASOLINA");
const tipoPruebaDefault = computed(() => (esGasolina.value ? "DINAMICA" : "OPACIDAD"));
const cambioAEstatica = ref(false);
const motivoCambio = ref("");
const tipoPruebaElegido = computed(() =>
  esGasolina.value && cambioAEstatica.value ? "ESTATICA" : tipoPruebaDefault.value
);
const configurando = ref(false);
const iniciando = ref(false);
const guardandoResultado = ref(false);
const resultadoPrueba = ref("APROBADO");
const valoresMedidos = ref([{ clave: "", valor: "" }]);

function agregarValorMedido() {
  valoresMedidos.value.push({ clave: "", valor: "" });
}
function quitarValorMedido(i) {
  valoresMedidos.value.splice(i, 1);
}
function reiniciarPrueba() {
  cambioAEstatica.value = false;
  motivoCambio.value = "";
  resultadoPrueba.value = "APROBADO";
  valoresMedidos.value = [{ clave: "", valor: "" }];
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
    expedientesEnCurso.value = data.filter((exp) => ESTADOS_PRUEBA.includes(exp.estado));
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cargar la lista de expedientes.";
  } finally {
    cargandoLista.value = false;
  }
}

async function abrirExpediente(id) {
  cargandoExpediente.value = true;
  error.value = null;
  try {
    const { data } = await api.get(`/expedientes/${id}`);
    expediente.value = data;
    reiniciarChecklist();
    reiniciarPrueba();
    sincronizarVehiculoForm(data.vehiculo);
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo abrir el expediente.";
  } finally {
    cargandoExpediente.value = false;
  }
}

function cerrarExpediente() {
  expediente.value = null;
  aviso.value = null;
  cargarExpedientesEnCurso();
}

async function recargarExpediente() {
  await abrirExpediente(expediente.value.id);
}

async function registrarInspeccion() {
  registrandoInspeccion.value = true;
  error.value = null;
  try {
    await api.post(`/inspeccion/${expediente.value.id}`, {
      resultado: resultadoInspeccion.value,
      checklist_json: { ...checklistForm },
      causales_rechazo:
        resultadoInspeccion.value === "RECHAZADA"
          ? { detalle: causalesRechazo.value, items: itemsRechazados.value.map((i) => i.key) }
          : null,
    });
    if (resultadoInspeccion.value === "RECHAZADA") {
      aviso.value = "Inspección rechazada. El expediente se envió a Impresión Central.";
      cerrarExpediente();
    } else {
      aviso.value = "Inspección visual aprobada.";
      await recargarExpediente();
    }
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo registrar la inspección.";
  } finally {
    registrandoInspeccion.value = false;
  }
}

async function evaluarObd() {
  evaluandoObd.value = true;
  error.value = null;
  try {
    const { data } = await api.post(`/obd/evaluar/${expediente.value.id}`);
    aviso.value = data.aplica
      ? "OBD/SBD aplica a este vehículo."
      : "OBD/SBD no aplica; el expediente pasa directo a Prueba.";
    await recargarExpediente();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo evaluar OBD/SBD.";
  } finally {
    evaluandoObd.value = false;
  }
}

async function solicitarObd() {
  solicitandoObd.value = true;
  error.value = null;
  try {
    await api.post(`/obd/solicitar/${expediente.value.id}`);
    aviso.value = "OBD/SBD solicitado.";
    await recargarExpediente();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo solicitar OBD/SBD.";
  } finally {
    solicitandoObd.value = false;
  }
}

async function guardarResultadoObd() {
  guardandoObd.value = true;
  error.value = null;
  try {
    await api.post(`/obd/resultado/${expediente.value.id}`, { resultado: resultadoObd.value });
    aviso.value = "Resultado de OBD/SBD guardado. Expediente listo para prueba.";
    await recargarExpediente();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo guardar el resultado de OBD/SBD.";
  } finally {
    guardandoObd.value = false;
  }
}

async function configurarPrueba() {
  configurando.value = true;
  error.value = null;
  try {
    await api.post(`/pruebas/configurar/${expediente.value.id}`, null, {
      params: {
        tipo_prueba: tipoPruebaElegido.value,
        cambio_manual: cambioAEstatica.value,
        motivo: cambioAEstatica.value ? motivoCambio.value : undefined,
      },
    });
    aviso.value = `Prueba configurada: ${tipoPruebaElegido.value}.`;
    await recargarExpediente();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo configurar la prueba.";
  } finally {
    configurando.value = false;
  }
}

async function iniciarPrueba() {
  iniciando.value = true;
  error.value = null;
  try {
    await api.post(`/pruebas/iniciar/${expediente.value.id}`);
    aviso.value = "Prueba iniciada.";
    await recargarExpediente();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo iniciar la prueba.";
  } finally {
    iniciando.value = false;
  }
}

async function guardarResultadoPrueba() {
  guardandoResultado.value = true;
  error.value = null;
  try {
    const valores = Object.fromEntries(
      valoresMedidos.value.filter((v) => v.clave.trim()).map((v) => [v.clave.trim(), v.valor])
    );
    await api.post(`/pruebas/resultado/${expediente.value.id}`, {
      resultado: resultadoPrueba.value,
      valores_medidos_json: valores,
    });
    aviso.value = "Resultado de prueba guardado. Expediente enviado a Impresión Central.";
    cerrarExpediente();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo guardar el resultado de la prueba.";
  } finally {
    guardandoResultado.value = false;
  }
}

onMounted(cargarExpedientesEnCurso);
</script>

<template>
  <v-container>
    <template v-if="!expediente">
      <p class="mb-4">
        Estación de Prueba · Centro {{ session.estacion?.center_id }} · Línea
        {{ session.estacion?.line_id }}
      </p>

      <v-alert v-if="error" type="error" class="mb-4" closable @click:close="error = null">
        {{ error }}
      </v-alert>

      <v-card variant="outlined">
        <v-card-title class="d-flex align-center ga-2">
          Expedientes en curso en esta línea
          <v-spacer />
          <v-btn variant="text" icon="mdi-refresh" :loading="cargandoLista" @click="cargarExpedientesEnCurso" />
        </v-card-title>
        <v-card-text>
          <v-progress-circular v-if="cargandoLista" indeterminate />
          <p v-else-if="expedientesEnCurso.length === 0" class="text-medium-emphasis">
            No hay expedientes pendientes en Inspección Visual, OBD/SBD o Prueba en esta línea.
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

      <v-alert v-if="error" type="error" class="mb-4" closable @click:close="error = null">
        {{ error }}
      </v-alert>
      <v-alert v-if="aviso" type="success" class="mb-4" closable @click:close="aviso = null">
        {{ aviso }}
      </v-alert>

      <v-progress-linear v-if="cargandoExpediente" indeterminate class="mb-4" />

      <!-- Corregir datos del vehículo: si Inspección Visual (o cualquier
           paso de Prueba) detecta un error en los datos, se corrige aquí
           sin devolver el expediente a Captura. -->
      <v-card class="mb-4" variant="outlined">
        <v-card-title class="d-flex align-center ga-2" style="cursor: pointer" @click="editandoVehiculo = !editandoVehiculo">
          Datos del vehículo
          <span class="text-body-2 text-medium-emphasis">(fuente: {{ expediente.vehiculo?.fuente_datos }})</span>
          <v-spacer />
          <v-icon :icon="editandoVehiculo ? 'mdi-chevron-up' : 'mdi-pencil'" />
        </v-card-title>
        <v-card-text v-if="editandoVehiculo">
          <v-row dense>
            <v-col cols="12" sm="6"><v-text-field v-model="vehiculoForm.niv" label="NIV" variant="outlined" density="compact" /></v-col>
            <v-col cols="12" sm="6"><v-text-field v-model="vehiculoForm.marca" label="Marca" variant="outlined" density="compact" /></v-col>
            <v-col cols="12" sm="6"><v-text-field v-model="vehiculoForm.linea" label="Línea/versión" variant="outlined" density="compact" /></v-col>
            <v-col cols="12" sm="6"><v-text-field v-model.number="vehiculoForm.modelo" label="Modelo" type="number" variant="outlined" density="compact" /></v-col>
            <v-col cols="12" sm="6"><v-text-field v-model="vehiculoForm.tipo_vehiculo" label="Tipo de vehículo" variant="outlined" density="compact" /></v-col>
          </v-row>
          <v-btn color="primary" :loading="guardandoVehiculo" @click="guardarVehiculo">
            Guardar corrección
          </v-btn>
        </v-card-text>
      </v-card>

      <!-- Inspección visual -->
      <v-card v-if="expediente.estado === 'INSPECCION_VISUAL_PENDIENTE'" class="mb-4" variant="outlined">
        <v-card-title>Inspección visual</v-card-title>
        <v-card-text>
          <v-checkbox
            v-for="item in CHECKLIST_ITEMS"
            :key="item.key"
            v-model="checklistForm[item.key]"
            :label="item.label"
            density="compact"
            hide-details
            color="primary"
          />

          <v-alert
            :type="resultadoInspeccion === 'APROBADA' ? 'success' : 'warning'"
            variant="tonal"
            density="compact"
            class="my-3"
          >
            Resultado: {{ resultadoInspeccion === "APROBADA" ? "Aprobada" : "Rechazada" }}
          </v-alert>

          <v-textarea
            v-if="resultadoInspeccion === 'RECHAZADA'"
            v-model="causalesRechazo"
            label="Detalle del rechazo (obligatorio)"
            variant="outlined"
            density="comfortable"
            rows="2"
          />

          <v-btn
            color="primary"
            :loading="registrandoInspeccion"
            :disabled="resultadoInspeccion === 'RECHAZADA' && !causalesRechazo.trim()"
            @click="registrarInspeccion"
          >
            Registrar inspección
          </v-btn>
        </v-card-text>
      </v-card>

      <!-- OBD/SBD -->
      <v-card
        v-else-if="['INSPECCION_VISUAL_APROBADA', 'OBD_PENDIENTE', 'OBD_SOLICITADO', 'OBD_RECIBIDO'].includes(expediente.estado)"
        class="mb-4"
        variant="outlined"
      >
        <v-card-title>OBD / SBD</v-card-title>
        <v-card-text>
          <template v-if="expediente.estado === 'INSPECCION_VISUAL_APROBADA'">
            <p class="mb-3 text-body-2">
              Determina si este vehículo requiere prueba OBD/SBD según tipo de unidad,
              combustible y modelo.
            </p>
            <v-btn color="primary" :loading="evaluandoObd" @click="evaluarObd">
              Evaluar aplicabilidad
            </v-btn>
          </template>

          <template v-else-if="expediente.estado === 'OBD_PENDIENTE'">
            <p class="mb-3 text-body-2">OBD/SBD aplica a este vehículo.</p>
            <v-btn color="primary" :loading="solicitandoObd" @click="solicitarObd">
              Solicitar OBD/SBD
            </v-btn>
          </template>

          <template v-else-if="expediente.estado === 'OBD_SOLICITADO'">
            <v-select
              v-model="resultadoObd"
              :items="['APROBADO', 'RECHAZADO', 'ERROR']"
              label="Resultado OBD/SBD"
              variant="outlined"
              density="comfortable"
              style="max-width: 320px"
            />
            <v-btn color="primary" :loading="guardandoObd" @click="guardarResultadoObd">
              Guardar resultado
            </v-btn>
          </template>
        </v-card-text>
      </v-card>

      <!-- Prueba dinámica/estática/opacidad -->
      <v-card
        v-else-if="['LISTO_PARA_PRUEBA', 'PRUEBA_CONFIGURADA', 'PRUEBA_EN_PROCESO'].includes(expediente.estado)"
        class="mb-4"
        variant="outlined"
      >
        <v-card-title>Prueba</v-card-title>
        <v-card-text>
          <template v-if="expediente.estado === 'LISTO_PARA_PRUEBA'">
            <p class="mb-2 text-body-2">
              Combustible: <strong>{{ combustible || "sin dato" }}</strong> · Tipo por defecto:
              <strong>{{ tipoPruebaDefault }}</strong>
            </p>
            <v-switch
              v-if="esGasolina"
              v-model="cambioAEstatica"
              label="Cambiar a prueba estática"
              color="primary"
              hide-details
              class="mb-2"
            />
            <v-textarea
              v-if="cambioAEstatica"
              v-model="motivoCambio"
              label="Motivo del cambio (obligatorio)"
              variant="outlined"
              density="comfortable"
              rows="2"
            />
            <v-btn
              color="primary"
              :loading="configurando"
              :disabled="cambioAEstatica && !motivoCambio.trim()"
              @click="configurarPrueba"
            >
              Configurar prueba ({{ tipoPruebaElegido }})
            </v-btn>
          </template>

          <template v-else-if="expediente.estado === 'PRUEBA_CONFIGURADA'">
            <p class="mb-3 text-body-2">
              Tipo de prueba: <strong>{{ expediente.tipo_prueba_final }}</strong>
            </p>
            <v-btn color="primary" :loading="iniciando" @click="iniciarPrueba">
              Iniciar prueba
            </v-btn>
          </template>

          <template v-else-if="expediente.estado === 'PRUEBA_EN_PROCESO'">
            <p class="mb-3 text-body-2">
              Tipo de prueba: <strong>{{ expediente.tipo_prueba_final }}</strong>
            </p>

            <p class="text-subtitle-2 mb-2">Valores medidos</p>
            <div
              v-for="(fila, i) in valoresMedidos"
              :key="i"
              class="d-flex ga-2 mb-2 align-center"
            >
              <v-text-field
                v-model="fila.clave"
                label="Parámetro"
                variant="outlined"
                density="compact"
                hide-details
              />
              <v-text-field
                v-model="fila.valor"
                label="Valor"
                variant="outlined"
                density="compact"
                hide-details
              />
              <v-btn icon="mdi-delete" variant="text" size="small" @click="quitarValorMedido(i)" />
            </div>
            <v-btn variant="text" prepend-icon="mdi-plus" class="mb-4" @click="agregarValorMedido">
              Agregar valor
            </v-btn>

            <v-select
              v-model="resultadoPrueba"
              :items="['APROBADO', 'RECHAZADO', 'ERROR']"
              label="Resultado de la prueba"
              variant="outlined"
              density="comfortable"
              style="max-width: 320px"
              class="mb-2"
            />
            <v-btn color="primary" :loading="guardandoResultado" @click="guardarResultadoPrueba">
              Guardar resultado
            </v-btn>
          </template>
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
