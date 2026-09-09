#!/usr/bin/env Rscript
# transpose.R : the R half of the PROC TRANSPOSE gate (quirk 16).
#
# usage: transpose.R <csv> <byspec> <idvar|-> <varspec|-> <prefix|-> <let 0|1>
#   All columns read as character except VAR columns, read numeric via the
#   varspec (name:num). Prints the output column header (pipe-joined), then
#   one row per line, NA for missing cells. Duplicate ID in a group without
#   LET prints DUPLICATE-ID-ERROR and stops, matching the SAS default.
#
# Single-pass semantics: columns are the union of mangled ID values across
# all groups in first-appearance order (or COL1..COLmax without ID, sized by
# the largest group), one output row per VAR variable per BY group.

args <- commandArgs(trailingOnly = TRUE)
csv <- args[1]
by <- if (args[2] == "-") character(0) else strsplit(args[2], ",")[[1]]
idv <- if (args[3] == "-") NA else args[3]
varspec <- if (args[4] == "-") NA else strsplit(args[4], ",")[[1]]
prefix <- if (args[5] == "-") "" else args[5]
let <- args[6] == "1"

df <- read.csv(csv, colClasses = "character", quote = "\"")
cat("n=", nrow(df), "\n", sep = "")

vars <- if (all(is.na(varspec))) {
  cand <- setdiff(names(df), c(by, if (!is.na(idv)) idv))
  cand[vapply(cand, function(v)
    all(!is.na(suppressWarnings(as.numeric(df[[v]][df[[v]] != "NA"])))), TRUE)]
} else varspec

mangle <- function(v) {
  s <- paste0(prefix, trimws(v))
  s <- gsub("[^A-Za-z0-9_]", "_", s)
  if (nchar(s) == 0 || grepl("^[0-9]", s)) s <- paste0("_", s)
  substr(s, 1, 32)
}

keys <- if (length(by)) {
  apply(df[, by, drop = FALSE], 1, paste, collapse = "\r")
} else {
  rep("", nrow(df))
}
ukeys <- unique(keys)

if (!is.na(idv)) {
  id_cols <- character(0)
  for (k in ukeys) {
    grp <- df[keys == k, , drop = FALSE]
    seen <- character(0)
    for (i in seq_len(nrow(grp))) {
      nm <- mangle(grp[[idv]][i])
      if (nm %in% seen && !let) { cat("DUPLICATE-ID-ERROR\n"); quit(status = 0) }
      seen <- c(seen, nm)
      if (!(nm %in% id_cols)) id_cols <- c(id_cols, nm)
    }
  }
  data_cols <- id_cols
} else {
  width <- max(vapply(ukeys, function(k) sum(keys == k), 1L))
  base <- if (nzchar(prefix)) prefix else "COL"
  data_cols <- paste0(base, seq_len(width))
}

out_cols <- c(by, "_NAME_", data_cols)
cat(paste(out_cols, collapse = "|"), "\n", sep = "")
for (k in ukeys) {
  grp <- df[keys == k, , drop = FALSE]
  for (v in vars) {
    cells <- setNames(rep("NA", length(data_cols)), data_cols)
    if (!is.na(idv)) {
      for (i in seq_len(nrow(grp))) cells[mangle(grp[[idv]][i])] <- grp[[v]][i]
    } else {
      for (i in seq_len(nrow(grp))) cells[i] <- grp[[v]][i]
    }
    byvals <- if (length(by)) as.character(grp[1, by]) else character(0)
    cat(paste(c(byvals, v, unname(cells)), collapse = "|"), "\n", sep = "")
  }
}
