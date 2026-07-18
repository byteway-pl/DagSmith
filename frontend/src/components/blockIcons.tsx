import type { IconType } from "react-icons";
import { FaAws, FaDatabase, FaDocker } from "react-icons/fa";
import {
  FiBox,
  FiCircle,
  FiCode,
  FiEye,
  FiFile,
  FiFolder,
  FiGitBranch,
  FiGlobe,
  FiMail,
  FiPackage,
  FiRepeat,
  FiShare2,
  FiStar,
  FiTerminal,
  FiZap,
} from "react-icons/fi";
import {
  SiCelery,
  SiGoogle,
  SiKubernetes,
  SiPython,
  SiRedis,
  SiSnowflake,
} from "react-icons/si";
import { VscAzure } from "react-icons/vsc";

export type BlockIcon = { Icon: IconType; color: string };

// Brand icon + color per provider category (category = provider package name).
const CATEGORY_ICONS: Record<string, BlockIcon> = {
  Core: { Icon: FiStar, color: "#60a5fa" },
  google: { Icon: SiGoogle, color: "#ea4335" },
  amazon: { Icon: FaAws, color: "#ff9900" },
  "microsoft azure": { Icon: VscAzure, color: "#0078d4" },
  "cncf kubernetes": { Icon: SiKubernetes, color: "#326ce5" },
  docker: { Icon: FaDocker, color: "#2496ed" },
  slack: { Icon: FiShare2, color: "#e01e5a" },
  redis: { Icon: SiRedis, color: "#dc382d" },
  snowflake: { Icon: SiSnowflake, color: "#29b5e8" },
  celery: { Icon: SiCelery, color: "#a9cc54" },
  "common sql": { Icon: FaDatabase, color: "#22d3ee" },
  smtp: { Icon: FiMail, color: "#f472b6" },
  http: { Icon: FiGlobe, color: "#38bdf8" },
  grpc: { Icon: FiShare2, color: "#38bdf8" },
  ssh: { Icon: FiTerminal, color: "#34d399" },
  sftp: { Icon: FiRepeat, color: "#94a3b8" },
  ftp: { Icon: FiRepeat, color: "#94a3b8" },
  "common io": { Icon: FiFolder, color: "#94a3b8" },
  standard: { Icon: FiPackage, color: "#94a3b8" },
};

export const categoryIcon = (category: string): BlockIcon =>
  CATEGORY_ICONS[category] ?? { Icon: FiPackage, color: "#94a3b8" };

// Type-based icon for a single block; falls back to the category brand icon.
export const blockIcon = (
  blockId: string,
  label: string,
  category: string,
  opaque: boolean,
): BlockIcon => {
  if (opaque) {
    return { Icon: FiCode, color: "#94a3b8" };
  }
  const lower = label.toLowerCase();
  if (blockId === "bash" || lower.includes("bash") || lower.includes("ssh")) {
    return { Icon: FiTerminal, color: "#34d399" };
  }
  if (blockId === "python" || lower.includes("python")) {
    return { Icon: SiPython, color: "#60a5fa" };
  }
  if (blockId === "trigger_dag" || lower.includes("trigger")) {
    return { Icon: FiZap, color: "#fbbf24" };
  }
  if (blockId === "empty") {
    return { Icon: FiCircle, color: "#94a3b8" };
  }
  if (lower.includes("sql") || lower.includes("database")) {
    return { Icon: FaDatabase, color: "#22d3ee" };
  }
  if (lower.endsWith("sensor")) {
    return { Icon: FiEye, color: "#c084fc" };
  }
  if (lower.includes("branch")) {
    return { Icon: FiGitBranch, color: "#fb923c" };
  }
  if (lower.includes("email") || lower.includes("smtp")) {
    return { Icon: FiMail, color: "#f472b6" };
  }
  if (lower.includes("http")) {
    return { Icon: FiGlobe, color: "#38bdf8" };
  }
  if (lower.includes("docker")) {
    return { Icon: FaDocker, color: "#2496ed" };
  }
  if (lower.includes("kubernetes") || lower.includes("pod")) {
    return { Icon: SiKubernetes, color: "#326ce5" };
  }
  if (lower.includes("file") || lower.includes("transfer")) {
    return { Icon: FiFile, color: "#94a3b8" };
  }
  const brand = CATEGORY_ICONS[category];
  if (brand) {
    return brand;
  }
  return { Icon: FiBox, color: "#94a3b8" };
};
