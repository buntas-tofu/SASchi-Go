#!/usr/bin/env Rscript
# intnx.R : the R half of the INTNX / INTCK-WEEK gate (quirk 17).
#
#   intnx : interval:chr, days:num, inc:num, align:chr -> epoch days
#   week  : d1:num, d2:num -> Sunday boundaries crossed
#
# Base R only. Month-family intervals advance by interval INDEX then align
# (BEGINNING default, MIDDLE floor-midpoint, END last day, SAME clipped);
# WEEK begins Sunday (epoch 01JAN1960 was a Friday, its week began
# 27DEC1959, day -5).

args <- commandArgs(trailingOnly = TRUE)
cmd <- args[1]; csv <- args[2]
EPOCH <- as.Date("1960-01-01")

read_pinned <- function(csv, classes) {
  df <- read.csv(csv, colClasses = classes, quote = "\"")
  cat("n=", nrow(df), "\n", sep = "")
  df
}

midx <- function(d) {
  p <- as.POSIXlt(d)
  (p$year + 1900) * 12 + p$mon
}

mfirst <- function(idx) {
  y <- idx %/% 12; m <- idx %% 12
  as.Date(sprintf("%04d-%02d-01", y, m + 1))
}

sas_intnx <- function(interval, days, inc, align) {
  iv <- toupper(trimws(interval))
  al <- substr(toupper(trimws(align)), 1, 1)
  d <- EPOCH + days
  if (iv == "DAY") return(days + inc)
  if (iv == "WEEK") {
    ws <- days - ((days + 5) %% 7)
    ws <- ws + 7 * inc
    return(switch(al, B = ws, E = ws + 6, M = ws + 3,
                  S = ws + ((days + 5) %% 7)))
  }
  step <- switch(iv, MONTH = 1, QTR = 3, YEAR = 12,
                 stop("uncharacterized interval"))
  idx <- (midx(d) %/% step + inc) * step
  first <- mfirst(idx)
  last <- mfirst(idx + step) - 1
  out <- if (al == "B") first
  else if (al == "E") last
  else if (al == "M") first + (as.integer(last - first) %/% 2)
  else {
    if (iv == "YEAR") {
      p <- as.POSIXlt(d)
      y <- idx %/% 12
      cand <- tryCatch(as.Date(sprintf("%04d-%02d-%02d", y, p$mon + 1,
                                       p$mday)),
                       error = function(e) as.Date(NA))
      if (is.na(cand)) as.Date(sprintf("%04d-%02d-28", y, p$mon + 1)) else cand
    } else {
      anchor <- mfirst((midx(d) %/% step) * step)
      offset <- as.integer(d - anchor)
      span <- as.integer(last - first)
      first + min(offset, span)
    }
  }
  as.integer(out - EPOCH)
}

if (cmd == "intnx") {
  df <- read_pinned(csv, c(interval = "character", days = "numeric",
                           inc = "numeric", align = "character"))
  for (i in seq_len(nrow(df)))
    cat(sas_intnx(df$interval[i], df$days[i], df$inc[i], df$align[i]),
        "\n", sep = "")
} else if (cmd == "week") {
  df <- read_pinned(csv, c(d1 = "numeric", d2 = "numeric"))
  widx <- function(n) (n + 5) %/% 7
  for (i in seq_len(nrow(df)))
    cat(widx(df$d2[i]) - widx(df$d1[i]), "\n", sep = "")
} else {
  stop("unknown subcommand")
}
