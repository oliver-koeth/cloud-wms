import JsBarcode from 'jsbarcode'
import type { LocationRow } from '../types'

export interface LocationLabel {
  name: string
  title: string
  barcode: string
}

/** Enabled bins with a barcode at or below `root` in the Warehouse tree. */
export function labelsFor(rows: LocationRow[], root: LocationRow): LocationLabel[] {
  return rows
    .filter((row) => !row.is_group && !row.disabled && row.barcode && row.lft >= root.lft && row.rgt <= root.rgt)
    .map((row) => ({ name: row.name, title: row.warehouse_name, barcode: row.barcode as string }))
}

const escapeHtml = (value: string) =>
  value.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char] as string)

/** A printable A4 sheet of 70 × 37 mm labels; `svg` renders one barcode. */
export function labelSheet(labels: LocationLabel[], svg: (value: string) => string): string {
  const cells = labels
    .map((label) => `<div class="label"><strong>${escapeHtml(label.title)}</strong>${svg(label.barcode)}</div>`)
    .join('')
  return `<!doctype html><html><head><meta charset="utf-8"><title>Location labels</title><style>
@page { size: A4; margin: 8mm; }
body { margin: 0; font-family: system-ui, sans-serif; }
.sheet { display: grid; grid-template-columns: repeat(3, 70mm); grid-auto-rows: 37mm; }
.label { box-sizing: border-box; padding: 3mm; border: 1px dashed #bbb; display: flex; flex-direction: column; align-items: center; justify-content: center; overflow: hidden; break-inside: avoid; }
.label strong { font-size: 12pt; margin-bottom: 1mm; }
.label svg { max-width: 100%; height: auto; }
@media print { .label { border-color: transparent; } }
</style></head><body><div class="sheet">${cells}</div></body></html>`
}

export function barcodeSvg(value: string): string {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  JsBarcode(svg, value, { format: 'CODE128', height: 48, width: 1.6, margin: 0, fontSize: 13 })
  return svg.outerHTML
}

export function printLabels(labels: LocationLabel[]) {
  if (!labels.length) throw new Error('No enabled bins with a barcode in this selection.')
  // Render first so an unprintable barcode fails before a window opens.
  const html = labelSheet(labels, barcodeSvg)
  const sheet = window.open('', '_blank')
  if (!sheet) throw new Error('Allow pop-ups for this site to print labels.')
  sheet.document.write(html)
  sheet.document.close()
  sheet.focus()
  sheet.print()
}
