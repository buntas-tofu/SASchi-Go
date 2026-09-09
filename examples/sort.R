#!/usr/bin/env Rscript
# sort.R : the R half of the PROC SORT cross-language gate (quirk 9).
#
# usage: sort.R <csv> <colspec> <byspec> <nodupkey 0|1>
#   colspec: comma list of name:num|chr, passed to colClasses so read.csv
#            never guesses types (the quirk-7 harness bug, where read.csv ate
#            an empty-string fixture row, taught that lesson; the caller also
#            checks the n= line below against the rows it wrote).
#   byspec:  comma list of name:asc|desc
#
# prints n=<rows>, then the sorted marker column i, one value per line.
#
# The SAS ordering, in R terms: numeric missing becomes -Inf, so it sorts
# below every number ascending and lands last under DESCENDING, exactly the
# SAS reversal (SAS numerics have no infinity, so the sentinel cannot
# collide). Character keys strip trailing blanks (SAS comparison pads the
# shorter operand, so trailing blanks never order). order(method = "radix")
# is C-locale byte collation and STABLE, which is EQUALS, the SAS default,
# and it accepts per-variable `decreasing`, which is DESCENDING per variable.

args <- commandArgs(trailingOnly = TRUE)
csv <- args[1]; colspec <- args[2]; byspec <- args[3]; nodup <- args[4] == "1"

cs <- strsplit(strsplit(colspec, ",")[[1]], ":")
classes <- setNames(
  vapply(cs, function(p) if (p[2] == "num") "numeric" else "character", ""),
  vapply(cs, `[`, "", 1))
df <- read.csv(csv, colClasses = classes, quote = "\"")
cat("n=", nrow(df), "\n", sep = "")

bs <- strsplit(strsplit(byspec, ",")[[1]], ":")
vars <- vapply(bs, `[`, "", 1)
dirs <- vapply(bs, function(p) p[2] == "desc", TRUE)

keys <- lapply(vars, function(v) {
  col <- df[[v]]
  if (is.numeric(col)) ifelse(is.na(col), -Inf, col) else sub(" +$", "", col)
})
ord <- do.call(order, c(keys, list(decreasing = dirs, method = "radix")))
out <- df[ord, , drop = FALSE]
if (nodup) {
  kdf <- as.data.frame(lapply(keys, function(k) k[ord]), stringsAsFactors = FALSE)
  out <- out[!duplicated(kdf), , drop = FALSE]
}
if (nrow(out) > 0) cat(out$i, sep = "\n")
cat("\n")
