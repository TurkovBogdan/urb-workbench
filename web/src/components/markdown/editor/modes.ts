// Что редактор умеет в этом месте применения.
//
// Поля, в которые пишут, разные по природе. У тела задачи есть заголовки, списки и таблицы; у
// названия этапа — только текст с выделением. Один редактор на оба случая работает лишь при
// одном условии: **редактор не должен уметь выражать больше, чем принимает хранилище и чем
// ждёт читатель**. Набор возможностей поэтому не оформление, а часть контракта поля.
//
// Состав действует сразу на четыре слоя, и в этом весь смысл держать его одним списком:
//
//   1. схема — выключенного узла в документе не существует, а не «он есть, но кнопки нет»;
//   2. разбор — markdown на входе приводится к разрешённому (bridge/restrict.ts), поэтому
//      вставка чужого текста не может протащить конструкцию мимо схемы;
//   3. хром — слэш-меню и панель показывают ровно то, что сработает;
//   4. печать — печатать нечего, чего нет в документе.
//
// Без пункта 2 остальные бесполезны: пользователь вставит из буфера заголовок, схема его
// отвергнет, и ProseMirror откажет ВСЕМУ документу разом.

/** Блочные конструкции. Абзац в списке не значится: он есть всегда и выключению не подлежит. */
export type BlockFeature = 'heading' | 'list' | 'quote' | 'codeBlock' | 'divider' | 'table'

/** Строчные: метки текста и пилюля-ссылка на сущность. */
export type InlineFeature = 'bold' | 'italic' | 'strike' | 'code' | 'link' | 'entityRef'

/** Хром: ручка перетаскивания блоков и меню по слэшу. */
export type ChromeFeature = 'handle' | 'slash'

export type Feature = BlockFeature | InlineFeature | ChromeFeature

export const BLOCK_FEATURES: readonly BlockFeature[] = [
  'heading', 'list', 'quote', 'codeBlock', 'divider', 'table',
]

export const INLINE_FEATURES: readonly InlineFeature[] = [
  'bold', 'italic', 'strike', 'code', 'link', 'entityRef',
]

/** Готовые наборы. Имя режима — то, что ставится в разметке; список — то, что он значит. */
export type EditorMode = 'full' | 'simple'

const FULL: readonly Feature[] = [...BLOCK_FEATURES, ...INLINE_FEATURES, 'handle', 'slash']

// Простой режим: абзац, жирный, курсив — и больше ничего. Блочных конструкций нет ни одной,
// поэтому нет и хрома: перетаскивать нечего, а меню по слэшу открывалось бы пустым. Слэш в
// таком поле снова становится обычным символом.
const SIMPLE: readonly Feature[] = ['bold', 'italic']

export const MODES: Record<EditorMode, readonly Feature[]> = {
  full: FULL,
  simple: SIMPLE,
}

export type FeatureSet = ReadonlySet<Feature>

/**
 * Разрешить режим и точечные поправки к нему в один набор.
 *
 * `features` заменяет список режима целиком, а не дополняет его: «режим плюс кое-что» читается
 * двусмысленно ровно там, где важна однозначность, — при ответе на вопрос «что это поле
 * принимает».
 */
export function resolveFeatures(mode: EditorMode = 'full', features?: readonly Feature[]): FeatureSet {
  return new Set(features ?? MODES[mode])
}
