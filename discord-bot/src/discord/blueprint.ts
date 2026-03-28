export const ROLE_BLUEPRINT = [
  "Owner",
  "Lead Admin",
  "Developer",
  "Moderator",
  "Tester",
  "Verified",
  "Community"
] as const;

export const STAFF_ROLE_NAMES = ["Owner", "Lead Admin", "Developer", "Moderator"] as const;

export const CATEGORY_BLUEPRINT = [
  {
    name: "Start Here",
    channels: ["rules", "announcements", "server-status", "faq", "verify"]
  },
  {
    name: "Community",
    channels: ["general", "suggestions", "media", "bug-reports"]
  },
  {
    name: "Playtesting",
    channels: ["playtest-news", "playtest-chat", "support-tickets"]
  },
  {
    name: "Development",
    channels: ["github-feed", "dev-updates", "roadmap", "contributors"]
  },
  {
    name: "Staff",
    channels: ["staff-chat", "mod-log", "ops-console", "incident-room", "ticket-review"]
  }
] as const;

export const SEEDED_MESSAGES: Record<string, string[]> = {
  rules: [
    "# OpenNXT Rules\nBe respectful, keep discussion on-topic, and do not share malicious files, exploits, or leaked content.",
    "Breaking the rules can result in content removal, mute, or ban. Staff decisions belong in support channels, not public arguments."
  ],
  faq: [
    "# OpenNXT FAQ\n- Development updates land in #dev-updates and #github-feed.\n- Playtest support starts with `/ticket create`.\n- Verification starts with `/verify start`."
  ],
  verify: [
    "# Verification\nRun `/verify start` to unlock the community and playtesting areas."
  ],
  "support-tickets": [
    "# Support Tickets\nUse `/ticket create` with a short subject to open a private help channel with staff."
  ],
  "server-status": [
    "# Server Status\nThis channel receives automated setup and runtime updates from the OpenNXT ops bot."
  ],
  announcements: [
    "# Announcements\nMajor milestones, releases, and important server notices appear here."
  ]
};
