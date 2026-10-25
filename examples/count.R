#!/usr/bin/env Rscript
# COUNT reference twin, bounded ASCII I/T slice. This is repository evidence
# for maintainers, not a live-SAS capture. Undefined overlaps require review.
# Independent implementation: inspect every possible substring window.

sas_count <- function(string, substring, modifiers = "") {
  values <- list(string, substring, modifiers)
  if (!all(vapply(values, function(x) is.character(x) && length(x) == 1L &&
                  !is.na(x), logical(1)))) stop("character arguments")
  if (!all(vapply(values, function(x) all(utf8ToInt(x) > 0L &
                  utf8ToInt(x) < 128L), logical(1)))) stop("encoding review")
  modifiers <- chartr("IT", "it", modifiers)
  if (grepl("[^it]", modifiers)) stop("unsupported modifier")
  if (nchar(string) == 0L) stop("zero-length string")
  if (grepl("t", modifiers, fixed = TRUE)) {
    string <- sub(" +$", "", string)
    substring <- sub(" +$", "", substring)
  }
  if (nchar(substring) == 0L) stop("empty substring")
  if (grepl("i", modifiers, fixed = TRUE)) {
    string <- chartr("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz", string)
    substring <- chartr("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz", substring)
  }
  width <- nchar(substring)
  windows <- nchar(string) - width + 1L
  if (windows <= 0L) return(0L)
  positions <- which(vapply(seq_len(windows), function(i)
    substr(string, i, i + width - 1L) == substring, logical(1)))
  if (any(diff(positions) < width)) stop("overlapping matches")
  length(positions)
}

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) stop("usage: Rscript count.R fixture.csv")
rows <- read.csv(args[1], colClasses = "character", na.strings = character(),
                 strip.white = FALSE, check.names = FALSE)
decode <- function(value, kind) {
  if (kind == "text") return(value)
  if (kind == "missing") return(NA_character_)
  if (kind == "number") return(as.numeric(value))
  stop("unsupported fixture type")
}
for (i in seq_len(nrow(rows))) {
  row <- rows[i, ]
  answer <- tryCatch(as.character(sas_count(decode(row$string, row$string_kind),
    decode(row$substring, row$substring_kind), decode(row$modifiers, row$modifiers_kind))),
    error = function(e) paste0("ERROR: ", conditionMessage(e)))
  cat(answer, "\n", sep = "")
}
