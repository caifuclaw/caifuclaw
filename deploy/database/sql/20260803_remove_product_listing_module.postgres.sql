-- Company: 深圳智柠网络科技有限公司
-- Author: mohsen liang

BEGIN;

DELETE FROM role_menu_permissions
WHERE menu_code IN (
    'source-table-templates',
    'skills-settings',
    'product-categories',
    'listing-image-rules',
    'data-collection',
    'listing-tasks'
);

DELETE FROM user_menu_permissions
WHERE menu_code IN (
    'source-table-templates',
    'skills-settings',
    'product-categories',
    'listing-image-rules',
    'data-collection',
    'listing-tasks'
);

DELETE FROM user_table_preferences
WHERE table_key LIKE 'listing-%'
   OR table_key LIKE 'product-categor%'
   OR table_key LIKE 'source-table-template%'
   OR table_key LIKE 'skills-setting%'
   OR table_key LIKE 'data-collection%';

DELETE FROM scheduled_tasks
WHERE lower(COALESCE(task_type, '')) LIKE '%listing%'
   OR lower(COALESCE(task_type, '')) LIKE '%data_collection%'
   OR lower(COALESCE(task_type, '')) LIKE '%platform_category%'
   OR lower(COALESCE(name, '')) LIKE '%listing%'
   OR lower(COALESCE(remark, '')) LIKE '%listing%';

ALTER TABLE IF EXISTS products
    DROP COLUMN IF EXISTS category_detail_id,
    DROP COLUMN IF EXISTS category_params,
    DROP COLUMN IF EXISTS created_from_listing;

ALTER TABLE IF EXISTS platform_product_pricing_rules
    DROP COLUMN IF EXISTS category_detail_id;

DROP TABLE IF EXISTS listing_image_variants CASCADE;
DROP TABLE IF EXISTS listing_upload_attempts CASCADE;
DROP TABLE IF EXISTS listing_task_events CASCADE;
DROP TABLE IF EXISTS listing_upload_rows CASCADE;
DROP TABLE IF EXISTS listing_upload_batches CASCADE;
DROP TABLE IF EXISTS listing_source_rows CASCADE;
DROP TABLE IF EXISTS listing_tasks CASCADE;
DROP TABLE IF EXISTS listing_image_rules CASCADE;
DROP TABLE IF EXISTS listing_api_field_mappings CASCADE;

DROP TABLE IF EXISTS product_category_platform_mappings CASCADE;
DROP TABLE IF EXISTS product_category_templates CASCADE;
DROP TABLE IF EXISTS product_category_details CASCADE;
DROP TABLE IF EXISTS product_category_groups CASCADE;

DROP TABLE IF EXISTS platform_attribute_dictionary_values CASCADE;
DROP TABLE IF EXISTS platform_category_attribute_schemas CASCADE;
DROP TABLE IF EXISTS platform_category_caches CASCADE;

DROP TABLE IF EXISTS source_table_template_fields CASCADE;
DROP TABLE IF EXISTS source_table_template_save_operations CASCADE;
DROP TABLE IF EXISTS source_table_template_versions CASCADE;
DROP TABLE IF EXISTS source_table_templates CASCADE;
DROP TABLE IF EXISTS source_table_common_field_versions CASCADE;
DROP TABLE IF EXISTS source_table_common_fields CASCADE;
DROP TABLE IF EXISTS skills_settings CASCADE;

COMMIT;
