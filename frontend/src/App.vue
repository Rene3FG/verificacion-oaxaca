<script setup>
import { watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import TopAppBar from "./components/TopAppBar.vue";
import { useSessionStore } from "./stores/session";

const session = useSessionStore();
const route = useRoute();
const router = useRouter();

// QA-E2E-01: el guard del router solo corre al navegar; cerrar sesión (botón
// de salida o 401 del servidor) no navega por sí solo y dejaba la vista
// operativa abierta sin sesión. Cualquier pérdida de sesión regresa al login.
watch(
  () => session.tieneSesionActiva,
  (activa) => {
    if (!activa && route.name !== "login") router.replace({ name: "login" });
  },
);
</script>

<template>
  <v-app>
    <TopAppBar />
    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>
