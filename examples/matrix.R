#!/usr/bin/env Rscript
# matrix.R : the R half of the IML matrix gate (rulebook MX-001, the
# matrix appendix). Two facts drive every lane:
#
#   SAS IML fills row-wise (shape reads a vector across rows) while base R
#   matrix() fills column-wise: equivalent construction needs byrow TRUE.
#   SAS IML's '*' is matrix multiplication and '#' is elementwise, exactly
#   opposite to R and numpy, where '*' is elementwise and the product is
#   '%*%' (numpy: '@').
#
# The lanes mirror sas_semantics.py operation for operation (explicit
# loops, same summation order), so byte-equality at 17 digits is a
# property of identical IEEE arithmetic. Matrices travel in CSV fields as
# rows joined with ';' and entries separated by spaces.
#
#   shape  : value (vector), n1 (rows), n2 (cols) -> row-major fill
#   fillcol: value, n1, n2 -> the base-R default fill, for the landmine
#   trans  : a -> a transposed
#   hcat   : a, b -> side by side        vcat : a, b -> stacked
#   mul    : a, b -> matrix product      elem : a, b -> elementwise
#   inv2   : a -> 2x2 inverse, or the token 'singular'

args <- commandArgs(trailingOnly = TRUE)
cmd <- args[1]; csv <- args[2]

read_pinned <- function(csv, classes) {
  df <- read.csv(csv, colClasses = classes, quote = "\"")
  cat("n=", nrow(df), "\n", sep = "")
  df
}

parse_mat <- function(s) {
  rows <- strsplit(s, ";", fixed = TRUE)[[1]]
  do.call(rbind, lapply(rows, function(r)
    as.numeric(strsplit(trimws(r), "[ ]+")[[1]])))
}

render <- function(m) {
  rows <- if (is.matrix(m)) lapply(seq_len(nrow(m)), function(r) m[r, ]) else m
  cat(paste(vapply(rows, function(r)
    paste(sprintf("%.17g", as.numeric(r)), collapse = " "), ""),
    collapse = ";"), "\n", sep = "")
}

if (cmd == "shape") {
  df <- read_pinned(csv, c(value = "character", n1 = "character", n2 = "character"))
  for (i in seq_len(nrow(df))) {
    v <- as.numeric(strsplit(trimws(df$value[i]), "[ ]+")[[1]])
    render(matrix(v, as.integer(df$n1[i]), as.integer(df$n2[i]), byrow = TRUE))
  }
} else if (cmd == "fillcol") {
  df <- read_pinned(csv, c(value = "character", n1 = "character", n2 = "character"))
  for (i in seq_len(nrow(df))) {
    v <- as.numeric(strsplit(trimws(df$value[i]), "[ ]+")[[1]])
    render(matrix(v, as.integer(df$n1[i]), as.integer(df$n2[i])))
  }
} else if (cmd == "trans") {
  df <- read_pinned(csv, c(a = "character"))
  for (i in seq_len(nrow(df))) render(t(parse_mat(df$a[i])))
} else if (cmd == "hcat") {
  df <- read_pinned(csv, c(a = "character", b = "character"))
  for (i in seq_len(nrow(df))) render(cbind(parse_mat(df$a[i]), parse_mat(df$b[i])))
} else if (cmd == "vcat") {
  df <- read_pinned(csv, c(a = "character", b = "character"))
  for (i in seq_len(nrow(df))) render(rbind(parse_mat(df$a[i]), parse_mat(df$b[i])))
} else if (cmd == "mul") {
  df <- read_pinned(csv, c(a = "character", b = "character"))
  for (i in seq_len(nrow(df))) {
    a <- parse_mat(df$a[i]); b <- parse_mat(df$b[i])
    nr <- nrow(a); nc <- ncol(b); out <- vector("list", nr)
    for (r in seq_len(nr)) {
      row <- numeric(nc)
      for (c in seq_len(nc)) {
        acc <- 0
        for (k in seq_len(ncol(a))) acc <- acc + a[r, k] * b[k, c]
        row[c] <- acc
      }
      out[[r]] <- row
    }
    render(out)
  }
} else if (cmd == "elem") {
  df <- read_pinned(csv, c(a = "character", b = "character"))
  for (i in seq_len(nrow(df))) {
    a <- parse_mat(df$a[i]); b <- parse_mat(df$b[i])
    render(lapply(seq_len(nrow(a)), function(r) a[r, ] * b[r, ]))
  }
} else if (cmd == "inv2") {
  df <- read_pinned(csv, c(a = "character"))
  for (i in seq_len(nrow(df))) {
    a <- parse_mat(df$a[i])
    det <- a[1, 1] * a[2, 2] - a[1, 2] * a[2, 1]
    if (det == 0) { cat("singular\n"); next }
    render(list(c(a[2, 2] / det, -a[1, 2] / det),
                c(-a[2, 1] / det, a[1, 1] / det)))
  }
} else {
  stop("unknown subcommand")
}
