export interface LinuxCapability {
  id: string;
  label: string;
  consequence: "read" | "mutating";
  available: boolean;
}

export interface LinuxServiceIntent {
  id: string;
  capability: string;
  scope: string;
  requestedBy: "operator" | "phivessel" | "system";
}

export interface LinuxServiceReceipt {
  id: string;
  intentId: string;
  adapter: "mock-zero-privilege";
  status: "blocked";
  executionAuthority: false;
  effectPerformed: false;
  reason: string;
}

export interface LinuxServiceAdapter {
  readonly operationalAuthority: false;
  readonly actionAuthority: false;
  readonly executionAuthority: false;
  listCapabilities(): readonly LinuxCapability[];
  request(intent: LinuxServiceIntent): Promise<LinuxServiceReceipt>;
}

const capabilities: readonly LinuxCapability[] = [
  { id: "system.power", label: "Power controls", consequence: "mutating", available: false },
  { id: "network.configure", label: "Network configuration", consequence: "mutating", available: false },
  { id: "package.manage", label: "Package management", consequence: "mutating", available: false },
  { id: "service.control", label: "Service control", consequence: "mutating", available: false },
  { id: "system.inspect", label: "System inspection", consequence: "read", available: true },
];

export function createZeroPrivilegeLinuxAdapter(): LinuxServiceAdapter {
  return {
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,

    listCapabilities() {
      return capabilities;
    },

    async request(intent) {
      return {
        id: `mock-receipt:${intent.id}`,
        intentId: intent.id,
        adapter: "mock-zero-privilege",
        status: "blocked",
        executionAuthority: false,
        effectPerformed: false,
        reason:
          "PhiShell v0.2 records the requested intent but this adapter cannot perform Linux effects.",
      };
    },
  };
}

export const linuxServiceAdapter = createZeroPrivilegeLinuxAdapter();
