<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useSessionStore } from "../stores/session";

const session = useSessionStore();
const router = useRouter();
const route = useRoute();
const enLogin = computed(() => route.name === "login");

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

// HU-004: fecha/hora siempre visible junto al contexto de la estación.
const ahora = ref(new Date());
const reloj = setInterval(() => (ahora.value = new Date()), 30_000);
onBeforeUnmount(() => clearInterval(reloj));
const fechaHora = computed(() =>
  ahora.value.toLocaleString("es-MX", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  })
);

function colorConexion(conexion, enError) {
  if (conexion === "en_linea") return "success";
  if (conexion === "sincronizando") return "warning";
  if (conexion === "pendientes") return enError > 0 ? "error" : "grey";
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
    <v-app-bar-title>Sistema de Verificación Vehicular Oaxaca</v-app-bar-title>

    <!-- Sin sesión (login) el Figma pide una barra limpia: solo "Acceso operativo",
         sin chips de estación ni de sincronización. -->
    <span v-if="enLogin" class="mr-4 text-body-2">Acceso operativo</span>

    <v-chip
      v-if="session.estacion && !enLogin"
      class="mr-2 rounded-institucional-full"
      variant="flat"
      color="white"
    >
      {{ session.estacion.station_type }} · {{ session.estacion.center_id }}
      <template v-if="session.estacion.line_id">
        · Línea {{ session.estacion.line_id }}
      </template>
    </v-chip>

    <v-chip
      v-if="!enLogin"
      class="mr-2 rounded-institucional-full"
      variant="flat"
      :color="colorConexion(session.conexion, session.estadoSync?.en_error)"
    >
      {{ textoConexion(session.conexion, session.estadoSync) }}
    </v-chip>

    <span v-if="!enLogin && session.usuario" class="mr-3 text-body-2">
      <v-icon icon="mdi-account" size="small" class="mr-1" />{{ session.usuario }}
    </span>
    <span v-if="!enLogin" class="mr-3 text-body-2">{{ fechaHora }}</span>

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
