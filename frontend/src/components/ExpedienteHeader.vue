<script setup>
import { computed } from "vue";
import { estadoColors } from "../plugins/vuetify";
import { useSessionStore } from "../stores/session";
import { formatearFecha } from "../utils/format";

const props = defineProps({
  expediente: { type: Object, required: true },
});

const session = useSessionStore();

const modeloAuto = computed(() => {
  const v = props.expediente.vehiculo;
  if (!v) return null;
  return [v.marca, v.linea].filter(Boolean).join(" ") || null;
});

// Mapeo simplificado estado -> color semántico; ver guidelines de diseño
// (sección "Estados visuales del expediente") para el catálogo completo.
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
</script>

<template>
  <v-card class="mb-4" variant="outlined">
    <v-card-text>
      <div class="d-flex align-center flex-wrap ga-3 mb-3">
        <span class="text-h6">Expediente #{{ props.expediente.id?.slice(0, 8) }}</span>
        <v-spacer />
        <v-chip :color="colorEstado(props.expediente.estado)" variant="flat">
          {{ props.expediente.estado }}
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
