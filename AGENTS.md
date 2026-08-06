# AGENTS.md instructions for D:\claw_project\caifuclaw_erp

## Workflow

After frontend or backend code changes are complete, run these steps in order:

1. Build: `.\build_caifuclaw_erp.cmd`
2. Restart frontend and backend services: `.\start_caifuclaw_erp.cmd -Restart`

## Service Start/Restart

To start or restart the frontend and backend services, run:

```powershell
.\start_caifuclaw_erp.cmd -Restart
```

## Quick Build

To quickly build/check the frontend and backend, run:

```powershell
.\build_caifuclaw_erp.cmd
```

The script runs `npm run build` for both frontend projects and performs Python backend syntax compile checks. By default, frontend output is written to a temporary directory and cleaned up automatically so project `dist` directories are not modified.

To write frontend build artifacts into the project `dist` directories, run:

```powershell
.\build_caifuclaw_erp.cmd -WriteFrontendDist
```
