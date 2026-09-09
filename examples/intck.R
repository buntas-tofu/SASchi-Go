#!/usr/bin/env Rscript
# intck.R : SAS INTCK (discrete, boundary-counting) in R, matching sas_semantics.py.
# Reads a fixtures CSV (cols interval,start,end ; dates ISO yyyy-mm-dd) from arg1
# and prints one integer per line: the R translation's INTCK result. The R side
# is deliberately built from the same boundary formula as Python, so the verifier
# proves agreement rather than assuming it.

sas_intck <- function(interval, start, end) {
  iv <- toupper(interval)
  sy <- as.integer(format(start, "%Y")); ey <- as.integer(format(end, "%Y"))
  sm <- as.integer(format(start, "%m")); em <- as.integer(format(end, "%m"))
  if (iv == "DAY")        as.integer(end - start)
  else if (iv == "MONTH") (ey - sy) * 12L + (em - sm)
  else if (iv == "QTR")   (ey * 4L + (em - 1L) %/% 3L) - (sy * 4L + (sm - 1L) %/% 3L)
  else if (iv == "YEAR")  ey - sy
  else stop(paste("interval not characterized:", interval))
}

args <- commandArgs(trailingOnly = TRUE)
fx <- read.csv(args[1], stringsAsFactors = FALSE, colClasses = "character")
for (i in seq_len(nrow(fx))) {
  cat(sas_intck(fx$interval[i], as.Date(fx$start[i]), as.Date(fx$end[i])), "\n", sep = "")
}
