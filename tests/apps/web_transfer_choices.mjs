// Scenarios for the choices of an import's conflicts, executed under Node against the real file —
// see `test_web_transfer_choices.py`. Run as `node … web_transfer_choices.mjs <scenario>`; a failed
// `assert` exits non-zero with the reason on stderr.
//
// The rules are the server's (`core_transfer.conflicts.resolve_choices`): a dependent «update» needs
// what it requires, a single-option conflict is chosen by itself, nothing is chosen by default.

import assert from 'node:assert/strict'

const WEB_SRC = new URL('../../web/src/', import.meta.url)

const { allChosen, canUpdate, carriedChoices, choose, chooseAll, presetChoices } = await import(
  new URL('components/transfer/types.ts', WEB_SRC).href
)

const side = { updated_at: null, created_at: null, size: null }

function conflict(id, options = ['update', 'replace'], requires = null) {
  return { id, entity: 'task', title: id, local: {}, options, reason: '', reason_params: {}, requires,
           dates: { local: side, archive: side } }
}

const TASK = conflict('TASK@A')
const NOTE = conflict('NOTE@B', ['update', 'replace'], { id: 'TASK@A', choice: 'update' })
const FOREIGN = conflict('NOTE@C', ['replace'])

const scenarios = {
  // Nothing is chosen for the person; a conflict with one option has it already.
  nothing_by_default: () => {
    const preset = presetChoices([TASK, NOTE, FOREIGN])
    assert.deepEqual(preset, { 'NOTE@C': 'replace' })
    assert.equal(allChosen([TASK, NOTE, FOREIGN], preset), false)
  },
  // Replacing the task takes its note's «update» away and falls back to «replace».
  replace_cascades: () => {
    let choices = choose([TASK, NOTE], {}, 'TASK@A', 'update')
    choices = choose([TASK, NOTE], choices, 'NOTE@B', 'update')
    choices = choose([TASK, NOTE], choices, 'TASK@A', 'replace')
    assert.deepEqual(choices, { 'TASK@A': 'replace', 'NOTE@B': 'replace' })
    assert.equal(canUpdate(NOTE, choices), false)
  },
  // Before the task is chosen the note's «update» is still open.
  update_open_until_decided: () => {
    assert.equal(canUpdate(NOTE, {}), true)
    assert.equal(canUpdate(FOREIGN, {}), false)
  },
  // «Update all» updates what can be updated and replaces the rest.
  update_all: () => {
    const choices = chooseAll([TASK, NOTE, FOREIGN], 'update')
    assert.deepEqual(choices, { 'TASK@A': 'update', 'NOTE@B': 'update', 'NOTE@C': 'replace' })
    assert.equal(allChosen([TASK, NOTE, FOREIGN], choices), true)
  },
  replace_all: () => {
    assert.deepEqual(chooseAll([TASK, NOTE, FOREIGN], 'replace'), {
      'TASK@A': 'replace', 'NOTE@B': 'replace', 'NOTE@C': 'replace',
    })
  },
  // A new plan keeps the choices that still fit and drops the ones it no longer offers.
  carried_over: () => {
    const narrowed = conflict('TASK@A', ['replace'])
    const carried = carriedChoices([narrowed, NOTE], { 'TASK@A': 'update', 'NOTE@B': 'update' })
    assert.deepEqual(carried, { 'TASK@A': 'replace', 'NOTE@B': 'replace' })
    const kept = carriedChoices([TASK, NOTE], { 'TASK@A': 'update', 'NOTE@B': 'update', 'GONE@X': 'update' })
    assert.deepEqual(kept, { 'TASK@A': 'update', 'NOTE@B': 'update' })
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
