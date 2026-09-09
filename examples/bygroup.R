#!/usr/bin/env Rscript
# bygroup.R : R twin of the SAS BY-group sequential model in sas_semantics.py.
# FIRST./LAST. flags follow the BY prefix; the retain pattern resets the running
# total at first.<last by> and outputs at last.<last by>. Built from the same
# rule so the verifier proves Python/R agreement, NOT R's native grouping. Two
# modes: flags (first then last flags per row) and retain (one row per group).

args <- commandArgs(trailingOnly = TRUE)
mode <- args[1]
df <- read.csv(args[2], stringsAsFactors = FALSE, colClasses = "character",
               blank.lines.skip = FALSE)
by_vars <- strsplit(args[3], ",", fixed = TRUE)[[1]]

by_flags <- function(df, by_vars) {
  n <- nrow(df)
  first <- matrix(FALSE, n, length(by_vars))
  last <- matrix(FALSE, n, length(by_vars))
  for (j in seq_along(by_vars)) {
    key <- apply(df[, by_vars[1:j], drop = FALSE], 1, paste, collapse = "\r")
    prev <- c(NA_character_, key[-n])
    nxt <- c(key[-1], NA_character_)
    first[, j] <- is.na(prev) | key != prev
    last[, j] <- is.na(nxt) | key != nxt
  }
  list(first = first, last = last)
}

if (mode == "flags") {
  fl <- by_flags(df, by_vars)
  for (i in seq_len(nrow(df))) {
    cat(paste(c(as.integer(fl$first[i, ]), as.integer(fl$last[i, ])),
              collapse = " "), "\n", sep = "")
  }
} else if (mode == "retain") {
  sum_var <- args[4]
  fl <- by_flags(df, by_vars)
  lb <- length(by_vars)
  total <- 0
  for (i in seq_len(nrow(df))) {
    if (fl$first[i, lb]) total <- 0
    v <- suppressWarnings(as.numeric(df[[sum_var]][i]))
    total <- total + (if (is.na(v)) 0 else v)
    if (fl$last[i, lb]) {
      vals <- as.character(df[i, by_vars])
      cat(paste(c(vals, format(total, trim = TRUE, scientific = FALSE)),
                collapse = " "), "\n", sep = "")
    }
  }
}
