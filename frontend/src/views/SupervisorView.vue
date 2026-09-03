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
  if (estado?.includes("APROBAD") || estado === "IMPRESO") {
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

// --- Sincronización (visibilidad de sync_outbox al operador) ---
const estadoSync = ref(null);
const cargandoEstadoSync = ref(false);
const sincronizando = ref(false);
const resultadoSync = ref(null);

async function cargarEstadoSync() {
  cargandoEstadoSync.value = true;
  error.value = null;
  try {
    const { data } = await api.get("/sync/estado");
    estadoSync.value = data;
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cargar el estado de sincronización.";
  } finally {
    cargandoEstadoSync.value = false;
  }
}

async function sincronizarAhora() {
  sincronizando.value = true;
  error.value = null;
  resultadoSync.value = null;
  try {
    const { data } = await api.post("/sync/procesar");
    resultadoSync.value = data;
    await cargarEstadoSync();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo procesar la cola de sincronización.";
  } finally {
    sincronizando.value = false;
  }
}

// --- Folios (inventario local, revisión Figma 2026-08-24) ---
const TIPOS_CERTIFICADO = ["PARTICULAR", "DOBLE_CERO", "INTENSIVO", "RECHAZO"];
const inventarioFolios = ref([]);
const cargandoInventario = ref(false);
const loteForm = reactive({ tipo_certificado: "PARTICULAR", folio_inicio: "", folio_fin: "" });
const registrandoLote = ref(false);

async function cargarInventarioFolios() {
  cargandoInventario.value = true;
  error.value = null;
  try {
    const { data } = await api.get("/folios/inventario");
    inventarioFolios.value = data;
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cargar el inventario de folios.";
  } finally {
    cargandoInventario.value = false;
  }
}

async function registrarLoteFolios() {
  registrandoLote.value = true;
  error.value = null;
  try {
    const { data } = await api.post("/folios/lotes", null, { params: { ...loteForm } });
    aviso.value = `${data.cantidad} folio(s) ${data.tipo_certificado} registrados.`;
    loteForm.folio_inicio = "";
    loteForm.folio_fin = "";
    await cargarInventarioFolios();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo registrar el lote de folios.";
  } finally {
    registrandoLote.value = false;
  }
}

// --- Límites de emisión (Certificate Result Projection Contract v1) ---
const METODOS_PRUEBA = ["GAS_STATIC", "GAS_DYNAMIC", "DIESEL_OPACITY"];
const FASES_LECTURA = ["RALENTI", "CRUCERO"];
const PARAMETROS_POR_METODO = {
  GAS_STATIC: ["hc_ppm", "co_pct", "o2_pct"],
  GAS_DYNAMIC: ["hc_ppm", "co_pct", "o2_pct"],
  DIESEL_OPACITY: ["coefficient_absorption_final_k_m1"],
};
const limitesEmision = ref([]);
const cargandoLimites = ref(false);
const limiteAbierto = ref(false);
const limiteForm = reactive({
  metodo: "GAS_DYNAMIC",
  fase: "RALENTI",
  parametro: "hc_ppm",
  valor_maximo: null,
  anio_modelo_desde: null,
  anio_modelo_hasta: null,
  peso_bruto_desde_kg: null,
  peso_bruto_hasta_kg: null,
});
const guardandoLimite = ref(false);

const limiteEsDiesel = computed(() => limiteForm.metodo === "DIESEL_OPACITY");
const parametrosDisponibles = computed(() => PARAMETROS_POR_METODO[limiteForm.metodo] ?? []);

function rangoTexto(desde, hasta) {
  if (desde == null && hasta == null) return "Sin acotar";
  return `${desde ?? "—"} – ${hasta ?? "—"}`;
}

async function cargarLimitesEmision() {
  cargandoLimites.value = true;
  error.value = null;
  try {
    const { data } = await api.get("/pruebas/limites-emision");
    limitesEmision.value = data;
  } catch (err) {
    error.value =
      err.response?.data?.detail || "No se pudo cargar el catálogo de límites de emisión.";
  } finally {
    cargandoLimites.value = false;
  }
}

function onMetodoLimiteChange(valor) {
  limiteForm.metodo = valor;
  limiteForm.fase = valor === "DIESEL_OPACITY" ? null : "RALENTI";
  limiteForm.parametro = PARAMETROS_POR_METODO[valor][0];
  limiteForm.anio_modelo_desde = null;
  limiteForm.anio_modelo_hasta = null;
  limiteForm.peso_bruto_desde_kg = null;
  limiteForm.peso_bruto_hasta_kg = null;
}

function abrirNuevoLimite() {
  onMetodoLimiteChange("GAS_DYNAMIC");
  limiteForm.valor_maximo = null;
  limiteAbierto.value = true;
}

async function guardarLimite() {
  guardandoLimite.value = true;
  error.value = null;
  try {
    await api.post("/pruebas/limites-emision", { ...limiteForm });
    aviso.value = "Límite de emisión guardado.";
    limiteAbierto.value = false;
    await cargarLimitesEmision();
  } catch (err) {
    const detail = err.response?.data?.detail;
    error.value =
      typeof detail === "string"
        ? detail
        : detail
          ? JSON.stringify(detail)
          : "No se pudo guardar el límite de emisión.";
  } finally {
    guardandoLimite.value = false;
  }
}

onMounted(() => {
  cargarMonitor();
  cargarUsuarios();
  cargarPermisos();
  cargarEstadoSync();
  cargarInventarioFolios();
  cargarLimitesEmision();
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
      <v-tab value="sincronizacion">Sincronización</v-tab>
      <v-tab value="folios">Folios</v-tab>
      <v-tab value="limites">Límites de emisión</v-tab>
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

      <v-window-item value="sincronizacion">
        <v-card variant="outlined">
          <v-card-title class="d-flex align-center ga-2">
            Sincronización con el central
            <v-spacer />
            <v-btn
              variant="text"
              icon="mdi-refresh"
              :loading="cargandoEstadoSync"
              @click="cargarEstadoSync"
            />
          </v-card-title>
          <v-card-text>
            <v-progress-linear v-if="cargandoEstadoSync && !estadoSync" indeterminate class="mb-4" />
            <template v-else-if="estadoSync">
              <v-row class="mb-2" dense>
                <v-col cols="6" sm="3">
                  <div class="text-caption text-medium-emphasis">Pendientes</div>
                  <div class="text-h6">{{ estadoSync.pendientes }}</div>
                </v-col>
                <v-col cols="6" sm="3">
                  <div class="text-caption text-medium-emphasis">En error</div>
                  <div class="text-h6">{{ estadoSync.en_error }}</div>
                </v-col>
                <v-col cols="6" sm="3">
                  <div class="text-caption text-medium-emphasis">Sincronizando</div>
                  <div class="text-h6">{{ estadoSync.sincronizando }}</div>
                </v-col>
                <v-col cols="6" sm="3">
                  <div class="text-caption text-medium-emphasis">Sincronizados</div>
                  <div class="text-h6">{{ estadoSync.sincronizados }}</div>
                </v-col>
              </v-row>
              <p v-if="estadoSync.pendiente_mas_antiguo" class="text-body-2 text-medium-emphasis mb-4">
                Pendiente más antiguo desde
                {{ new Date(estadoSync.pendiente_mas_antiguo).toLocaleString() }}.
              </p>
              <p v-else class="text-body-2 text-medium-emphasis mb-4">
                No hay nada pendiente de sincronizar.
              </p>

              <v-btn
                color="primary"
                :loading="sincronizando"
                :disabled="estadoSync.pendientes === 0"
                prepend-icon="mdi-sync"
                @click="sincronizarAhora"
              >
                Sincronizar ahora
              </v-btn>

              <p v-if="resultadoSync" class="text-body-2 mt-3">
                Último intento: {{ resultadoSync.enviados }} enviados,
                {{ resultadoSync.fallidos }} fallidos,
                {{ resultadoSync.en_backoff }} en espera de reintento
                (de {{ resultadoSync.procesados }} procesados).
              </p>
              <p v-if="resultadoSync?.fallidos > 0" class="text-caption text-medium-emphasis">
                No hay un central real definido todavía — los fallos son esperados hasta que
                exista esa integración.
              </p>
            </template>
          </v-card-text>
        </v-card>
      </v-window-item>

      <v-window-item value="folios">
        <v-card class="mb-4" variant="outlined">
          <v-card-title class="d-flex align-center ga-2">
            Inventario local de folios
            <v-spacer />
            <v-btn
              variant="text"
              icon="mdi-refresh"
              :loading="cargandoInventario"
              @click="cargarInventarioFolios"
            />
          </v-card-title>
          <v-card-text>
            <v-progress-linear v-if="cargandoInventario" indeterminate class="mb-4" />
            <v-table v-else density="compact">
              <thead>
                <tr>
                  <th>Tipo</th>
                  <th>Disponibles</th>
                  <th>Asignados</th>
                  <th>Impresos</th>
                  <th>Dañados</th>
                  <th>Invalidados</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="fila in inventarioFolios" :key="fila.tipo_certificado">
                  <td>{{ fila.tipo_certificado }}</td>
                  <td>{{ fila.disponibles }}</td>
                  <td>{{ fila.asignados }}</td>
                  <td>{{ fila.impresos }}</td>
                  <td>{{ fila.danados }}</td>
                  <td>{{ fila.invalidados }}</td>
                </tr>
              </tbody>
            </v-table>
          </v-card-text>
        </v-card>

        <v-card variant="outlined">
          <v-card-title>Registrar lote por rango</v-card-title>
          <v-card-text>
            <v-select
              v-model="loteForm.tipo_certificado"
              :items="TIPOS_CERTIFICADO"
              label="Tipo de certificado"
              variant="outlined"
              density="comfortable"
            />
            <v-text-field
              v-model="loteForm.folio_inicio"
              label="Folio inicial (ej. OAX-000001)"
              variant="outlined"
              density="comfortable"
            />
            <v-text-field
              v-model="loteForm.folio_fin"
              label="Folio final (ej. OAX-000500)"
              variant="outlined"
              density="comfortable"
            />
            <v-btn
              color="primary"
              :loading="registrandoLote"
              :disabled="!loteForm.folio_inicio || !loteForm.folio_fin"
              @click="registrarLoteFolios"
            >
              Registrar lote
            </v-btn>
          </v-card-text>
        </v-card>
      </v-window-item>

      <v-window-item value="limites">
        <v-card variant="outlined">
          <v-card-title class="d-flex align-center ga-2">
            Límites de emisión (NOM-041/NOM-045)
            <v-spacer />
            <v-btn
              variant="text"
              icon="mdi-refresh"
              :loading="cargandoLimites"
              @click="cargarLimitesEmision"
            />
            <v-btn color="primary" prepend-icon="mdi-plus" @click="abrirNuevoLimite">
              Nuevo límite
            </v-btn>
          </v-card-title>
          <v-card-text>
            <v-progress-linear v-if="cargandoLimites" indeterminate class="mb-4" />
            <p v-else-if="limitesEmision.length === 0" class="text-medium-emphasis">
              Sin límites cargados. NOM-041 (gasolina) debería estar precargada por
              <code>seed_limites_nom041.py</code>; NOM-045 (diésel) sigue pendiente de la tabla
              oficial.
            </p>
            <v-table v-else density="compact">
              <thead>
                <tr>
                  <th>Método</th>
                  <th>Fase</th>
                  <th>Parámetro</th>
                  <th>Máximo</th>
                  <th>Año-modelo</th>
                  <th>Peso bruto (kg)</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(fila, i) in limitesEmision" :key="i">
                  <td>{{ fila.metodo }}</td>
                  <td>{{ fila.fase ?? "—" }}</td>
                  <td>{{ fila.parametro }}</td>
                  <td>{{ fila.valor_maximo }}</td>
                  <td>{{ rangoTexto(fila.anio_modelo_desde, fila.anio_modelo_hasta) }}</td>
                  <td>{{ rangoTexto(fila.peso_bruto_desde_kg, fila.peso_bruto_hasta_kg) }}</td>
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

    <v-dialog v-model="limiteAbierto" max-width="480">
      <v-card>
        <v-card-title>Nuevo límite de emisión</v-card-title>
        <v-card-text>
          <v-select
            :model-value="limiteForm.metodo"
            :items="METODOS_PRUEBA"
            label="Método"
            variant="outlined"
            density="comfortable"
            @update:model-value="onMetodoLimiteChange"
          />
          <v-select
            v-if="!limiteEsDiesel"
            v-model="limiteForm.fase"
            :items="FASES_LECTURA"
            label="Fase"
            variant="outlined"
            density="comfortable"
          />
          <v-select
            v-model="limiteForm.parametro"
            :items="parametrosDisponibles"
            label="Parámetro"
            variant="outlined"
            density="comfortable"
          />
          <v-text-field
            v-model.number="limiteForm.valor_maximo"
            label="Valor máximo"
            type="number"
            variant="outlined"
            density="comfortable"
          />
          <v-text-field
            v-model.number="limiteForm.anio_modelo_desde"
            label="Año-modelo desde (vacío = sin acotar)"
            type="number"
            variant="outlined"
            density="comfortable"
          />
          <v-text-field
            v-model.number="limiteForm.anio_modelo_hasta"
            label="Año-modelo hasta (vacío = sin acotar)"
            type="number"
            variant="outlined"
            density="comfortable"
          />
          <!-- NOM-045 (diésel) estratifica por año-modelo Y peso bruto a la
               vez (corrección 2026-09-03, ver CLAUDE.md) — solo diésel
               admite estos dos campos adicionales; gasolina (NOM-041) no
               estratifica por peso. -->
          <template v-if="limiteEsDiesel">
            <v-text-field
              v-model.number="limiteForm.peso_bruto_desde_kg"
              label="Peso bruto desde, kg (vacío = sin acotar)"
              type="number"
              variant="outlined"
              density="comfortable"
            />
            <v-text-field
              v-model.number="limiteForm.peso_bruto_hasta_kg"
              label="Peso bruto hasta, kg (vacío = sin acotar)"
              type="number"
              variant="outlined"
              density="comfortable"
            />
          </template>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="limiteAbierto = false">Cancelar</v-btn>
          <v-btn
            color="primary"
            :loading="guardandoLimite"
            :disabled="!limiteForm.parametro || limiteForm.valor_maximo === null"
            @click="guardarLimite"
          >
            Guardar
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>
