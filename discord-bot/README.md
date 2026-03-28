# OpenNXT Discord Bot

TypeScript service that handles Discord community scaffolding, moderation helpers, GitHub progress feeds, and safe local OpenNXT host operations.

## Features

- `/community scaffold` to create the baseline OpenNXT Discord structure
- verification, support ticket, and anti-spam workflows
- GitHub webhook intake for `vgcman16/OpenNXT`
- approval-gated local ops for build, setup, start, stop, restart, status, and logs

## Setup

1. Copy `.env.example` to `.env` and fill in the required values.
2. From this directory run `npm.cmd install`.
3. Run `npm.cmd run build`.
4. Start the bot with `npm.cmd start` or `npm.cmd run dev`.

## Notes

- Use `npm.cmd` on this Windows host because `npm.ps1` is blocked by PowerShell execution policy.
- The bot assumes it runs on the same machine as the OpenNXT checkout.
- Host-control commands are restricted to allowlisted users with a configured staff role or one of the scaffolded staff roles.
