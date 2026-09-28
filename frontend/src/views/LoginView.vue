<script setup>
import { computed, onMounted, ref } from "vue";
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

const TIPO_ESTACION = { captura: "Captura", prueba: "Prueba", impresion: "Impresión" };

onMounted(async () => {
  try {
    await session.detectarEstacion();
  } catch {
    // session.error/errorTipo ya quedan seteados; se muestran en el template.
  }
});

async function entrar() {
  try {
    await session.iniciarSesion(username.value, password.value);
  } catch {
    // session.errorTipo distingue 401 (credenciales) de 403 (sin permiso).
    return;
  }
  router.push({ name: ROUTE_BY_STATION_TYPE[session.estacion.station_type] });
}

function cambiarUsuario() {
  username.value = "";
  password.value = "";
  session.limpiarError();
}

const centro = computed(() => {
  const c = session.estacion?.center_id ?? "";
  return c.charAt(0).toUpperCase() + c.slice(1);
});

const lineas = computed(() => {
  const e = session.estacion;
  if (!e) return "";
  const lista = e.allowed_line_ids?.length ? e.allowed_line_ids : e.line_id ? [e.line_id] : [];
  if (lista.length === 0) return "Todas";
  if (lista.length === 1) return `Línea ${lista[0]}`;
  return `Líneas ${lista.slice(0, -1).join(", ")} y ${lista[lista.length - 1]}`;
});

const tipoEstacion = computed(
  () => TIPO_ESTACION[session.estacion?.station_type] ?? session.estacion?.station_type,
);

const centroYLinea = computed(() => `${centro.value} · ${lineas.value}`);

// Estado que se renderiza: A = estación no configurada, B = acceso denegado
// (403), C = formulario de login (incluye el error de credenciales, 401).
const estado = computed(() => {
  if (session.errorTipo === "estacion_no_configurada" || !session.estacion) {
    return session.cargando && !session.errorTipo ? "cargando" : "estacion_no_configurada";
  }
  if (session.errorTipo === "sin_permiso") return "sin_permiso";
  return "formulario";
});
</script>

<template>
  <v-container class="fill-height justify-center">
    <v-progress-circular v-if="estado === 'cargando'" indeterminate />

    <!-- Estado A: estación no configurada (Figma: Acceso / Error — Estación no configurada) -->
    <v-card
      v-else-if="estado === 'estacion_no_configurada'"
      class="login-card rounded-institucional-lg elevation-institucional-0"
      variant="flat"
    >
      <v-card-title class="login-titulo">No es posible iniciar sesión</v-card-title>
      <v-card-text>
        <v-alert type="error" variant="tonal" class="mb-4" icon="mdi-monitor-off">
          <div class="font-weight-bold">Estación no configurada</div>
          {{ session.error }} El espacio de trabajo no puede cargarse hasta completar su configuración.
        </v-alert>

        <div class="bloque-gris mb-4">
          <div class="font-weight-bold mb-1">Qué debe configurarse</div>
          La computadora debe tener una workstation válida con centro, tipo de estación y línea cuando aplique.
        </div>

        <v-btn
          color="primary"
          variant="outlined"
          class="text-none"
          :loading="session.cargando"
          @click="session.detectarEstacion().catch(() => {})"
        >
          Reintentar detección
        </v-btn>
      </v-card-text>
    </v-card>

    <!-- Estado B: acceso denegado, autenticación válida pero sin permiso (HTTP 403) -->
    <v-card
      v-else-if="estado === 'sin_permiso'"
      class="login-card rounded-institucional-lg elevation-institucional-0"
      variant="flat"
    >
      <v-card-title class="login-titulo">Acceso denegado</v-card-title>
      <v-card-text>
        <div class="tarjeta-estacion mb-4">
          <div class="fila-meta"><span>Usuario</span><strong>{{ session.usuarioDenegado }}</strong></div>
          <div class="fila-meta"><span>Estación</span><strong>{{ session.estacion.name }}</strong></div>
          <div class="fila-meta"><span>Centro / línea</span><strong>{{ centroYLinea }}</strong></div>
        </div>

        <v-alert type="error" variant="tonal" class="mb-4" icon="mdi-lock-outline">
          <div class="font-weight-bold">Sin permiso para esta estación</div>
          {{ session.error }} Tu sesión no puede abrir el espacio de trabajo de {{ tipoEstacion }} {{ lineas }}.
        </v-alert>

        <p class="texto-ayuda mb-4">
          La autenticación fue válida; el bloqueo corresponde a la autorización sobre la estación física.
        </p>

        <v-btn color="primary" variant="outlined" class="text-none" @click="cambiarUsuario">
          Cambiar usuario
        </v-btn>
      </v-card-text>
    </v-card>

    <!-- Estado C: formulario de login -->
    <v-card v-else class="login-card rounded-institucional-lg elevation-institucional-0" variant="flat">
      <v-card-title class="login-titulo">Iniciar sesión</v-card-title>
      <v-card-subtitle class="texto-ayuda">
        La estación fue detectada automáticamente en esta computadora.
      </v-card-subtitle>
      <v-card-text class="pt-4">
        <v-alert v-if="session.errorTipo === 'credenciales'" type="error" class="mb-4">
          {{ session.error }}
        </v-alert>

        <div class="tarjeta-estacion mb-4">
          <div class="d-flex align-center justify-space-between mb-2">
            <span class="etiqueta-estacion">Estación detectada</span>
            <v-chip size="small" color="success" variant="tonal" prepend-icon="mdi-check-circle">
              Configurada
            </v-chip>
          </div>
          <div class="fila-meta"><span>Estación</span><strong>{{ session.estacion.name }}</strong></div>
          <div class="fila-meta"><span>Centro</span><strong>{{ centro }}</strong></div>
          <div class="fila-meta"><span>Línea</span><strong>{{ lineas }}</strong></div>
          <div class="fila-meta"><span>Tipo</span><strong>{{ tipoEstacion }}</strong></div>
        </div>

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

        <div class="bloque-gris mb-4">
          <strong>Validación de acceso</strong> — Al iniciar sesión, el sistema valida que el usuario tenga
          permiso para operar esta estación.
        </div>

        <v-btn color="primary" block size="large" class="text-none" :loading="session.cargando" @click="entrar">
          Iniciar sesión
        </v-btn>
      </v-card-text>
    </v-card>
  </v-container>
</template>

<style scoped>
.login-card {
  width: 100%;
  max-width: 640px;
  padding: 12px 16px;
  border: 1px solid #e5e7eb !important;
}
.login-titulo {
  font-size: 24px;
  font-weight: 700;
  color: #111827;
}
.texto-ayuda {
  font-size: 12px;
  color: #4b5563;
}
.tarjeta-estacion {
  background: #fdf3f6;
  border-radius: 10px;
  padding: 16px;
}
.etiqueta-estacion {
  font-size: 12px;
  font-weight: 600;
  color: #7f1d3b;
}
.fila-meta {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  padding: 2px 0;
}
.fila-meta span {
  color: #4b5563;
}
.bloque-gris {
  background: #f1f3f5;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 12px;
  color: #374151;
}
</style>
