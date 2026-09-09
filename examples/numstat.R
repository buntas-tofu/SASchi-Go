#!/usr/bin/env Rscript
# numstat.R : the R half of the statistical-function gate (quirk 12, first
# half: probability/quantile functions and SAS moment estimators).
#
#   dist    : fn:chr, a:num, b:num, c:num -> value or NA, 17 digits
#   moments : stat:chr, data:chr (semicolon-joined, NA allowed) -> value or NA
#
# Base R distributions are the twin (pnorm/qnorm, pchisq/qchisq, pt/qt,
# pf/qf); the SAS temperament returns NA out of domain instead of warning.
# Moments are the SAS G1/G2 formulas by hand: base R has no skewness or
# kurtosis, which is exactly the trap the reference documents.

args <- commandArgs(trailingOnly = TRUE)
cmd <- args[1]; csv <- args[2]

read_pinned <- function(csv, classes) {
  df <- read.csv(csv, colClasses = classes, quote = "\"")
  cat("n=", nrow(df), "\n", sep = "")
  df
}

emit <- function(v) cat(if (is.null(v) || is.na(v)) "NA"
                        else format(v, digits = 17), "\n", sep = "")

dist_one <- function(fn, a, b, c) {
  switch(fn,
    probnorm = pnorm(a),
    probit   = if (a > 0 && a < 1) qnorm(a) else NA,
    probchi  = if (a >= 0 && b > 0) pchisq(a, b) else NA,
    cinv     = if (a >= 0 && a < 1 && b > 0) qchisq(a, b) else NA,
    probt    = if (b > 0) pt(a, b) else NA,
    tinv     = if (a > 0 && a < 1 && b > 0) qt(a, b) else NA,
    probf    = if (a >= 0 && b > 0 && c > 0) pf(a, b, c) else NA,
    finv     = if (a >= 0 && a < 1 && b > 0 && c > 0) qf(a, b, c) else NA,
    stop("unknown fn"))
}

sas_vals <- function(s) {
  xs <- suppressWarnings(as.numeric(strsplit(s, ";")[[1]]))
  xs[!is.na(xs)]
}

sas_std <- function(xs, div) {
  n <- length(xs)
  d <- if (div == "N") n else n - 1
  if (d <= 0) return(NA)
  m <- mean(xs)
  sqrt(sum((xs - m)^2) / d)
}

moments_one <- function(stat, s) {
  xs <- sas_vals(s)
  n <- length(xs)
  if (stat == "mean") return(if (n) mean(xs) else NA)
  if (stat == "std_df") return(sas_std(xs, "DF"))
  if (stat == "std_n") return(sas_std(xs, "N"))
  sd0 <- sas_std(xs, "DF")
  if (stat == "skew") {
    if (n < 3 || is.na(sd0) || sd0 == 0) return(NA)
    z <- (xs - mean(xs)) / sd0
    return(n / ((n - 1) * (n - 2)) * sum(z^3))
  }
  if (stat == "kurt") {
    if (n < 4 || is.na(sd0) || sd0 == 0) return(NA)
    z <- (xs - mean(xs)) / sd0
    return(n * (n + 1) / ((n - 1) * (n - 2) * (n - 3)) * sum(z^4)
           - 3 * (n - 1)^2 / ((n - 2) * (n - 3)))
  }
  stop("unknown stat")
}

if (cmd == "dist") {
  df <- read_pinned(csv, c(fn = "character", a = "numeric",
                           b = "numeric", c = "numeric"))
  for (i in seq_len(nrow(df)))
    emit(dist_one(df$fn[i], df$a[i], df$b[i], df$c[i]))
} else if (cmd == "moments") {
  df <- read_pinned(csv, c(stat = "character", data = "character"))
  for (i in seq_len(nrow(df)))
    emit(moments_one(df$stat[i], df$data[i]))
} else {
  stop("unknown subcommand")
}
