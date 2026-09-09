#!/usr/bin/env Rscript
# numfmt.R : the R half of the precision and PUT-rendering gates (quirks 10
# and 11). One subcommand per construct; every lane reads a CSV with pinned
# colClasses (the quirk-7 lesson), prints n=<rows> as the harness guard, then
# one result per row.
#
#   trunc  : value:num, len:num  -> LENGTH-truncated double, 17 digits
#   fuzz   : value:num           -> FUZZ(value), 17 digits
#   putn   : value:num (NA ok), w:num, d:num -> the rendered field, quoted
#   date9  : days:num            -> DDMONYYYY (C locale, uppercase)
#   yymmdd : s:chr               -> epoch days or NA
#
# Truncation mirrors SAS LENGTH storage byte-exactly: big-endian pack, keep
# the leading `len` bytes, zero the low-order mantissa tail. PUT w.d rounds
# half AWAY from zero on the stored double (formatC/sprintf round half to
# even, the naive trap), drops decimals to fit, asterisk-fills, and prints
# missing as a right-justified period (the MISSING= default).

invisible(Sys.setlocale("LC_TIME", "C"))
args <- commandArgs(trailingOnly = TRUE)
cmd <- args[1]; csv <- args[2]

read_pinned <- function(csv, classes) {
  df <- read.csv(csv, colClasses = classes, quote = "\"")
  cat("n=", nrow(df), "\n", sep = "")
  df
}

sas_num_trunc <- function(x, len) {
  raw8 <- writeBin(as.double(x), raw(), size = 8, endian = "big")
  raw8[(len + 1):8] <- as.raw(0)
  if (len == 8) raw8 <- writeBin(as.double(x), raw(), size = 8, endian = "big")
  readBin(raw8, "double", size = 8, endian = "big")
}

sas_fuzz <- function(x) {
  n <- floor(x + 0.5)
  if (abs(x - n) < 1e-12) n else x
}

round_half_away <- function(x, d) {
  # Round on the STORED double's exact decimal expansion, not on abs(x)*10^d:
  # the scaling multiply manufactures false ties (2.675*100 lands exactly on
  # 267.5 in doubles while the stored 2.675 sits below the tie). sprintf
  # expands the true binary value; the first dropped digit decides, which is
  # exactly Decimal ROUND_HALF_UP, the Python reference's rule.
  str <- sprintf("%.*f", d + 25, abs(x))
  dot <- regexpr(".", str, fixed = TRUE)[1]
  keep <- as.numeric(substr(str, 1, dot + d))
  dropped <- substring(str, dot + d + 1)
  if (substr(dropped, 1, 1) >= "5") keep <- keep + 10^(-d)
  sign(x) * keep
}

sas_putn <- function(x, w, d) {
  if (is.na(x)) return(formatC(".", width = w))
  for (dd in seq(d, 0)) {
    s <- sprintf(paste0("%.", dd, "f"), round_half_away(x, dd))
    if (nchar(s) <= w) return(formatC(s, width = w))
  }
  paste(rep("*", w), collapse = "")
}

if (cmd == "trunc") {
  df <- read_pinned(csv, c(value = "numeric", len = "numeric"))
  for (i in seq_len(nrow(df)))
    cat(format(sas_num_trunc(df$value[i], df$len[i]), digits = 17), "\n", sep = "")
} else if (cmd == "fuzz") {
  df <- read_pinned(csv, c(value = "numeric"))
  for (v in df$value) cat(format(sas_fuzz(v), digits = 17), "\n", sep = "")
} else if (cmd == "putn") {
  df <- read_pinned(csv, c(value = "numeric", w = "numeric", d = "numeric"))
  for (i in seq_len(nrow(df)))
    cat('"', sas_putn(df$value[i], df$w[i], df$d[i]), '"', "\n", sep = "")
} else if (cmd == "date9") {
  df <- read_pinned(csv, c(days = "numeric"))
  for (v in df$days)
    cat(toupper(format(as.Date(v, origin = "1960-01-01"), "%d%b%Y")), "\n", sep = "")
} else if (cmd == "yymmdd") {
  df <- read_pinned(csv, c(s = "character"))
  for (v in df$s) {
    # strptime is prefix-lenient ('2024013X' parses as Jan 3); the round-trip
    # guard enforces the informat's strictness: parse, re-render, must match.
    t <- trimws(v)
    d <- as.Date(t, "%Y%m%d")
    ok <- !is.na(d) && format(d, "%Y%m%d") == t
    cat(if (!ok) "NA" else
        format(as.numeric(d - as.Date("1960-01-01")), digits = 17), "\n", sep = "")
  }
} else {
  stop("unknown subcommand")
}
