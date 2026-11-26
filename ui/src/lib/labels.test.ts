import { describe, expect, it } from 'vitest'
import { labelSheet, labelsFor } from './labels'
import type { LocationRow } from '../types'

const row = (name: string, lft: number, rgt: number, extra: Partial<LocationRow> = {}): LocationRow => ({
  name,
  warehouse_name: name,
  parent_warehouse: null,
  is_group: 0,
  disabled: 0,
  company: 'Demo Co',
  barcode: `LOC-${name}`,
  depth: 0,
  lft,
  rgt,
  on_hand: 0,
  modified: '',
  ...extra,
})

describe('location labels', () => {
  const zone = row('Zone A', 1, 8, { is_group: 1, barcode: null })
  const rows = [
    zone,
    row('A-01', 2, 3),
    row('A-02', 4, 5, { disabled: 1 }),
    row('A-03', 6, 7, { barcode: null }),
    row('B-01', 9, 10),
  ]

  it('prints enabled bins with a barcode inside the selected group only', () => {
    expect(labelsFor(rows, zone)).toEqual([{ name: 'A-01', title: 'A-01', barcode: 'LOC-A-01' }])
    expect(labelsFor(rows, rows[4]).map((label) => label.name)).toEqual(['B-01'])
  })

  it('escapes location names in the printed sheet', () => {
    const html = labelSheet([{ name: 'x', title: '<b>A&B</b>', barcode: 'LOC-1' }], (value) => `<svg data-value="${value}"></svg>`)

    expect(html).toContain('<strong>&lt;b&gt;A&amp;B&lt;/b&gt;</strong><svg data-value="LOC-1"></svg>')
  })
})
