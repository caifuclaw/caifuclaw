# Frontend React Migration Notes

Last updated: 2026-05-22

## Decisions

- Old Vue frontend is backed up at `caifuclaw_business_app/frontend_vue_backup_20260522`.
- New React frontend stays at `caifuclaw_business_app/frontend`.
- Stack: React + Vite + Ant Design React + `@ant-design/pro-components` + Zustand.
- Dark mode only changes the left menu.
- Keep the Vue backup until React testing is accepted.

## Current State

- All previous placeholder business pages have been replaced.
- The remaining `Placeholder` page is only used for the 404 route.
- Global menu labels, order status labels, and layout user-menu text were repaired from the old mojibake state.

## Migrated Pages

- Login
- Dashboard
- Orders, including filters, status tabs, batch actions, export, manual sync, and detail drawer
- Print preview
- Order summary
- Purchase orders
- Purchase details
- Scan outbound, including scanner focus lock, queue processing, and audio feedback
- Outbound scan records
- Inventory
- Products
- Shops, including API-key shops and OAuth authorization flow
- System settings, including print settings, scheduled tasks, email SMTP, task runs, run detail, export PDFs, and failed reprint
- Users and roles
- Sync API logs

## Verification

Run from `caifuclaw_business_app/frontend`:

```powershell
npm run typecheck
npm run build
```

Both commands passed on 2026-05-22.

Build notes:

- Vite reports large chunks for Ant Design and the PDF worker. This is a warning, not a build failure.
- `vendor-pdf` is currently generated as an empty chunk because the actual worker is emitted separately.

## Suggested Next Checks

- Login against the real backend and smoke-test each menu route.
- Verify platform-specific shop authorization with real credentials.
- Verify scheduled task run, export PDF, and failed reprint against backend services.
- If bundle size becomes a deployment concern, split heavy pages with route-level lazy imports.
