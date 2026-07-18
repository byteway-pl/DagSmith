// Props injected by Airflow's ReactPlugin host component (route params).
export type PluginProps = {
  dagId?: string;
  mapIndex?: string;
  runId?: string;
  taskId?: string;
};

declare global {
  // Chakra UI system shared by the Airflow Core UI at runtime.
  // eslint-disable-next-line no-var
  var ChakraUISystem: unknown;
}
