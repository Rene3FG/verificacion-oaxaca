import { createApp } from "vue";
import { createPinia } from "pinia";

// Auto-hospedada (no Google Fonts CDN): el sistema opera sin internet
// (Etapa 12), así que la tipografía institucional no puede depender de
// una red externa disponible.
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "./styles/main.css";

import App from "./App.vue";
import router from "./router";
import vuetify from "./plugins/vuetify";

createApp(App).use(createPinia()).use(router).use(vuetify).mount("#app");
