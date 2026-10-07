// One ladder of page sizes for every list in the app — the research registry, sources, web search
// pages, job runs. Each used to have its own ladder (25/50/100/200, 200/500/1000), and "rows per
// page" meant different things depending on where you stood.
//
// Default is 100: that many rows can still be scanned by eye, yet it almost always fits a whole
// section, so no paging is needed.
export const PAGE_SIZES = [50, 100, 200, 500]

export const DEFAULT_PAGE_SIZE = 100
