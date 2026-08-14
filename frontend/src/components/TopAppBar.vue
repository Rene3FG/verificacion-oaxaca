<script setup>
import { useRouter } from "vue-router";
import { useSessionStore } from "../stores/session";

const session = useSessionStore();
const router = useRouter();
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
      :color="session.conexion === 'en_linea' ? 'green' : 'grey'"
    >
      {{ session.conexion === "en_linea" ? "En línea" : "Sin internet" }}
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
