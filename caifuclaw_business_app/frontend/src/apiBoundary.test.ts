import { readdirSync, readFileSync } from 'node:fs'
import { extname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const srcRoot = fileURLToPath(new URL('.', import.meta.url))
const allowedApiRoot = join(srcRoot, 'api')
const sourceExtensions = new Set(['.ts', '.tsx', '.js', '.jsx'])
const directBusinessRequest = /(?:axios\s*\.|\bhttp\.(?:get|post|put|patch|delete)\s*\(|fetch\s*\(\s*[`'"]\/api\b)/

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return sourceFiles(path)
    if (!sourceExtensions.has(extname(entry.name)) || entry.name.includes('.test.') || entry.name.includes('.spec.')) {
      return []
    }
    return [path]
  })
}

describe('frontend API boundary', () => {
  it('keeps business HTTP requests inside src/api', () => {
    const violations = sourceFiles(srcRoot)
      .filter((path) => !path.startsWith(allowedApiRoot))
      .filter((path) => directBusinessRequest.test(readFileSync(path, 'utf8')))
      .map((path) => relative(srcRoot, path).replaceAll('\\', '/'))

    expect(violations).toEqual([])
  })
})
