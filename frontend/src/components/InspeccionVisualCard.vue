<script setup>
// Inspección visual NOM-047 (8 puntos Bueno/Malo/No aplica). Opción A de
// docs/PROPUESTA_FLUJO_INSPECCION_VISUAL_NOM047.md: el cliente indicó
// (2026-10-30 y 2026-11-06) que la inspección es el último paso de la
// captura, así que vive en la caseta. El resultado lo determina el backend
// (cualquier MALO rechaza); aquí solo se anticipa.
import { computed, onMounted, reactive, ref } from "vue";
import { api } from "../api/client";

const props = defineProps({
  verificacionId: { type: String, required: true },
});
const emit = defineEmits(["registrada"]);

const OPCIONES_ITEM = [
  { value: "BUENO", label: "Bueno" },
  { value: "MALO", label: "Malo" },
  { value: "NO_APLICA", label: "No aplica" },
];

const items = ref([]);
const respuestas = reactive({});
const observaciones = ref("");
const registrando = ref(false);
const error = ref(null);

const itemsMalos = computed(() => items.value.filter((i) => respuestas[i.clave] === "MALO"));
const completo = computed(
  () => items.value.length > 0 && items.value.every((i) => respuestas[i.clave] != null),
);
const resultado = computed(() => {
  if (!completo.value) return null;
  return itemsMalos.value.length === 0 ? "APROBADA" : "RECHAZADA";
});

async function cargarChecklist() {
  try {
    const { data } = await api.get("/inspeccion/checklist");
    items.value = data;
    for (const item of data) respuestas[item.clave] = null;
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo cargar el checklist de inspección visual.";
  }
}

async function registrar() {
  registrando.value = true;
  error.value = null;
  try {
    const { data } = await api.post(`/inspeccion/${props.verificacionId}`, {
      checklist: { ...respuestas },
      observaciones: observaciones.value.trim() || null,
    });
    emit("registrada", data);
  } catch (err) {
    error.value = err.response?.data?.detail || "No se pudo registrar la inspección.";
  } finally {
    registrando.value = false;
  }
}

onMounted(cargarChecklist);
defineExpose({ respuestas, observaciones, resultado, completo, registrar, error });
</script>

<template>
  <v-card class="mb-4 rounded-institucional-lg elevation-institucional-0" variant="flat">
    <v-card-title>Inspección visual</v-card-title>
    <v-card-subtitle class="texto-ayuda">
      Último paso de la captura. Un punto en Malo es rechazo directo, sin prueba de emisiones.
    </v-card-subtitle>
    <v-card-text>
      <v-alert v-if="error" type="error" class="mb-3" closable @click:close="error = null">
        {{ error }}
      </v-alert>
      <div
        v-for="item in items"
        :key="item.clave"
        class="d-flex align-center justify-space-between flex-wrap ga-2 py-2 border-b"
      >
        <span class="text-body-2" style="max-width: 55%">{{ item.etiqueta }}</span>
        <v-btn-toggle v-model="respuestas[item.clave]" density="compact" divided variant="outlined" color="primary">
          <v-btn
            v-for="opcion in OPCIONES_ITEM"
            :key="opcion.value"
            :value="opcion.value"
            size="small"
            :color="opcion.value === 'MALO' ? 'error' : undefined"
          >
            {{ opcion.label }}
          </v-btn>
        </v-btn-toggle>
      </div>

      <v-alert
        v-if="resultado"
        :type="resultado === 'APROBADA' ? 'success' : 'warning'"
        variant="tonal"
        density="compact"
        class="my-3"
      >
        <template v-if="resultado === 'APROBADA'">Resultado: Aprobada</template>
        <template v-else>
          Resultado: Rechazada — {{ itemsMalos.map((i) => i.etiqueta).join("; ") }}
        </template>
      </v-alert>
      <v-alert v-else type="info" variant="tonal" density="compact" class="my-3">
        Marca los {{ items.length }} puntos para poder registrar la inspección.
      </v-alert>

      <v-textarea
        v-if="resultado === 'RECHAZADA'"
        v-model="observaciones"
        label="Observaciones (opcional — los puntos en Malo ya son la causal)"
        variant="outlined"
        density="comfortable"
        rows="2"
      />

      <v-btn color="primary" :loading="registrando" :disabled="!completo" @click="registrar">
        Registrar inspección
      </v-btn>
    </v-card-text>
  </v-card>
</template>
