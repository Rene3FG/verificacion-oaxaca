<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { api } from "../api/client";
import { estadoColors } from "../plugins/vuetify";
import { useSessionStore } from "../stores/session";

const session = useSessionStore();

const STATION_TYPES = ["captura", "prueba", "impresion"];

const tab = ref("monitor");
const error = ref(null);
const aviso = ref(null);

// --- Monitor (HU-111) ---
const expedientes = ref([]);
const cargandoMonitor = ref(false);

async function cargarMonitor() {
  cargandoMonitor.value = true;
  error.value = null;
  try {
    const { data } = await api.get("/supervision/monitor");
    expedientes.value = data;
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cargar el monitor del centro.";
  } finally {
    cargandoMonitor.value = false;
  }
}

function colorEstado(estado) {
  if (estado?.includes("RECHAZAD") || estado?.includes("ERROR") || estado?.includes("FALLIDA")) {
    return estadoColors.rechazado;
  }
  if (estado?.includes("APROBAD") || estado === "CERRADO" || estado === "IMPRESO") {
    return estadoColors.aprobado;
  }
  if (estado?.includes("PROCESO") || estado?.includes("SOLICITADO")) {
    return estadoColors.proceso;
  }
  return estadoColors.pendiente;
}

// --- Bitácora (HU-117) ---
const bitacoraAbierta = ref(false);
const bitacoraExpediente = ref(null);
const bitacora = ref([]);
const cargandoBitacora = ref(false);

async function abrirBitacora(expediente) {
  bitacoraExpediente.value = expediente;
  bitacoraAbierta.value = true;
  cargandoBitacora.value = true;
  bitacora.value = [];
  try {
    const { data } = await api.get(`/supervision/expedientes/${expediente.id}/bitacora`);
    bitacora.value = data;
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cargar la bitácora.";
  } finally {
    cargandoBitacora.value = false;
  }
}

// --- Reasignar línea (HU-114) ---
const reasignarAbierto = ref(false);
const reasignarExpediente = ref(null);
const reasignarForm = reactive({ nueva_linea_id: null, motivo: "" });
const reasignando = ref(false);

function abrirReasignar(expediente) {
  reasignarExpediente.value = expediente;
  reasignarForm.nueva_linea_id = null;
  reasignarForm.motivo = "";
  reasignarAbierto.value = true;
}

async function confirmarReasignar() {
  reasignando.value = true;
  error.value = null;
  try {
    await api.post(`/expedientes/${reasignarExpediente.value.id}/reasignar-linea`, {
      nueva_linea_id: reasignarForm.nueva_linea_id,
      motivo: reasignarForm.motivo,
    });
    aviso.value = `Expediente reasignado a la línea ${reasignarForm.nueva_linea_id}.`;
    reasignarAbierto.value = false;
    await cargarMonitor();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo reasignar la línea.";
  } finally {
    reasignando.value = false;
  }
}

// --- Permisos (HU-121) ---
const usuarios = ref([]);
const permisos = ref([]);
const cargandoPermisos = ref(false);

const usuariosPorId = computed(() => {
  const mapa = {};
  for (const u of usuarios.value) mapa[u.id] = u;
  return mapa;
});

async function cargarUsuarios() {
  try {
    const { data } = await api.get("/usuarios");
    usuarios.value = data;
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cargar la lista de usuarios.";
  }
}

async function cargarPermisos() {
  cargandoPermisos.value = true;
  error.value = null;
  try {
    const { data } = await api.get("/permisos", {
      params: { center_id: session.estacion?.center_id },
    });
    permisos.value = data;
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cargar la lista de permisos.";
  } finally {
    cargandoPermisos.value = false;
  }
}

const permisoAbierto = ref(false);
const permisoForm = reactive({
  user_id: null,
  station_type: "captura",
  center_id: "",
  line_id: null,
  can_operate: true,
  can_supervise: false,
});
const guardandoPermiso = ref(false);

function abrirNuevoPermiso() {
  permisoForm.user_id = null;
  permisoForm.station_type = "captura";
  permisoForm.center_id = session.estacion?.center_id ?? "";
  permisoForm.line_id = null;
  permisoForm.can_operate = true;
  permisoForm.can_supervise = false;
  permisoAbierto.value = true;
}

