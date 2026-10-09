// Length caps of a note — they mirror `src/modules/notes/constants.py`, so a field stops the typing
// instead of the backend refusing after the save. `tests/apps/test_web_note_limits.py` keeps the
// two sides equal.
export const NOTE_TITLE_MAX = 128
export const NOTE_DESCRIPTION_MAX = 512
export const NOTE_BODY_MAX = 65536
