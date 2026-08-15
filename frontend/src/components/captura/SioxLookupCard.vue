<template>
  <v-card class="elevation-2 rounded-lg pa-4">
    <v-card-title class="text-h6 font-weight-bold d-flex align-center">
      <v-icon color="primary" class="mr-2">mdi-car-search</v-icon>
      Consulta e Importación SIOX (Etapa 2)
    </v-card-title>

    <v-card-text>
      <!-- Formulario de búsqueda por placa -->
      <v-row align="center">
        <v-col cols="12" md="8">
          <v-text-field
            v-model="placaInput"
            label="Placa del Vehículo"
            placeholder="Ej. TLA1234"
            variant="outlined"
            density="compact"
            hide-details="auto"
            :rules="[rules.required, rules.placaFormat]"
            @keyup.enter="handleBuscar"
            clearable
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-btn
            color="primary"
            block
            size="large"
            :loading="expedienteStore.sioxStatus === 'LOADING'"
            :disabled="!isPlacaValida"
            @click="handleBuscar"
          >
            <v-icon left class="mr-1">mdi-magnify</v-icon>
            Consultar SIOX
          </v-btn>
        </v-col>
      </v-row>

      <!-- Feedback de Estado: Consultando -->
      <v-progress-linear
        v-if="expedienteStore.sioxStatus === 'LOADING'"
        indeterminate
        color="primary"
        class="mt-4"
      />

      <!-- Feedback de Estado: Sin datos o Error -->
      <v-alert
        v-if="expedienteStore.sioxStatus === 'NOT_FOUND' || expedienteStore.sioxStatus === 'ERROR'"
        type="warning"
        variant="tonal"
        class="mt-4"
        closable
      >
        {{ expedienteStore.sioxErrorMessage }}
        <div class="mt-2">
          <v-btn size="small" variant="outlined" color="warning" @click="activarCapturaManual">
            Capturar Datos Manualmente
          </v-btn>
        </div>
      </v-alert>

      <!-- Resultado de SIOX Encontrado -->
      <v-card v-if="expedienteStore.tieneSioxValido" variant="outlined" class="mt-4 pa-3 bg-grey-lighten-5">
        <div class="d-flex justify-space-between align-center mb-2">
          <span class="text-subtitle-1 font-weight-bold text-success">
            <v-icon color="success">mdi-check-circle</v-icon> Datos Obtenidos de SIOX
          </span>
          <v-chip color="info" size="small" label>Origen: SIOX</v-chip>
        </div>

        <v-row density="compact">
          <v-col cols="6" sm="4"><strong>Marca:</strong> {{ expedienteStore.sioxData.marca }}</v-col>
          <v-col cols="6" sm="4"><strong>Submarca/Línea:</strong> {{ expedienteStore.sioxData.linea }}</v-col>
          <v-col cols="6" sm="4"><strong>Modelo (Año):</strong> {{ expedienteStore.sioxData.modelo }}</v-col>
          <v-col cols="6" sm="4"><strong>NÚMERO DE SERIE (VIN):</strong> {{ expedienteStore.sioxData.vin }}</v-col>
          <v-col cols="6" sm="4"><strong>Combustible:</strong> {{ expedienteStore.sioxData.tipo_combustible }}</v-col>
        </v-row>

        <v-divider class="my-3" />

        <!-- Botón de Confirmación Manual según Regla de Negocio -->
        <div class="d-flex justify-end">
          <v-btn
            color="success"
            size="large"
            :loading="expedienteStore.loading"
            :disabled="expedienteStore.datosConfirmadosManual"
            @click="handleConfirmarNormalizacion"
          >
            <v-icon class="mr-1">mdi-file-check</v-icon>
            Confirmar y Normalizar Datos
          </v-btn>
        </div>
      </v-card>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref, computed } from 'vue';
import { useExpedienteStore } from '@/stores/expedienteStore';

const expedienteStore = useExpedienteStore();
const placaInput = ref('');

const rules = {
  required: (v) => !!v || 'La placa es obligatoria',
  placaFormat: (v) => /^[A-Z0-9-]{6,8}$/i.test(v) || 'Formato de placa inválido',
};

const isPlacaValida = computed(() => {
  return placaInput.value && rules.placaFormat(placaInput.value) === true;
});

const handleBuscar = () => {
  if (isPlacaValida.value) {
    expedienteStore.buscarPlacaSiox(placaInput.value.toUpperCase());
  }
};

const handleConfirmarNormalizacion = async () => {
  try {
    await expedienteStore.confirmarYNormalizar(expedienteStore.sioxData);
  } catch (err) {
    console.error('Error al confirmar datos:', err);
  }
};

const activarCapturaManual = () => {
  // Lógica para habilitar captura manual cuando SIOX no retorna datos (HU-015)
};
</script>