#!/usr/bin/env Rscript
# merge.R : the R half of the MERGE BY gate (quirk 15).
#
# usage: merge.R <left.csv> <right.csv> <byspec>
#   byspec: comma list of BY variable names; both CSVs carry pinned character
#   columns except the BY vars, which are numeric ("NA" allowed and missing
#   BY values MATCH each other, per the quirk-14 comparison law).
#
# Implements the PDV mechanics, not a join: max(nl, nr) rows per group,
# carry-forward on the exhausted side, shared variables overwritten by the
# right while it reads and FLIPPING to the left on the right's exhaustion,
# group-level retained IN= flags. prints n=<rows-in> guard for each input,
# then one output row per line: values pipe-joined, then in_l, in_r.

args <- commandArgs(trailingOnly = TRUE)
lcsv <- args[1]; rcsv <- args[2]
by <- strsplit(args[3], ",")[[1]]

read_side <- function(csv) {
  df <- read.csv(csv, colClasses = "character", quote = "\"")
  for (v in by) df[[v]] <- suppressWarnings(as.numeric(df[[v]]))
  cat("n=", nrow(df), "\n", sep = "")
  df
}

L <- read_side(lcsv); R <- read_side(rcsv)

key_of <- function(df, i) {
  vals <- vapply(by, function(v) {
    x <- df[[v]][i]
    if (is.na(x)) "MISSING" else format(x, digits = 17)
  }, "")
  paste(vals, collapse = "\r")
}

group_rows <- function(df) {
  ks <- if (nrow(df)) vapply(seq_len(nrow(df)), function(i) key_of(df, i), "") else character(0)
  split(seq_len(nrow(df)), factor(ks, levels = unique(ks)))
}

glist <- group_rows(L); grist <- group_rows(R)
lcols <- names(L); rcols <- names(R)
shared <- setdiff(intersect(lcols, rcols), by)
lonly <- setdiff(lcols, c(rcols, by))
ronly <- setdiff(rcols, c(lcols, by))
outcols <- c(by, lonly, ronly, shared)

keys <- union(names(glist), names(grist))
ord <- order(vapply(keys, function(k) {
  if (grepl("MISSING", k)) paste0("0\r", k) else paste0("1\r", k)
}, ""))
keys <- keys[ord]

cell <- function(v) if (is.na(v)) "NA" else v

for (key in keys) {
  li <- glist[[key]]; ri <- grist[[key]]
  nl <- length(li); nr <- length(ri)
  n <- max(nl, nr)
  for (i in seq_len(n)) {
    vals <- character(0)
    src <- if (nl) L[li[1], , drop = FALSE] else R[ri[1], , drop = FALSE]
    for (v in by) vals <- c(vals, cell(
      if (is.na(src[[v]][1])) NA else format(src[[v]][1], digits = 17)))
    for (v in lonly) vals <- c(vals, cell(
      if (nl) L[[v]][li[min(i, nl)]] else NA))
    for (v in ronly) vals <- c(vals, cell(
      if (nr) R[[v]][ri[min(i, nr)]] else NA))
    for (v in shared) {
      val <- if (nr && i <= nr) R[[v]][ri[i]]
             else if (nl) L[[v]][li[min(i, nl)]]
             else R[[v]][ri[nr]]
      vals <- c(vals, cell(val))
    }
    cat(paste(vals, collapse = "|"), "|", as.integer(nl > 0), "|",
        as.integer(nr > 0), "\n", sep = "")
  }
}
