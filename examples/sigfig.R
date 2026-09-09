#!/usr/bin/env Rscript
# sigfig.R : the R half of the significant-digit gate (rulebook DS-020,
# the four-sig-fig surface). Lanes:
#
#   render : value:num, mode:chr -> sprintf of the mode, byte-identical to
#            the C printf that Python's % formatting wraps. Modes: plain
#            (%.4g), prespace (% .4g), sign (%+.4g), sci_e (%e), sci_E (%E).
#   signif : value:num, n:num  -> signif(value, n) rendered at 17 digits.
#            R signif and Python %g both round half to even, the landmine
#            against SAS ROUND (half away from zero).
#   sas    : value:num, n:num  -> the SAS-equivalent four-sig-fig value:
#            unit = 10^(floor(log10(abs(x))) - n + 1), then sas_round
#            semantics (half away from zero with the ROUND fuzz, exactly
#            the reference arithmetic), rendered at 17 digits.

args <- commandArgs(trailingOnly = TRUE)
cmd <- args[1]; csv <- args[2]

read_pinned <- function(csv, classes) {
  df <- read.csv(csv, colClasses = classes, quote = "\"")
  cat("n=", nrow(df), "\n", sep = "")
  df
}

round_half_away <- function(x, d) {
  str <- sprintf("%.*f", d + 25, abs(x))
  dot <- regexpr(".", str, fixed = TRUE)[1]
  keep <- as.numeric(substr(str, 1, dot + d))
  dropped <- substring(str, dot + d + 1)
  if (substr(dropped, 1, 1) >= "5") keep <- keep + 10^(-d)
  sign(x) * keep
}

sas_round_lane <- function(x, unit) {
  # Mirror sas_semantics.sas_round exactly: half away from zero with the
  # documented ROUND fuzz, on the same IEEE division and multiplication.
  q <- abs(x) / unit
  r <- floor(q + 0.5 + 1e-9)
  sign(x) * r * unit
}

fmt17 <- function(x) sprintf("%.17g", x)

if (cmd == "render") {
  df <- read_pinned(csv, c(value = "numeric", mode = "character"))
  fmts <- c(plain = "%.4g", prespace = "% .4g", sign = "%+.4g",
            sci_e = "%e", sci_E = "%E")
  for (i in seq_len(nrow(df))) {
    f <- fmts[[df$mode[i]]]
    if (is.null(f)) stop("unknown mode")
    cat(sprintf(f, df$value[i]), "\n", sep = "")
  }
} else if (cmd == "signif") {
  df <- read_pinned(csv, c(value = "numeric", n = "numeric"))
  for (i in seq_len(nrow(df)))
    cat(fmt17(signif(df$value[i], df$n[i])), "\n", sep = "")
} else if (cmd == "sas") {
  df <- read_pinned(csv, c(value = "numeric", n = "numeric"))
  for (i in seq_len(nrow(df))) {
    x <- df$value[i]; n <- df$n[i]
    if (x == 0) { cat("0\n"); next }
    unit <- 10^(floor(log10(abs(x))) - n + 1)
    cat(fmt17(sas_round_lane(x, unit)), "\n", sep = "")
  }
} else {
  stop("unknown subcommand")
}
