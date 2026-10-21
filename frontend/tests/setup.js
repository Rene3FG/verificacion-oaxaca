// jsdom no trae ResizeObserver y Vuetify lo usa en VLayout/VAppBar.
globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
