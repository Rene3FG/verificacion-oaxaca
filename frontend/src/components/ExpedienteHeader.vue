<script setup>
import { computed, ref, watch } from "vue";
import { api } from "../api/client";
import { useSessionStore } from "../stores/session";
import { formatearFecha } from "../utils/format";
import { colorEstado, iconoEstado, textoEstado } from "../utils/estado";

const props = defineProps({
  expediente: { type: Object, required: true },
});

const session = useSessionStore();

const modeloAuto = computed(() => {
  const v = props.expediente.vehiculo;
  if (!v) return null;
  return [v.marca, v.linea].filter(Boolean).join(" ") || null;
});

// HU-105/109/110: estado de sincronización de este expediente. Se vuelve a
// consultar cuando cambia su estado o updated_at (cada acción encola filas).
const sync = ref(null);
const SYNC_UI = {
  SINCRONIZADO: { color: "success", icon: "mdi-cloud-check", texto: "Sincronizado" },
  PENDIENTE: { color: "warning", icon: "mdi-cloud-upload", texto: "Pendiente de sincronizar" },
  ERROR: { color: "error", icon: "mdi-cloud-alert", texto: "Error de sincronización" },
  SIN_REGISTROS: { color: "default", icon: "mdi-cloud-outline", texto: "Sin sincronizar" },
};
const syncUi = computed(() => (sync.value ? SYNC_UI[sync.value.estado] : null));
watch(
  () => [props.expediente.id, props.expediente.updated_at],
  async ([id]) => {
    if (!id) return;
    try {
      sync.value = (await api.get(`/sync/expediente/${id}`)).data;
    } catch {
      sync.value = null;
    }
  },
  { immediate: true },
);
</script>

<template>
  <v-card class="mb-4 rounded-institucional-lg elevation-institucional-0" variant="flat">
    <v-card-text>
      <div class="d-flex align-center flex-wrap ga-3 mb-3">
        <span class="text-h6">Expediente #{{ props.expediente.id?.slice(0, 8) }}</span>
        <v-spacer />
        <v-chip
          v-if="syncUi"
          :color="syncUi.color"
          :prepend-icon="syncUi.icon"
          class="rounded-institucional-full"
          variant="tonal"
          :title="`${sync.pendientes} pendientes · ${sync.en_error} con error · ${sync.sincronizados} enviados`"
        >
          {{ syncUi.texto }}
        </v-chip>
        <v-chip
          :color="colorEstado(props.expediente.estado)"
          :prepend-icon="iconoEstado(props.expediente.estado)"
          class="rounded-institucional-full"
          variant="flat"
        >
          {{ textoEstado(props.expediente.estado) }}
        </v-chip>
      </div>

      <!-- Franja de datos según Figma (módulo Impresión): PLACA, MODELO,
      COMBUSTIBLE, TIPO, CENTRO, LÍNEA, OPERADOR, FECHA/HORA como campos
      etiquetados en fila, no chips sueltos. "TIPO" en el diseño es el tipo
      de certificado (certificado_tipo), no el tipo de prueba. "OPERADOR"
      no viene del backend por expediente (ExpedienteRead no lo expone,
      ver schemas/verificacion.py) — se muestra el usuario de la sesión
      actual de esta estación como aproximación, no un dato inventado. -->
      <v-row dense>
        <v-col cols="6" sm="3" md="auto">
          <span class="text-caption text-medium-emphasis d-block">Placa</span>
          <span class="font-weight-medium">
            {{ props.expediente.placa }}
            <template v-if="modeloAuto">({{ modeloAuto }})</template>
          </span>
        </v-col>
        <v-col cols="6" sm="3" md="auto">
          <span class="text-caption text-medium-emphasis d-block">Modelo</span>
          <span class="font-weight-medium">{{ props.expediente.vehiculo?.modelo ?? "—" }}</span>
        </v-col>
        <v-col cols="6" sm="3" md="auto">
          <span class="text-caption text-medium-emphasis d-block">Combustible</span>
          <span class="font-weight-medium">{{ props.expediente.combustible_validado ?? "—" }}</span>
        </v-col>
        <v-col cols="6" sm="3" md="auto">
          <span class="text-caption text-medium-emphasis d-block">Tipo</span>
          <span class="font-weight-medium">{{ props.expediente.certificado_tipo ?? "—" }}</span>
        </v-col>
        <v-col cols="6" sm="3" md="auto">
          <span class="text-caption text-medium-emphasis d-block">Centro</span>
          <span class="font-weight-medium">{{ props.expediente.centro_id }}</span>
        </v-col>
        <v-col cols="6" sm="3" md="auto">
          <span class="text-caption text-medium-emphasis d-block">Línea</span>
          <span class="font-weight-medium">{{ props.expediente.linea_id }}</span>
        </v-col>
        <v-col cols="6" sm="3" md="auto">
          <span class="text-caption text-medium-emphasis d-block">Operador</span>
          <span class="font-weight-medium">{{ session.usuario ?? "—" }}</span>
        </v-col>
        <v-col cols="6" sm="3" md="auto">
          <span class="text-caption text-medium-emphasis d-block">Fecha / hora</span>
          <span class="font-weight-medium">
            {{ formatearFecha(props.expediente.updated_at) ?? "—" }}
          </span>
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>
