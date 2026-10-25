# Original DS-026 Base DATA-step control witness. Repository evidence, no live SAS.
# R's for-loop index is deliberately avoided: it keeps the last visited value.
args <- commandArgs(trailingOnly=TRUE)
if (args[1] == "controls") {
  cases <- read.csv(args[2], stringsAsFactors=FALSE)
  cat("id,count,final,values\n")
  for (row in seq_len(nrow(cases))) {
    a <- cases$start[row]; z <- cases$stop[row]; b <- cases$by[row]
    valid <- all(is.finite(c(a,z,b))) && all(c(a,z,b) == trunc(c(a,z,b))) &&
      all(abs(c(a,z,b)) <= 2147483647) && b != 0
    if (!valid) { cat(cases$id[row], ",REFUSE,,\n", sep=""); next }
    current <- a; values <- numeric(0)
    while (if (b > 0) current <= z else current >= z) {
      values <- c(values, current)
      if (length(values) > 10000) break
      current <- current + b
    }
    if (length(values) > 10000) { cat(cases$id[row], ",REFUSE,,\n", sep=""); next }
    cat(cases$id[row], ",", length(values), ",", sprintf("%.0f", current), ",",
        paste(sprintf("%.0f", values), collapse="|"), "\n", sep="")
  }
} else if (args[1] == "program") {
  cat("i,total,seen\n")
  # Independent witness for ORIGINAL_PROGRAM in verify_do_counted.py.
  total <- 0; i <- 5; data_iteration <- 1
  while (i >= -1) {
    total <- total + i
    cat(sprintf("%.0f,%.0f,%.0f\n", i,total,data_iteration))
    i <- i - 2
  }
  # Explicit OUTPUT inside the loop suppresses bottom-of-step output.
} else stop("unknown witness mode")
