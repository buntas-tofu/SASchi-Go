#!/usr/bin/env Rscript
# csvimport.R : the R half of the CSV import gate (rulebook DS-021).
# Lanes:
#
#   types   : csv path -> the default read.csv() inference per column,
#             normalized (INT/NUM/CHAR), row-count guarded. The naive
#             translation lane.
#   pinned  : csv path -> the same file read with explicit colClasses
#             (identifiers as character), rendering every cell quoted, so
#             byte-equality proves the pinned read. The rule lane.

args <- commandArgs(trailingOnly = TRUE)
cmd <- args[1]; csv <- args[2]

if (cmd == "types") {
  df <- read.csv(csv, check.names = FALSE)
  cat("n=", nrow(df), "\n", sep = "")
  cat(paste(vapply(df, function(col) {
    if (is.character(col)) "CHAR" else if (is.integer(col)) "INT"
    else if (is.numeric(col)) "NUM" else "OTHER"
  }, character(1)), collapse = ","), "\n", sep = "")
} else if (cmd == "pinned") {
  df <- read.csv(csv, colClasses = "character", check.names = FALSE,
                 na.strings = "__NONE__")
  cat("n=", nrow(df), "\n", sep = "")
  for (i in seq_len(nrow(df))) {
    cells <- vapply(df[i, ], as.character, character(1))
    cat(paste0('"', cells, '"', collapse = ","), "\n", sep = "")
  }
} else {
  stop("unknown subcommand")
}
