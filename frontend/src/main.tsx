import { ChakraProvider, defaultSystem } from "@chakra-ui/react";
import type { FC } from "react";

import { HomePage } from "src/pages/HomePage";
import type { PluginProps } from "src/types";

/**
 * Plugin root. Must be the module's only (default) export so the UMD build
 * assigns the component function itself to `globalThis.AirflowPlugin`.
 *
 * Uses the Chakra system provided by the Airflow Core UI for consistent
 * theming; falls back to the default system when running standalone (dev).
 */
const DagSmith: FC<PluginProps> = (props) => {
  const system =
    (globalThis.ChakraUISystem as typeof defaultSystem | undefined) ?? defaultSystem;

  return (
    <ChakraProvider value={system}>
      <HomePage {...props} />
    </ChakraProvider>
  );
};

export default DagSmith;
