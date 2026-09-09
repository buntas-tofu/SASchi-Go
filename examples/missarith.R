#!/usr/bin/env Rscript
# missarith.R : the R half of the missing-arithmetic gate (quirk 14).
#
#   arith : a:chr, op:chr, b:chr -> value or NA (missing operand or zero
#           divisor is missing, never Inf and never an error)
#   sum   : vals:chr (semicolon-joined, NA allowed) -> SUM(of ...) semantics
#   lt    : a:chr, b:chr -> 1/0, SAS order (missing below every number,
#           missing EQ missing so lt is false)
#   truth : x:chr -> 1/0 (missing and zero false)
#
# The point of the twin: R's native NA arithmetic propagates but NA < 0 is
# NA (a third state that silently drops filter rows) and 1/0 is Inf; the SAS
# rules are implemented explicitly, is.na checked first, so both hosts obey
# the same law.

args <- commandArgs(trailingOnly = TRUE)
cmd <- args[1]; csv <- args[2]

read_pinned <- function(csv, classes) {
  df <- read.csv(csv, colClasses = classes, quote = "\"")
  cat("n=", nrow(df), "\n", sep = "")
  df
}

num <- function(s) suppressWarnings(as.numeric(s))

sas_arith <- function(a, op, b) {
  a <- num(a); b <- num(b)
  if (is.na(a) || is.na(b)) return(NA)
  switch(op,
    "+" = a + b, "-" = a - b, "*" = a * b,
    "/" = if (b == 0) NA else a / b,
    "**" = a^b,
    stop("uncharacterized operator"))
}

emit <- function(v) cat(if (is.na(v)) "NA" else format(v, digits = 17),
                        "\n", sep = "")

if (cmd == "arith") {
  df <- read_pinned(csv, c(a = "character", op = "character", b = "character"))
  for (i in seq_len(nrow(df))) emit(sas_arith(df$a[i], df$op[i], df$b[i]))
} else if (cmd == "sum") {
  df <- read_pinned(csv, c(vals = "character"))
  for (s in df$vals) {
    xs <- suppressWarnings(as.numeric(strsplit(s, ";")[[1]]))
    xs <- xs[!is.na(xs)]
    emit(if (length(xs)) sum(xs) else NA)
  }
} else if (cmd == "lt") {
  df <- read_pinned(csv, c(a = "character", b = "character"))
  for (i in seq_len(nrow(df))) {
    a <- num(df$a[i]); b <- num(df$b[i])
    v <- if (is.na(a)) !is.na(b) else if (is.na(b)) FALSE else a < b
    cat(as.integer(v), "\n", sep = "")
  }
} else if (cmd == "truth") {
  df <- read_pinned(csv, c(x = "character"))
  for (s in df$x) {
    x <- num(s)
    cat(as.integer(!(is.na(x) || x == 0)), "\n", sep = "")
  }
} else {
  stop("unknown subcommand")
}
