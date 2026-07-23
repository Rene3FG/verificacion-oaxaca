<script setup>
import { useSessionStore } from "../stores/session";

const session = useSessionStore();
</script>

<template>
  <v-container>
    <p>Impresión Central · Centro {{ session.estacion?.center_id }} · Líneas {{ session.estacion?.allowed_line_ids }}</p>
  </v-container>
</template>
