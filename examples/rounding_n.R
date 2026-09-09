# rounding_n.R : gold-pair R translation of the count-rounding ladder.
# Source: a small-count disclosure-control rounding ladder.
# STATUS: the fixture suite in verify_rounding.py defines the acceptance bar.
#
# R's round() also rounds half to even (IEC 60559), the same trap as Python's.
# sas_round below is the half-away-from-zero reference, mirroring
# sas_semantics.py including the fuzz term.

FUZZ <- 1e-9

sas_round <- function(x, unit = 1) {
  stopifnot(unit > 0)
  sign(x) * floor(abs(x) / unit + 0.5 + FUZZ) * unit
}

round_count <- function(x) {
  # R's ifelse evaluates EVERY branch over the WHOLE vector before selecting,
  # unlike the SAS ladder or Python's if/elif. The last branch must therefore
  # compute safely for values it will never be selected for: pmax guards
  # log10 against the small values (log10(0) is -Inf, unit would be 0).
  # Landmine found by the fixture gate, 2026-07-09.
  ifelse(x < 15, 10,
  ifelse(x < 100, sas_round(x, 10),
  ifelse(x < 1000, sas_round(x, 50),
  ifelse(x < 10000, sas_round(x, 100),
  ifelse(x < 100000, sas_round(x, 500),
  ifelse(x < 1000000, sas_round(x, 1000),
         sas_round(x, 10 ^ (floor(log10(pmax(x, 1))) - 3))))))))
}

round_counts <- function(df, varlist) {
  for (var in varlist) {
    df[[paste0(var, "_r")]] <- round_count(df[[var]])
  }
  df
}

args <- commandArgs(trailingOnly = TRUE)
if (length(args) == 3) {
  df <- read.csv(args[1])
  varlist <- strsplit(args[3], ",")[[1]]
  write.csv(round_counts(df, varlist), args[2], row.names = FALSE)
  cat(sprintf("%d rows -> %s (rounded: %s)\n", nrow(df), args[2], args[3]))
}
