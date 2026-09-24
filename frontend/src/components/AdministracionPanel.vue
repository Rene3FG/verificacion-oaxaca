<script setup>
import { onMounted, reactive, ref } from "vue";
import { api } from "../api/client";
import { useSessionStore } from "../stores/session";

const session = useSessionStore();
const STATION_TYPES = ["captura", "prueba", "impresion"];

const error = ref(null);
const aviso = ref(null);
const sub = ref("usuarios");

// --- Usuarios ---
const usuarios = ref([]);
const cargandoUsuarios = ref(false);
const usuarioAbierto = ref(false);
const usuarioEditandoId = ref(null);
const usuarioForm = reactive({ username: "", nombre_completo: "", password: "" });
const guardandoUsuario = ref(false);

async function cargarUsuarios() {
  cargandoUsuarios.value = true;
  try {
    const { data } = await api.get("/usuarios");
    usuarios.value = data;
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cargar la lista de usuarios.";
  } finally {
    cargandoUsuarios.value = false;
  }
}

function abrirUsuario(u = null) {
  usuarioEditandoId.value = u?.id ?? null;
  usuarioForm.username = u?.username ?? "";
  usuarioForm.nombre_completo = u?.nombre_completo ?? "";
  usuarioForm.password = "";
  usuarioAbierto.value = true;
}

async function guardarUsuario() {
  guardandoUsuario.value = true;
  error.value = null;
  try {
    if (usuarioEditandoId.value) {
      const cambios = { nombre_completo: usuarioForm.nombre_completo };
      if (usuarioForm.password) cambios.password = usuarioForm.password;
      await api.patch(`/usuarios/${usuarioEditandoId.value}`, cambios);
      aviso.value = "Usuario actualizado.";
    } else {
      await api.post("/usuarios", { ...usuarioForm });
      aviso.value = `Usuario ${usuarioForm.username} creado. Asígnale permisos en la pestaña Permisos.`;
    }
    usuarioAbierto.value = false;
    await cargarUsuarios();
  } catch (err) {
    error.value = err.response?.data?.detail?.[0]?.msg || err.response?.data?.detail || "No se pudo guardar el usuario.";
  } finally {
    guardandoUsuario.value = false;
  }
}

async function alternarUsuario(u) {
  error.value = null;
  try {
    await api.patch(`/usuarios/${u.id}`, { is_active: !u.is_active });
    await cargarUsuarios();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cambiar el estado del usuario.";
  }
}

// --- Estaciones ---
const estaciones = ref([]);
const cargandoEstaciones = ref(false);
const estacionAbierta = ref(false);
const estacionEditandoId = ref(null);
const estacionForm = reactive({
  name: "",
  station_type: "captura",
  center_id: "",
  line_id: null,
  device_identifier: "",
});
const guardandoEstacion = ref(false);

async function cargarEstaciones() {
  cargandoEstaciones.value = true;
  try {
    const { data } = await api.get("/estaciones", {
      params: { center_id: session.estacion?.center_id },
    });
    estaciones.value = data;
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cargar el listado de estaciones.";
  } finally {
    cargandoEstaciones.value = false;
  }
}

function abrirEstacion(e = null) {
  estacionEditandoId.value = e?.id ?? null;
  estacionForm.name = e?.name ?? "";
  estacionForm.station_type = e?.station_type ?? "captura";
  estacionForm.center_id = e?.center_id ?? session.estacion?.center_id ?? "";
  estacionForm.line_id = e?.line_id ?? null;
  estacionForm.device_identifier = e?.device_identifier ?? "";
  estacionAbierta.value = true;
}

async function guardarEstacion() {
  guardandoEstacion.value = true;
  error.value = null;
  const body = {
    ...estacionForm,
    line_id: estacionForm.line_id === "" ? null : estacionForm.line_id,
    device_identifier: estacionForm.device_identifier || null,
  };
  try {
    if (estacionEditandoId.value) {
      await api.patch(`/estaciones/${estacionEditandoId.value}`, body);
      aviso.value = "Estación actualizada.";
    } else {
      await api.post("/estaciones", body);
      aviso.value = `Estación ${body.name} creada.`;
    }
    estacionAbierta.value = false;
    await cargarEstaciones();
  } catch (err) {
    error.value = err.response?.data?.detail?.[0]?.msg || err.response?.data?.detail || "No se pudo guardar la estación.";
  } finally {
    guardandoEstacion.value = false;
  }
}

async function desactivarEstacion(e) {
  error.value = null;
  try {
    await api.patch(`/estaciones/${e.id}`, { is_active: false });
    aviso.value = `Estación ${e.name} desactivada.`;
    await cargarEstaciones();
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo desactivar la estación.";
  }
}

