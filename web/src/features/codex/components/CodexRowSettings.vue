<script setup lang="ts">
// A codex's settings in the current workspace — the middle of its `EntityRowList` row, filled
// through the `columns` slot: available (eye) | the agent writes (lock). Each control is a switch
// with an icon that shows its state, in a column of fixed width, so the switches of every row
// stand one under another.
import { useI18n } from 'vue-i18n'
import { IconEye, IconEyeOff, IconLock, IconLockOpen } from '@tabler/icons-vue'

import HelpHint from '@/components/HelpHint.vue'

import type { CodexListItem } from '../stores/codex-list.store'

defineProps<{ item: CodexListItem; canMount: boolean }>()

const emit = defineEmits<{
  mount: [on: boolean]
  lock: [agentCanEdit: boolean]
}>()

const { t } = useI18n()
</script>

<template>
  <VDivider vertical class="codex-settings__divider" />

  <!-- Available in the current workspace — the agent reads its materials there. The name and its
       "?" on top; below, the eye that says it at a glance and the switch that changes it. The "?"
       stays outside the label: a click on it must explain, not toggle. `.stop` — a switch must
       not also open the codex. -->
  <div class="codex-settings__toggle" :class="{ 'codex-settings__toggle--on': item.mounted }" @click.stop>
    <div class="codex-settings__head">
      <span class="codex-settings__label">{{ t('codex.list.mounted') }}</span>
      <HelpHint :text="t('codex.list.mounted_hint')" :tabbable="false" />
    </div>
    <label class="codex-settings__control">
      <IconEye v-if="item.mounted" :size="16" :stroke-width="1.6" />
      <IconEyeOff v-else :size="16" :stroke-width="1.6" />
      <VSwitch
        :model-value="item.mounted"
        :disabled="!canMount || Boolean(item.deleted_at)"
        :aria-label="t('codex.list.mounted')"
        color="primary"
        density="compact"
        hide-details
        inset
        class="codex-settings__switch"
        @update:model-value="(on) => emit('mount', Boolean(on))"
      />
    </label>
  </div>

  <VDivider vertical class="codex-settings__divider" />

  <!-- The agent's right to write here — a property of the mount, so off while not mounted. -->
  <div
    class="codex-settings__toggle"
    :class="{ 'codex-settings__toggle--on': item.mounted && item.agentCanEdit }"
    @click.stop
  >
    <div class="codex-settings__head">
      <span class="codex-settings__label">{{ t('codex.list.agent_writes') }}</span>
      <HelpHint :text="t('codex.list.agent_writes_hint')" :tabbable="false" />
    </div>
    <label class="codex-settings__control">
      <IconLockOpen v-if="item.mounted && item.agentCanEdit" :size="16" :stroke-width="1.6" />
      <IconLock v-else :size="16" :stroke-width="1.6" />
      <VSwitch
        :model-value="item.mounted && item.agentCanEdit"
        :disabled="!item.mounted || Boolean(item.deleted_at)"
        :aria-label="t('codex.list.agent_writes')"
        color="primary"
        density="compact"
        hide-details
        inset
        class="codex-settings__switch"
        @update:model-value="(on) => emit('lock', Boolean(on))"
      />
    </label>
  </div>

  <!-- The settings end here; the row's buttons follow. -->
  <VDivider vertical class="codex-settings__divider" />
</template>

<style scoped>
/* The `EntityRowList` divider, the same on every page: it spans the text block's height, not the
   row's. Repeated here because slot content does not get the list's scoped styles. */
.codex-settings__divider {
  align-self: center;
  height: 28px;
  opacity: 1;
  border-color: var(--border);
}

/* A control column: the name with its "?" on top, the state icon and the switch below. A fixed
   width, so the switches of neighbouring rows stand one under another — the widest name with its
   "?" and no more, so no column carries empty space before the next divider. The icon is quiet
   while off and takes the accent when on; the name stays readable either way. */
.codex-settings__toggle {
  flex: none;
  width: 128px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.codex-settings__head {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  color: var(--text-muted);
}

.codex-settings__label {
  min-width: 0;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* The height is the track's and a little air, not the switch's 40px box: that box is mostly empty
   above and below a 20px track, and it pushed the switch away from its name. The box still
   overflows, centred, so its hit area stays whole. */
.codex-settings__control {
  display: flex;
  align-items: center;
  height: 24px;
  gap: 8px;
  color: var(--text-faint);
  cursor: pointer;
}

.codex-settings__toggle--on .codex-settings__control { color: var(--accent); }

.codex-settings__switch { flex: none; }
</style>
