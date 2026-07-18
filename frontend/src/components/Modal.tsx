import { Box, Flex, Heading } from "@chakra-ui/react";
import type { FC, ReactNode } from "react";

// Minimal overlay modal (Chakra v3 Dialog composition avoided on purpose for M1).
export const Modal: FC<{ title: string; children: ReactNode; wide?: boolean }> = ({
  title,
  children,
  wide = false,
}) => (
  <Flex
    position="fixed"
    inset="0"
    bg="blackAlpha.600"
    zIndex={1400}
    align="center"
    justify="center"
    p={4}
  >
    <Box
      bg="bg.panel"
      borderRadius="md"
      boxShadow="lg"
      p={5}
      maxW={wide ? "5xl" : "lg"}
      w="full"
      maxH="85vh"
      overflowY="auto"
    >
      <Heading size="md" mb={4}>
        {title}
      </Heading>
      {children}
    </Box>
  </Flex>
);
