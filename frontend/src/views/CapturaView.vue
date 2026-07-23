<script setup>
import { useSessionStore } from "../stores/session";

const session = useSessionStore();
</script>

<template>
  <v-container>
    <p>Estación de Captura · Centro {{ session.estacion?.center_id }} · Línea {{ session.estacion?.line_id }}</p>
  </v-container>
</template>
