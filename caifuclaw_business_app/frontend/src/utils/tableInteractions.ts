const INTERACTIVE_TABLE_TARGET_SELECTOR = [
  'button',
  'a',
  'input',
  'textarea',
  'select',
  '[role="button"]',
  '.ant-select',
  '.ant-checkbox-wrapper'
].join(', ')

export function shouldIgnoreTableRowDoubleClick(target: EventTarget | null) {
  const element = target as (EventTarget & { closest?: (selector: string) => Element | null }) | null
  return Boolean(element?.closest?.(INTERACTIVE_TABLE_TARGET_SELECTOR))
}
