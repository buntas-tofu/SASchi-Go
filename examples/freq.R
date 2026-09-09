#!/usr/bin/env Rscript
# freq.R : the R half of the PROC FREQ descriptive gate (rulebook ST-015).
# Lanes:
#
#   tab    : csv (status,heritage rows) -> per cell of the 2x2 cross-tab:
#            row|col count cell% row% col%, one decimal each. The SAS
#            listing shape (cell, row, and column percents).
#   oneway : csv -> per level of the first column: count pct cumcount
#            cumpct, the PROC FREQ one-way listing shape.
#   ghost  : csv -> the same cross-tab but the first column carries an
#            extra factor level that never occurs in the data: R table
#            materializes the zero-count row (NaN percents) where SAS
#            would omit the level entirely.

args <- commandArgs(trailingOnly = TRUE)
cmd <- args[1]; csv <- args[2]

df <- read.csv(csv, stringsAsFactors = FALSE, check.names = FALSE)
cat("n=", nrow(df), "\n", sep = "")

fmt_pct <- function(x) if (!is.finite(x)) "MISSING" else sprintf("%.1f", x)

render_tab <- function(tab) {
  out <- character(0)
  for (r in rownames(tab)) {
    for (c in colnames(tab)) {
      v <- tab[r, c]
      p_all <- 100 * v / sum(tab)
      p_row <- 100 * v / sum(tab[r, ])
      p_col <- 100 * v / sum(tab[, c])
      out <- c(out, sprintf("%s|%s %d %s %s %s", r, c, v,
                            fmt_pct(p_all), fmt_pct(p_row), fmt_pct(p_col)))
    }
  }
  out
}

if (cmd == "tab") {
  tab <- table(df[[1]], df[[2]])
  cat(paste(render_tab(tab), collapse = "\n"), "\n", sep = "")
} else if (cmd == "oneway") {
  tab <- table(df[[1]])
  acc <- 0
  for (lvl in names(tab)) {
    v <- tab[[lvl]]; acc <- acc + v
    cat(sprintf("%s %d %s %d %s", lvl, v, fmt_pct(100 * v / sum(tab)),
                acc, fmt_pct(100 * acc / sum(tab))), "\n", sep = "")
  }
} else if (cmd == "ghost") {
  status <- factor(df[[1]], levels = c(sort(unique(df[[1]])), "ghost"))
  tab <- table(status, df[[2]])
  cat(paste(render_tab(tab), collapse = "\n"), "\n", sep = "")
} else {
  stop("unknown subcommand")
}
