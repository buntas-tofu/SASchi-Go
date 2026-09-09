#!/usr/bin/env Rscript
# fisher.R : the R half of the Fisher exact gate (rulebook ST-014). One
# lane: reads a CSV of 2x2 tables (name,a,b,c,d), prints n= rows as the
# harness guard, then per row: name, two-sided p, left-sided p, each %.4g.
# Orientation: the matrix is built byrow so a is the top-left cell; 'less'
# is the lower tail on a, the SAS XPL_FISH column. R and scipy both default
# to two-sided, which is the landmine: the SAS left column requires an
# explicit alternative.

args <- commandArgs(trailingOnly = TRUE)
csv <- args[1]
df <- read.csv(csv, colClasses = c(name = "character", a = "numeric",
                                   b = "numeric", c = "numeric", d = "numeric"))
cat("n=", nrow(df), "\n", sep = "")
for (i in seq_len(nrow(df))) {
  m <- matrix(c(df$a[i], df$b[i], df$c[i], df$d[i]), nrow = 2, byrow = TRUE)
  p2 <- fisher.test(m, alternative = "two.sided")$p.value
  p1 <- fisher.test(m, alternative = "less")$p.value
  cat(sprintf("%s %.4g %.4g\n", df$name[i], p2, p1))
}
