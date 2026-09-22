#!/usr/bin/env Rscript
# lag.R : the R half of the LAG/DIF queue gate (DS-007).
#
#   queue       : value, n                -> LAG<n>(value) once per row
#   conditional : value, invoked, n       -> LAG<n> where the call runs
#   dif         : value, invoked, n       -> DIF<n> = value - LAG<n>
#   occurrences : value, inv_a, inv_b, n  -> two occurrences, two queues
#
# The queue law is the reference's, mirrored operation for operation: read the
# front only once the queue holds n values, then store the current value, then
# drop the oldest. A row where the call does not run returns missing and leaves
# the queue alone. A missing argument IS an execution. Missing prints as ".",
# which is SAS's own marker and cannot be confused with a literal "NA" in a
# data file. Base R has no LAG queue to borrow, so this is hand-written on
# purpose: the trap is that dplyr::lag is row-based and cannot express
# invocation-driven history.

args <- commandArgs(trailingOnly = TRUE)
cmd <- args[1]
csv <- args[2]

read_pinned <- function(csv, classes) {
  df <- read.csv(csv, colClasses = classes, quote = "\"")
  cat("n=", nrow(df), "\n", sep = "")
  df
}

tok <- function(v) if (is.null(v) || is.na(v)) "." else sprintf("%.17g", v)

emit <- function(v) cat(tok(v), "\n", sep = "")

lag_run <- function(values, invoked, n) {
  queue <- numeric(0)
  out <- rep(NA_real_, length(values))
  for (i in seq_along(values)) {
    if (!invoked[i]) next
    if (length(queue) == n) out[i] <- queue[1]
    queue <- c(queue, values[i])
    if (length(queue) > n) queue <- queue[-1]
  }
  out
}

dif_run <- function(values, invoked, n) {
  queue <- numeric(0)
  out <- rep(NA_real_, length(values))
  for (i in seq_along(values)) {
    if (!invoked[i]) next
    front <- if (length(queue) == n) queue[1] else NA_real_
    if (!is.na(front) && !is.na(values[i])) out[i] <- values[i] - front
    queue <- c(queue, values[i])
    if (length(queue) > n) queue <- queue[-1]
  }
  out
}

if (cmd == "queue") {
  df <- read_pinned(csv, c(value = "numeric", n = "integer"))
  for (v in lag_run(df$value, rep(TRUE, nrow(df)), df$n[1])) emit(v)
} else if (cmd == "conditional") {
  df <- read_pinned(csv, c(value = "numeric", invoked = "integer",
                           n = "integer"))
  for (v in lag_run(df$value, df$invoked == 1L, df$n[1])) emit(v)
} else if (cmd == "dif") {
  df <- read_pinned(csv, c(value = "numeric", invoked = "integer",
                           n = "integer"))
  for (v in dif_run(df$value, df$invoked == 1L, df$n[1])) emit(v)
} else if (cmd == "occurrences") {
  df <- read_pinned(csv, c(value = "numeric", inv_a = "integer",
                           inv_b = "integer", n = "integer"))
  a <- lag_run(df$value, df$inv_a == 1L, df$n[1])
  b <- lag_run(df$value, df$inv_b == 1L, df$n[1])
  for (i in seq_len(nrow(df))) cat(sprintf("%s %s\n", tok(a[i]), tok(b[i])))
} else {
  stop("unknown subcommand")
}