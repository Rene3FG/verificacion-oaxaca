<script setup>
import { onMounted, ref } from "vue";
import { api } from "../api/client";
import ExpedienteHeader from "../components/ExpedienteHeader.vue";
import { useSessionStore } from "../stores/session";

const session = useSessionStore();
const expedientes = ref([]);
const cargando = ref(false);
const error = ref(null);

async function cargarCola() {
  cargando.value = true;
  error.value = null;
  try {
    const { data } = await api.get("/pruebas/cola");
    expedientes.value = data;
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cargar la cola de prueba.";
  } finally {
    cargando.value = false;
  }
}

onMounted(cargarCola);
</script>

<template>
  <v-container>
    <p class="mb-4">
      Estación de Prueba · Centro {{ session.estacion?.center_id }} · Línea {{ session.estacion?.line_id }}
    </p>

    <v-alert v-if="error" type="error" class="mb-4">{{ error }}</v-alert>

    <v-progress-circular v-if="cargando" indeterminate class="mb-4" />

    <template v-else>
      <p v-if="expedientes.length === 0" class="text-medium-emphasis">
        No hay expedientes listos para prueba en esta línea.
      </p>
      <ExpedienteHeader
        v-for="expediente in expedientes"
        :key="expediente.id"
        :expediente="expediente"
      />
    </template>
  </v-container>
</template>
