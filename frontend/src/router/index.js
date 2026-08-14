import { createRouter, createWebHistory } from "vue-router";
import { useSessionStore } from "../stores/session";

const routes = [
  { path: "/", name: "login", component: () => import("../views/LoginView.vue") },
  {
    path: "/captura",
    name: "captura",
    component: () => import("../views/CapturaView.vue"),
    meta: { stationType: "captura" },
  },
  {
    path: "/prueba",
    name: "prueba",
    component: () => import("../views/PruebaView.vue"),
    meta: { stationType: "prueba" },
  },
  {
    path: "/impresion",
    name: "impresion",
    component: () => import("../views/ImpresionView.vue"),
    meta: { stationType: "impresion" },
  },
  {
    path: "/supervisor",
    name: "supervisor",
    component: () => import("../views/SupervisorView.vue"),
    meta: { requiereSupervisor: true },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

// HU-007/008: una estación solo puede operar su propio módulo; sin sesión
// activa se regresa siempre a login.
router.beforeEach((to) => {
  const session = useSessionStore();
  if (to.meta.stationType && !session.tieneSesionActiva) {
    return { name: "login" };
  }
  if (to.meta.stationType && session.estacion?.station_type !== to.meta.stationType) {
    return { name: "login" };
  }
  if (to.meta.requiereSupervisor && !session.puedeSupervisar) {
    return { name: "login" };
  }
});

export default router;
