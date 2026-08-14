<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useSessionStore } from "../stores/session";

const session = useSessionStore();
const router = useRouter();
const username = ref("");
const password = ref("");

const ROUTE_BY_STATION_TYPE = {
  captura: "captura",
  prueba: "prueba",
  impresion: "impresion",
};

onMounted(async () => {
  try {
    await session.detectarEstacion();
  } catch {
    // session.error ya queda seteado; se muestra en el template.
  }
});

async function entrar() {
  await session.iniciarSesion(username.value, password.value);
  router.push({ name: ROUTE_BY_STATION_TYPE[session.estacion.station_type] });
}
</script>

<template>
  <v-container class="fill-height" max-width="480">
    <v-card class="w-100" variant="elevated">
      <v-card-title>Sistema de Verificación Vehicular</v-card-title>
      <v-card-text>
        <v-alert v-if="session.error" type="error" class="mb-4">
          {{ session.error }}
        </v-alert>

        <template v-if="session.estacion">
          <p class="mb-2">
            Estación detectada: <strong>{{ session.estacion.name }}</strong>
          </p>
          <p class="mb-4">
            Centro: {{ session.estacion.center_id }}
            <template v-if="session.estacion.line_id">
              · Línea: {{ session.estacion.line_id }}
            </template>
          </p>

          <v-text-field
            v-model="username"
            label="Usuario"
            variant="outlined"
            autocomplete="username"
            @keyup.enter="entrar"
          />
          <v-text-field
            v-model="password"
            label="Contraseña"
            type="password"
            variant="outlined"
            autocomplete="current-password"
            @keyup.enter="entrar"
          />

          <v-btn
            color="primary"
            block
            :loading="session.cargando"
            @click="entrar"
          >
            Iniciar sesión
          </v-btn>
        </template>

        <v-progress-circular v-else-if="session.cargando" indeterminate />
      </v-card-text>
    </v-card>
  </v-container>
</template>
