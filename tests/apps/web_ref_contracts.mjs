// Scenarios for the entity-code contract both markdown zones share
// (`web/src/components/markdown/shared/contracts.ts`), executed under Node against the real file —
// see `test_web_ref_contracts.py`. Run as `node … web_ref_contracts.mjs <scenario>`.

import assert from 'node:assert/strict'

const contracts = await import(new URL('../../web/src/components/markdown/shared/contracts.ts', import.meta.url).href)
const { REF_TYPES, REF_CODE, WHOLE_CODE_SPAN, canonicalCode, parseRefCode, refIsFile, refIsMissing, refPath } = contracts

const HASH = '0123456789'

/** Every code the scanner finds in a text, as `[type, hash]`. */
function scan(text) {
  REF_CODE.lastIndex = 0
  return [...text.matchAll(REF_CODE)].map((match) => [match[1].toUpperCase(), match[2]])
}

const scenarios = {
  every_backend_type_is_in_the_vocabulary() {
    assert.deepEqual(
      [...REF_TYPES].sort(),
      ['CODEX', 'FILE', 'IMAGE', 'JOURNAL', 'NOTE', 'STAGE', 'TASK', 'TASKGROUP', 'WORKSPACE'],
    )
  },

  each_type_is_read_as_itself() {
    for (const type of REF_TYPES) {
      assert.deepEqual(scan(`see ${type}@${HASH}.`), [[type, HASH]], type)
    }
  },

  a_group_code_is_a_group_not_a_task() {
    assert.deepEqual(scan(`TASKGROUP@${HASH}`), [['TASKGROUP', HASH]])
  },

  several_codes_in_one_text_are_all_found() {
    assert.deepEqual(scan(`TASK@${HASH}, STAGE@${HASH} и CODEX@${HASH}`), [
      ['TASK', HASH],
      ['STAGE', HASH],
      ['CODEX', HASH],
    ])
  },

  a_lower_case_code_still_resolves_and_folds_to_upper() {
    assert.deepEqual(scan(`task@abcdef0123`), [['TASK', 'abcdef0123']])
    assert.equal(parseRefCode('  task@abcdef0123 '), 'TASK@ABCDEF0123')
    assert.equal(canonicalCode('note@abcdef0123'), 'NOTE@ABCDEF0123')
  },

  a_longer_or_shorter_hash_is_plain_text() {
    assert.deepEqual(scan(`TASK@${HASH}a`), [], 'eleven hex characters')
    assert.deepEqual(scan(`TASK@012345678`), [], 'nine hex characters')
    assert.equal(parseRefCode(`TASK@${HASH}a`), null)
  },

  an_unknown_type_is_plain_text() {
    assert.deepEqual(scan(`GROUP@${HASH} RESEARCH@${HASH}`), [])
    assert.equal(parseRefCode(`GROUP@${HASH}`), null)
  },

  // Pinned, not desired: the scanner has no left word boundary, so a code glued to a longer word
  // still becomes a pill of the word's tail. Flips when a boundary is added to REF_CODE.
  a_code_glued_to_a_word_is_read_from_its_tail() {
    assert.deepEqual(scan(`SUBTASK@${HASH}`), [['TASK', HASH]])
  },

  a_whole_span_is_exactly_one_code() {
    assert.ok(WHOLE_CODE_SPAN.test(`STAGE@${HASH}`))
    assert.ok(!WHOLE_CODE_SPAN.test(`STAGE@${HASH} и`))
    assert.ok(!WHOLE_CODE_SPAN.test(`TASK@${HASH} TASK@${HASH}`))
  },

  the_address_the_code_alone_can_tell() {
    assert.equal(refPath(`TASK@${HASH}`), `/tasks/task/TASK@${HASH}`)
    assert.equal(refPath(`TASKGROUP@${HASH}`), '/tasks/groups')
    assert.equal(refPath(`WORKSPACE@${HASH}`), '/workspaces')
    assert.equal(refPath(`CODEX@${HASH}`), `/codex/materials/CODEX@${HASH}`)
    for (const type of ['STAGE', 'JOURNAL', 'NOTE', 'FILE', 'IMAGE']) {
      assert.equal(refPath(`${type}@${HASH}`), null, `${type} waits for its preview`)
    }
  },

  only_a_file_opens_outside_the_app() {
    assert.ok(refIsFile(`FILE@${HASH}`))
    assert.ok(refIsFile(`IMAGE@${HASH}`))
    assert.ok(refIsFile(`image@${HASH}`), 'a lower-case prefix is still a file')
    for (const type of ['TASKGROUP', 'TASK', 'STAGE', 'JOURNAL', 'NOTE', 'WORKSPACE', 'CODEX']) {
      assert.ok(!refIsFile(`${type}@${HASH}`), type)
    }
  },

  a_file_gone_from_the_storage_is_red_but_only_not_found_of_the_rest() {
    for (const miss of ['not_found', 'deleted']) {
      assert.ok(refIsMissing(`FILE@${HASH}`, miss), `FILE ${miss}`)
      assert.ok(refIsMissing(`IMAGE@${HASH}`, miss), `IMAGE ${miss}`)
    }
    // A file is shown wherever it was brought in; the workspace is not a verdict about it.
    assert.ok(!refIsMissing(`FILE@${HASH}`, 'foreign_scope'), 'FILE foreign_scope')
    assert.ok(!refIsMissing(`FILE@${HASH}`, 'failed'), 'a failed request is not a verdict')
    assert.ok(!refIsMissing(`FILE@${HASH}`, undefined), 'found or pending')
    assert.ok(refIsMissing(`TASK@${HASH}`, 'not_found'))
    assert.ok(!refIsMissing(`TASK@${HASH}`, 'deleted'))
    assert.ok(!refIsMissing(`CODEX@${HASH}`, 'foreign_scope'))
  },
}

const name = process.argv[2]
if (name === '--list') {
  console.log(JSON.stringify(Object.keys(scenarios)))
} else {
  assert.ok(name in scenarios, `unknown scenario ${name}`)
  await scenarios[name]()
  console.log('ok')
}
