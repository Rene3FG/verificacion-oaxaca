<script setup>
import TopAppBar from "./components/TopAppBar.vue";
</script>

<template>
  <v-app>
    <TopAppBar />
    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>
