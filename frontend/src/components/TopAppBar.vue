<script setup>
import { onBeforeUnmount, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { useSessionStore } from "../stores/session";

const session = useSessionStore();
const router = useRouter();

const REFRESCO_SYNC_MS = 30_000;
let intervalo = null;

function iniciarPolling() {
  if (intervalo) return;
  session.actualizarEstadoSync();
  intervalo = setInterval(() => session.actualizarEstadoSync(), REFRESCO_SYNC_MS);
}

function detenerPolling() {
  clearInterval(intervalo);
  intervalo = null;
}

watch(
  () => session.tieneSesionActiva,
  (activa) => (activa ? iniciarPolling() : detenerPolling()),
);

onMounted(() => {
  if (session.tieneSesionActiva) iniciarPolling();
});
onBeforeUnmount(detenerPolling);

function colorConexion(conexion, enError) {
  if (conexion === "en_linea") return "green";
  if (conexion === "sincronizando") return "amber";
  if (conexion === "pendientes") return enError > 0 ? "red" : "grey";
  return "grey";
}

function textoConexion(conexion, estadoSync) {
  if (conexion === "en_linea") return "Todo sincronizado";
  if (conexion === "sincronizando") return "Sincronizando…";
  if (conexion === "pendientes") {
    const { pendientes, en_error: enError } = estadoSync;
    return enError > 0 ? `${pendientes} pendientes (${enError} con error)` : `${pendientes} pendientes`;
  }
  return "—";
}
</script>

<template>
  <v-app-bar color="primary" density="comfortable">
    <v-app-bar-title>Sistema de Verificación Vehicular</v-app-bar-title>

    <v-chip v-if="session.estacion" class="mr-2" variant="flat" color="white">
      {{ session.estacion.station_type }} · {{ session.estacion.center_id }}
      <template v-if="session.estacion.line_id">
        · Línea {{ session.estacion.line_id }}
      </template>
    </v-chip>

    <v-chip
      class="mr-2"
      variant="flat"
      :color="colorConexion(session.conexion, session.estadoSync?.en_error)"
    >
      {{ textoConexion(session.conexion, session.estadoSync) }}
    </v-chip>

    <v-btn
      v-if="session.puedeSupervisar"
      class="mr-2"
      variant="tonal"
      color="white"
      prepend-icon="mdi-shield-account"
      @click="router.push({ name: 'supervisor' })"
    >
      Supervisor
    </v-btn>

    <v-btn v-if="session.tieneSesionActiva" icon="mdi-logout" @click="session.cerrarSesion()" />
  </v-app-bar>
</template>
