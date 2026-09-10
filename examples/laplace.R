#!/usr/bin/env Rscript
# laplace.R : the R half of the Laplace distribution gate (rulebook ST-016,
# the Appendix E.2 noise surface). Base R carries no Laplace distribution;
# every lane here mirrors the sas_semantics.py closed forms operation for
# operation, so byte-equality at 17 digits is a property of identical IEEE
# arithmetic, never of a library coincidence.
#
#   pdf   : value:num, m:num, s:num -> exp(-abs(x - m)/s) / (2*s)
#   cdf   : value:num, m:num, s:num -> 0.5*exp((x - m)/s) below the location,
#           1 - 0.5*exp(-(x - m)/s) at or above it (both give 0.5 at x = m)
#   quant : value:num (a probability p), m:num, s:num ->
#           m - s*sign(p - 0.5)*log(1 - 2*abs(p - 0.5)); p = 0.5 returns m.
#           The same expression is the inverse-CDF construction for drawing
#           from a pinned uniform grid, the lane where "validate the
#           distribution, never a stream" becomes executable.
#
# Every lane prints n=<rows> first as the harness guard, then one %.17g
# result per row.

args <- commandArgs(trailingOnly = TRUE)
cmd <- args[1]; csv <- args[2]

read_pinned <- function(csv) {
  df <- read.csv(csv, colClasses = c(value = "numeric", m = "numeric",
                                     s = "numeric"), quote = "\"")
  cat("n=", nrow(df), "\n", sep = "")
  df
}

fmt17 <- function(x) sprintf("%.17g", x)

sas_laplace_pdf <- function(x, m, s) {
  exp(-abs(x - m) / s) / (2 * s)
}

sas_laplace_cdf <- function(x, m, s) {
  if (x < m) 0.5 * exp((x - m) / s) else 1 - 0.5 * exp(-(x - m) / s)
}

sas_laplace_quantile <- function(p, m, s) {
  u <- p - 0.5
  if (u == 0) return(m)
  m - s * sign(u) * log(1 - 2 * abs(u))
}

f <- switch(cmd,
            pdf = sas_laplace_pdf,
            cdf = sas_laplace_cdf,
            quant = sas_laplace_quantile,
            stop("unknown subcommand"))

df <- read_pinned(csv)
for (i in seq_len(nrow(df))) {
  cat(fmt17(f(df$value[i], df$m[i], df$s[i])), "\n", sep = "")
}
