<script setup>
import { estadoColors } from "../plugins/vuetify";

const props = defineProps({
  expediente: { type: Object, required: true },
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
    <v-card-text class="d-flex align-center flex-wrap ga-3">
      <span class="text-h6">Expediente #{{ props.expediente.id?.slice(0, 8) }}</span>
      <v-chip>Placa {{ props.expediente.placa }}</v-chip>
      <v-chip v-if="props.expediente.vehiculo?.modelo">
        Modelo {{ props.expediente.vehiculo.modelo }}
      </v-chip>
      <v-chip v-if="props.expediente.combustible_validado">
        {{ props.expediente.combustible_validado }}
      </v-chip>
      <v-chip :color="colorEstado(props.expediente.estado)" variant="flat">
        {{ props.expediente.estado }}
      </v-chip>
    </v-card-text>
  </v-card>
</template>
