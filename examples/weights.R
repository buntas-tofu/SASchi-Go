#!/usr/bin/env Rscript
# weights.R : the R half of the WEIGHT-semantics gate (quirk 12, second half).
#
#   wstat : stat:chr (mean|std_df|std_n|std_wdf|std_weight), excl:num (0|1),
#           x:chr, w:chr (semicolon-joined, NA allowed) -> value or NA
#   wfreq : levels:chr, w:chr (semicolon-joined) -> "level=count" pairs,
#           insertion order, zero-total levels dropped
#
# Base R has no weighted variance; the divisor set is hand-built from the
# documented VARDEF semantics (DF n-1, N n, WDF sum(w)-1, WEIGHT sum(w)),
# missing weight excludes the row, nonpositive weights are INCLUDED unless
# excl (the EXCLNPWGT toggle), and a negative weighted CSS reads as missing.

args <- commandArgs(trailingOnly = TRUE)
cmd <- args[1]; csv <- args[2]

read_pinned <- function(csv, classes) {
  df <- read.csv(csv, colClasses = classes, quote = "\"")
  cat("n=", nrow(df), "\n", sep = "")
  df
}

nums <- function(s) suppressWarnings(as.numeric(strsplit(s, ";")[[1]]))

wrows <- function(xs, ws, excl) {
  keep <- !is.na(xs) & !is.na(ws)
  xs <- xs[keep]; ws <- ws[keep]
  if (excl) { k2 <- ws > 0; xs <- xs[k2]; ws <- ws[k2] }
  list(x = xs, w = ws)
}

wstat <- function(stat, excl, xs, ws) {
  r <- wrows(xs, ws, excl)
  n <- length(r$x); sw <- sum(r$w)
  if (n == 0 || sw == 0) return(NA)
  m <- sum(r$w * r$x) / sw
  if (stat == "mean") return(m)
  css <- sum(r$w * (r$x - m)^2)
  div <- switch(stat, std_df = n - 1, std_n = n,
                std_wdf = sw - 1, std_weight = sw)
  if (div <= 0 || css < 0) return(NA)
  sqrt(css / div)
}

if (cmd == "wstat") {
  df <- read_pinned(csv, c(stat = "character", excl = "numeric",
                           x = "character", w = "character"))
  for (i in seq_len(nrow(df))) {
    v <- wstat(df$stat[i], df$excl[i] == 1, nums(df$x[i]), nums(df$w[i]))
    cat(if (is.na(v)) "NA" else format(v, digits = 17), "\n", sep = "")
  }
} else if (cmd == "wfreq") {
  df <- read_pinned(csv, c(levels = "character", w = "character"))
  for (i in seq_len(nrow(df))) {
    lv <- strsplit(df$levels[i], ";")[[1]]
    ws <- nums(df$w[i])
    keep <- !is.na(ws)
    lv <- lv[keep]; ws <- ws[keep]
    out <- list()
    for (j in seq_along(lv)) {
      k <- lv[j]
      out[[k]] <- (if (is.null(out[[k]])) 0 else out[[k]]) + ws[j]
    }
    keep_names <- names(out)[vapply(out, function(v) v != 0, TRUE)]
    cat(paste0(keep_names, "=",
               vapply(keep_names, function(k) format(out[[k]], digits = 17), ""),
               collapse = ";"), "\n", sep = "")
  }
} else {
  stop("unknown subcommand")
}
