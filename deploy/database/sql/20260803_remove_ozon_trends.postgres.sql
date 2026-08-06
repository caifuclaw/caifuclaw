BEGIN;

DELETE FROM role_menu_permissions
WHERE menu_code = 'ozon-trends';

DELETE FROM user_menu_permissions
WHERE menu_code = 'ozon-trends';

DELETE FROM user_table_preferences
WHERE lower(table_key) LIKE '%ozon%trend%';

DELETE FROM scheduled_tasks
WHERE lower(COALESCE(task_type, '')) LIKE '%ozon%trend%'
   OR lower(COALESCE(name, '')) LIKE '%ozon%trend%'
   OR lower(COALESCE(remark, '')) LIKE '%ozon%trend%';

DROP TABLE IF EXISTS ozon_trend_snapshots CASCADE;
DROP TABLE IF EXISTS ozon_trend_runs CASCADE;
DROP TABLE IF EXISTS ozon_trend_categories CASCADE;

COMMIT;