onMounted(() => {
  cargarUsuarios();
  cargarEstaciones();
});
</script>

<template>
  <div>
    <v-alert v-if="error" type="error" class="mb-4" closable @click:close="error = null">
      {{ error }}
    </v-alert>
    <v-alert v-if="aviso" type="success" class="mb-4" closable @click:close="aviso = null">
      {{ aviso }}
    </v-alert>

    <v-btn-toggle v-model="sub" mandatory density="compact" class="mb-4">
      <v-btn value="usuarios">Usuarios</v-btn>
      <v-btn value="estaciones">Estaciones</v-btn>
    </v-btn-toggle>

    <v-card v-if="sub === 'usuarios'" class="rounded-institucional-lg elevation-institucional-0" variant="flat">
      <v-card-title class="d-flex align-center ga-2">
        Usuarios
        <v-spacer />
        <v-btn color="primary" prepend-icon="mdi-plus" @click="abrirUsuario()">Nuevo usuario</v-btn>
      </v-card-title>
      <v-card-text>
        <v-progress-linear v-if="cargandoUsuarios" indeterminate class="mb-4" />
        <v-table v-else density="compact">
          <thead>
            <tr><th>Usuario</th><th>Nombre</th><th>Estado</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="u in usuarios" :key="u.id">
              <td>{{ u.username }}</td>
              <td>{{ u.nombre_completo }}</td>
              <td>
                <v-chip size="small" :color="u.is_active ? 'success' : 'grey'" variant="tonal">
                  {{ u.is_active ? "Activo" : "Inactivo" }}
                </v-chip>
              </td>
              <td class="text-right">
                <v-btn variant="text" size="small" @click="abrirUsuario(u)">Editar</v-btn>
                <v-btn variant="text" size="small" :color="u.is_active ? 'error' : 'success'" @click="alternarUsuario(u)">
                  {{ u.is_active ? "Desactivar" : "Reactivar" }}
                </v-btn>
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
    </v-card>

    <v-card v-else class="rounded-institucional-lg elevation-institucional-0" variant="flat">
      <v-card-title class="d-flex align-center ga-2">
        Estaciones
        <v-spacer />
        <v-btn color="primary" prepend-icon="mdi-plus" @click="abrirEstacion()">Nueva estación</v-btn>
      </v-card-title>
      <v-card-text>
        <v-progress-linear v-if="cargandoEstaciones" indeterminate class="mb-4" />
        <p v-else-if="estaciones.length === 0" class="text-medium-emphasis">Sin estaciones activas en este centro.</p>
        <v-table v-else density="compact">
          <thead>
            <tr><th>Nombre</th><th>Tipo</th><th>Línea</th><th>Dispositivo</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="e in estaciones" :key="e.id">
              <td>{{ e.name }}</td>
              <td>{{ e.station_type }}</td>
              <td>{{ e.line_id ?? "—" }}</td>
              <td>{{ e.device_identifier ?? "—" }}</td>
              <td class="text-right">
                <v-btn variant="text" size="small" @click="abrirEstacion(e)">Editar</v-btn>
                <v-btn variant="text" size="small" color="error" @click="desactivarEstacion(e)">Desactivar</v-btn>
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
    </v-card>

    <v-dialog v-model="usuarioAbierto" max-width="480">
      <v-card class="rounded-institucional-lg">
        <v-card-title>{{ usuarioEditandoId ? "Editar usuario" : "Nuevo usuario" }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="usuarioForm.username" label="Usuario" :disabled="!!usuarioEditandoId" />
          <v-text-field v-model="usuarioForm.nombre_completo" label="Nombre completo" />
          <v-text-field
            v-model="usuarioForm.password"
            type="password"
            :label="usuarioEditandoId ? 'Nueva contraseña (opcional)' : 'Contraseña (mín. 8)'"
            autocomplete="new-password"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="usuarioAbierto = false">Cancelar</v-btn>
          <v-btn color="primary" :loading="guardandoUsuario" @click="guardarUsuario">Guardar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="estacionAbierta" max-width="480">
      <v-card class="rounded-institucional-lg">
        <v-card-title>{{ estacionEditandoId ? "Editar estación" : "Nueva estación" }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="estacionForm.name" label="Nombre" />
          <v-select v-model="estacionForm.station_type" :items="STATION_TYPES" label="Tipo" />
          <v-text-field v-model="estacionForm.center_id" label="Centro" />
          <v-text-field v-model.number="estacionForm.line_id" type="number" label="Línea (opcional)" />
          <v-text-field v-model="estacionForm.device_identifier" label="Identificador de dispositivo (opcional)" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="estacionAbierta = false">Cancelar</v-btn>
          <v-btn color="primary" :loading="guardandoEstacion" @click="guardarEstacion">Guardar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
