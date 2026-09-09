#!/usr/bin/env Rscript
# arrays.R : the R half of the arrays gate (quirk 19).
#
# usage: arrays.R <scenario>
# Fixed scenarios, printed end-states, compared verbatim by the verifier.
# The engine aliases through an environment, because an R vector copies on
# assignment and silently divorces from the variables: the exact landmine
# the reference pins. Bounds arithmetic mirrors sas_array (custom lower
# bounds, halt on out-of-range).

mk_array <- function(env, names, lo = 1) list(env = env, names = names, lo = lo)

arr_idx <- function(a, i) {
  j <- i - a$lo + 1
  if (j < 1 || j > length(a$names)) stop("array subscript out of range")
  a$names[j]
}

arr_get <- function(a, i) get(arr_idx(a, i), envir = a$env)
arr_set <- function(a, i, v) assign(arr_idx(a, i), v, envir = a$env)

scenario <- commandArgs(trailingOnly = TRUE)[1]

if (scenario == "alias") {
  env <- new.env()
  assign("x1", 1, envir = env); assign("x2", 2, envir = env)
  assign("x3", 3, envir = env)
  a <- mk_array(env, c("x1", "x2", "x3"))
  arr_set(a, 2, 99)
  assign("x3", 7, envir = env)
  cat(get("x2", envir = env), arr_get(a, 3), length(a$names), a$lo,
      a$lo + length(a$names) - 1, sep = "|")
  cat("\n")
} else if (scenario == "census") {
  env <- new.env()
  for (y in 1990:1995) assign(paste0("y", y), y - 1990 + 10, envir = env)
  a <- mk_array(env, paste0("y", 1990:1995), lo = 1990)
  cat(arr_get(a, 1993), a$lo, a$lo + length(a$names) - 1, length(a$names),
      sep = "|")
  cat("\n")
} else if (scenario == "oob") {
  env <- new.env(); assign("y1990", 10, envir = env)
  a <- mk_array(env, c("y1990"), lo = 1990)
  out <- tryCatch({arr_get(a, 1989); "NO-HALT"}, error = function(e) "HALT")
  cat(out, "\n", sep = "")
} else if (scenario == "retain") {
  tempenv <- new.env(); assign("t1", 0, envir = tempenv)
  tmp <- mk_array(tempenv, c("t1"))
  normal_last <- NA
  for (iter in 1:2) {
    iterenv <- new.env(); assign("x", NA, envir = iterenv)  # PDV reset
    arr_set(tmp, 1, arr_get(tmp, 1) + 5)
    normal_last <- get("x", envir = iterenv)
  }
  cat(arr_get(tmp, 1), "|", ifelse(is.na(normal_last), "NA", normal_last),
      "\n", sep = "")
} else {
  stop("unknown scenario")
}
