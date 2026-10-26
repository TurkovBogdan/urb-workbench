// Scenarios for the order a files section sends when only some of the holder's files are shown,
// executed under Node against the real file — see `test_web_file_order.py`. Run as
// `node … web_file_order.mjs <scenario>`; a failed `assert` exits non-zero with the reason on stderr.
//
// The holder puts the codes it is sent on top and the rest below, so what is checked is that an
// unseen file keeps its place among the shown ones whatever they do.

import assert from 'node:assert/strict'

const WEB_SRC = new URL('../../web/src/', import.meta.url)

const { placeShown } = await import(new URL('components/files/order.ts', WEB_SRC).href)

const scenarios = {
  // Nothing hidden: the new order is the order sent.
  all_shown: () => {
    assert.deepEqual(placeShown(['A', 'B', 'C'], ['C', 'A', 'B']), ['C', 'A', 'B'])
  },
  // The case met in the browser: the last shown card dragged first, a hidden file second and last.
  hidden_keep_their_places: () => {
    const all = ['S', 'n1', 'W', 'L', 'D', 'a', 'b', 'r', 'n2']
    const shown = ['r', 'S', 'W', 'L', 'D', 'a', 'b']
    assert.deepEqual(placeShown(all, shown), ['r', 'n1', 'S', 'W', 'L', 'D', 'a', 'b', 'n2'])
  },
  // A hidden file at the very top stays on top when the shown ones swap.
  hidden_first: () => {
    assert.deepEqual(placeShown(['h', 'A', 'B'], ['B', 'A']), ['h', 'B', 'A'])
  },
  // Every file hidden but one: the one stays where it was.
  one_shown: () => {
    assert.deepEqual(placeShown(['h1', 'A', 'h2'], ['A']), ['h1', 'A', 'h2'])
  },
  // Every code goes out once: none lost, none doubled.
  each_code_once: () => {
    const all = ['h1', 'A', 'B', 'h2', 'C', 'h3']
    const out = placeShown(all, ['C', 'B', 'A'])
    assert.deepEqual([...out].sort(), [...all].sort())
    assert.deepEqual(out, ['h1', 'C', 'B', 'h2', 'A', 'h3'])
  },
}

const [name] = process.argv.slice(2)
if (name === '--list') {
  console.log(JSON.stringify(Object.keys(scenarios)))
} else {
  const run = scenarios[name]
  if (!run) throw new Error(`unknown scenario: ${name}`)
  await run()
  console.log('ok')
}
