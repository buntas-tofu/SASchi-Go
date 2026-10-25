#!/usr/bin/env Rscript
# Independent MOD witness for exact binary64 integers. Maintainer evidence,
# not live SAS output. Binary long division avoids R %% and rounded quotients.

sas_mod <- function(dividend, divisor) {
  for (value in list(dividend, divisor)) {
    if (is.null(value) || inherits(value, 'sas_missing'))
      stop('missing or structured arguments require review')
    if (!is.numeric(value) || length(value) != 1L)
      stop('numeric arguments required')
    if (!is.finite(value)) stop('nonfinite arguments require review')
    if (abs(value) > 2^53) stop('magnitude beyond binary64 exact-integer bound')
    if (value != trunc(value)) stop('fractional arguments require SAS fuzzing review')
  }
  if (divisor == 0) stop('zero divisor requires SAS error-behavior review')
  remainder <- abs(dividend)
  step <- abs(divisor)
  # All additions/subtractions below stay within the exact integer domain.
  while (step <= remainder / 2) step <- step * 2
  while (step >= abs(divisor)) {
    if (remainder >= step) remainder <- remainder - step
    step <- step / 2
  }
  if (dividend < 0 && remainder != 0) -remainder else remainder
}

args <- commandArgs(trailingOnly=TRUE)
if (length(args) != 1L) stop('usage: Rscript mod.R fixture.csv')
rows <- read.csv(args[1], colClasses='character', na.strings=character(),
                 strip.white=FALSE, check.names=FALSE)
decode <- function(value, kind) {
  if (kind == 'number') return(as.numeric(value))
  if (kind == 'missing') return(NULL)
  if (kind == 'tagged') return(structure(list(missing=value), class='sas_missing'))
  if (kind == 'boolean') return(value == 'True')
  if (kind == 'other') return(list(value))
  value
}
for (i in seq_len(nrow(rows))) {
  row <- rows[i, ]
  result <- tryCatch(sprintf('%.0f', sas_mod(decode(row$a, row$a_kind),
                                            decode(row$b, row$b_kind))),
                     error=function(e) paste0('ERROR: ', conditionMessage(e)))
  cat(result, '\n', sep='')
}