async function crearPermiso() {
  guardandoPermiso.value = true;
  error.value = null;
  try {
    await api.post("/permisos", { ...permisoForm });
    aviso.value = "Permiso creado.";
    permisoAbierto.value = false;
    await cargarPermisos();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo crear el permiso.";
  } finally {
    guardandoPermiso.value = false;
  }
}

async function actualizarPermiso(permiso, campo, valor) {
  error.value = null;
  try {
    await api.patch(`/permisos/${permiso.id}`, { [campo]: valor });
    await cargarPermisos();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo actualizar el permiso.";
    await cargarPermisos();
  }
}

async function eliminarPermiso(permiso) {
  error.value = null;
  try {
    await api.delete(`/permisos/${permiso.id}`);
    aviso.value = "Permiso eliminado.";
    await cargarPermisos();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo eliminar el permiso.";
  }
}

onMounted(() => {
  cargarMonitor();
  cargarUsuarios();
  cargarPermisos();
});
</script>

<template>
  <v-container>
    <p class="mb-4">
      Supervisión · Centro {{ session.estacion?.center_id }}
    </p>

    <v-alert v-if="error" type="error" class="mb-4" closable @click:close="error = null">
      {{ error }}
    </v-alert>
    <v-alert v-if="aviso" type="success" class="mb-4" closable @click:close="aviso = null">
      {{ aviso }}
    </v-alert>

    <v-tabs v-model="tab" class="mb-4">
      <v-tab value="monitor">Monitor</v-tab>
      <v-tab value="permisos">Permisos</v-tab>
    </v-tabs>

    <v-window v-model="tab">
      <v-window-item value="monitor">
        <v-card variant="outlined">
          <v-card-title class="d-flex align-center ga-2">
            Expedientes en curso
            <v-spacer />
            <v-btn
              variant="text"
              icon="mdi-refresh"
              :loading="cargandoMonitor"
              @click="cargarMonitor"
            />
          </v-card-title>
          <v-card-text>
            <v-progress-linear v-if="cargandoMonitor" indeterminate class="mb-4" />
            <p v-else-if="expedientes.length === 0" class="text-medium-emphasis">
              No hay expedientes activos en este centro.
            </p>
            <v-table v-else density="compact">
              <thead>
                <tr>
                  <th>Línea</th>
                  <th>Placa</th>
                  <th>Estado</th>
                  <th>Actualizado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="exp in expedientes" :key="exp.id">
                  <td>{{ exp.linea_id }}</td>
                  <td>{{ exp.placa }}</td>
                  <td>
                    <v-chip :color="colorEstado(exp.estado)" size="small" variant="flat">
                      {{ exp.estado }}
                    </v-chip>
                  </td>
                  <td>{{ new Date(exp.updated_at).toLocaleString() }}</td>
                  <td class="d-flex ga-2">
                    <v-btn size="small" variant="text" @click="abrirBitacora(exp)">
                      Bitácora
                    </v-btn>
                    <v-btn size="small" variant="text" @click="abrirReasignar(exp)">
                      Reasignar línea
                    </v-btn>
                  </td>
                </tr>
              </tbody>
            </v-table>
          </v-card-text>
        </v-card>
      </v-window-item>

      <v-window-item value="permisos">
        <v-card variant="outlined">
          <v-card-title class="d-flex align-center ga-2">
            Permisos por estación
            <v-spacer />
            <v-btn color="primary" prepend-icon="mdi-plus" @click="abrirNuevoPermiso">
              Nuevo permiso
            </v-btn>
          </v-card-title>
          <v-card-text>
            <v-progress-linear v-if="cargandoPermisos" indeterminate class="mb-4" />
            <p v-else-if="permisos.length === 0" class="text-medium-emphasis">
              Sin permisos registrados para este centro.
            </p>
            <v-table v-else density="compact">
              <thead>
                <tr>
                  <th>Usuario</th>
                  <th>Estación</th>
                  <th>Centro</th>
                  <th>Línea</th>
                  <th>Opera</th>
                  <th>Supervisa</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="permiso in permisos" :key="permiso.id">
                  <td>
                    {{ usuariosPorId[permiso.user_id]?.username ?? permiso.user_id.slice(0, 8) }}
                  </td>
                  <td>{{ permiso.station_type }}</td>
                  <td>{{ permiso.center_id }}</td>
                  <td>{{ permiso.line_id ?? "Todas" }}</td>
                  <td>
                    <v-switch
                      :model-value="permiso.can_operate"
                      hide-details
                      density="compact"
                      color="primary"
                      @update:model-value="(v) => actualizarPermiso(permiso, 'can_operate', v)"
                    />
                  </td>
                  <td>
                    <v-switch
                      :model-value="permiso.can_supervise"
                      hide-details
                      density="compact"
                      color="primary"
                      @update:model-value="(v) => actualizarPermiso(permiso, 'can_supervise', v)"
                    />
                  </td>
                  <td>
                    <v-btn
                      size="small"
                      variant="text"
                      icon="mdi-delete"
                      @click="eliminarPermiso(permiso)"
                    />
                  </td>
                </tr>
              </tbody>
            </v-table>
          </v-card-text>
        </v-card>
      </v-window-item>
    </v-window>

    <v-dialog v-model="bitacoraAbierta" max-width="640">
      <v-card>
        <v-card-title>
          Bitácora · Placa {{ bitacoraExpediente?.placa }}
        </v-card-title>
        <v-card-text>
          <v-progress-circular v-if="cargandoBitacora" indeterminate />
          <p v-else-if="bitacora.length === 0" class="text-medium-emphasis">
            Sin eventos registrados.
          </p>
          <v-timeline v-else density="compact" side="end">
            <v-timeline-item v-for="evento in bitacora" :key="evento.id" size="x-small">
              <div class="text-caption text-medium-emphasis">
                {{ new Date(evento.created_at).toLocaleString() }} · {{ evento.modulo }}
              </div>
              <div>{{ evento.evento }}</div>
              <div v-if="evento.estado_anterior || evento.estado_nuevo" class="text-caption">
                {{ evento.estado_anterior ?? "—" }} → {{ evento.estado_nuevo ?? "—" }}
              </div>
            </v-timeline-item>
          </v-timeline>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="bitacoraAbierta = false">Cerrar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="reasignarAbierto" max-width="480">
      <v-card>
        <v-card-title>
          Reasignar línea · Placa {{ reasignarExpediente?.placa }}
        </v-card-title>
        <v-card-text>
          <p class="mb-3 text-body-2">
            Línea actual: {{ reasignarExpediente?.linea_id }}
          </p>
          <v-text-field
            v-model.number="reasignarForm.nueva_linea_id"
            label="Nueva línea"
            type="number"
            variant="outlined"
            density="comfortable"
          />
          <v-textarea
            v-model="reasignarForm.motivo"
            label="Motivo (obligatorio)"
            variant="outlined"
            density="comfortable"
            rows="2"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="reasignarAbierto = false">Cancelar</v-btn>
          <v-btn
            color="primary"
            :loading="reasignando"
            :disabled="!reasignarForm.nueva_linea_id || !reasignarForm.motivo.trim()"
            @click="confirmarReasignar"
          >
            Reasignar
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="permisoAbierto" max-width="480">
      <v-card>
        <v-card-title>Nuevo permiso</v-card-title>
        <v-card-text>
          <v-select
            v-model="permisoForm.user_id"
            :items="usuarios"
            item-title="username"
            item-value="id"
            label="Usuario"
            variant="outlined"
            density="comfortable"
          />
          <v-select
            v-model="permisoForm.station_type"
            :items="STATION_TYPES"
            label="Tipo de estación"
            variant="outlined"
            density="comfortable"
          />
          <v-text-field
            v-model="permisoForm.center_id"
            label="Centro"
            variant="outlined"
            density="comfortable"
          />
          <v-text-field
            v-model.number="permisoForm.line_id"
            label="Línea (vacío = todas)"
            type="number"
            variant="outlined"
            density="comfortable"
          />
          <v-switch v-model="permisoForm.can_operate" label="Puede operar" color="primary" />
          <v-switch v-model="permisoForm.can_supervise" label="Puede supervisar" color="primary" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="permisoAbierto = false">Cancelar</v-btn>
          <v-btn
            color="primary"
            :loading="guardandoPermiso"
            :disabled="!permisoForm.user_id || !permisoForm.center_id"
            @click="crearPermiso"
          >
            Crear
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>
