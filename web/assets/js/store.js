// Small observable state container for the framework-free frontend.

export function createStore(initialState) {
  let state = Object.freeze({ ...initialState });
  const listeners = new Set();
  return {
    getState: () => state,
    setState(update) {
      const patch = typeof update === "function" ? update(state) : update;
      state = Object.freeze({ ...state, ...patch });
      for (const listener of listeners) listener(state);
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    }
  };
}
