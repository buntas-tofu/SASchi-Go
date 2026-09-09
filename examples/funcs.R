#!/usr/bin/env Rscript
# funcs.R : R translations of SAS MAX/MIN (ignore missing) and the LENGTH family
# (trailing-blank exclusion, floor of 1), built from the same rule as
# sas_semantics.py so the verifier proves agreement. Two modes.

sas_max <- function(v) { v <- v[!is.na(v)]; if (length(v) == 0) NA_real_ else max(v) }
sas_min <- function(v) { v <- v[!is.na(v)]; if (length(v) == 0) NA_real_ else min(v) }
sas_length  <- function(x) { if (is.na(x)) return(1L); s <- sub("[ ]+$", "", x); if (nchar(s) == 0) 1L else nchar(s) }
sas_lengthn <- function(x) { if (is.na(x)) return(0L); nchar(sub("[ ]+$", "", x)) }
sas_lengthc <- function(x) { if (is.na(x)) return(0L); nchar(x) }
# SAS char->num: trim, accept only the standard numeric informat, else missing.
# Uses the same regex as sas_semantics.py, NOT R's as.numeric (which would read
# "0x10" as 16). The regex is the gate; as.numeric only parses what it passes.
sas_charnum <- function(x) {
  if (is.na(x)) return(NA_real_)
  t <- trimws(x)
  if (t == "" || !grepl("^[+-]?([0-9]+\\.?[0-9]*|\\.[0-9]+)([eE][+-]?[0-9]+)?$", t)) return(NA_real_)
  as.numeric(t)
}

args <- commandArgs(trailingOnly = TRUE)
mode <- args[1]
# blank.lines.skip = FALSE so a lone empty-string fixture ("") is not dropped as
# a blank line; char->num must test it, and a dropped row silently misaligns.
fx <- read.csv(args[2], stringsAsFactors = FALSE, colClasses = "character",
               blank.lines.skip = FALSE)

if (mode == "length") {
  for (i in seq_len(nrow(fx))) {
    base <- fx$base[i]; if (is.na(base)) base <- ""
    nt <- as.integer(fx$n_trail[i])
    s <- paste0(base, strrep(" ", nt))
    cat(sas_length(s), sas_lengthn(s), sas_lengthc(s), "\n")
  }
} else if (mode == "maxmin") {
  for (i in seq_len(nrow(fx))) {
    parts <- strsplit(fx$nums[i], ";", fixed = TRUE)[[1]]
    v <- suppressWarnings(as.numeric(ifelse(parts == "NA", NA, parts)))
    cat(sas_max(v), sas_min(v), "\n")
  }
} else if (mode == "substr") {
  for (i in seq_len(nrow(fx))) {
    s <- fx$s[i]; if (is.na(s)) s <- ""
    pos <- as.integer(fx$pos[i]); ln <- fx$len[i]
    if (is.na(ln) || ln == "") cat(substr(s, pos, nchar(s)), "\n", sep = "")
    else cat(substr(s, pos, pos + as.integer(ln) - 1L), "\n", sep = "")
  }
} else if (mode == "evaldiv") {
  # SAS %EVAL integer division truncates toward zero; R's %/% floors, so use trunc.
  for (i in seq_len(nrow(fx))) {
    a <- as.integer(fx$a[i]); b <- as.integer(fx$b[i])
    cat(trunc(a / b), "\n", sep = "")
  }
} else if (mode == "charnum") {
  for (i in seq_len(nrow(fx))) {
    s <- fx$s[i]; if (is.na(s)) s <- ""
    v <- sas_charnum(s)
    cat(if (is.na(v)) "NA" else format(v, scientific = FALSE, trim = TRUE), "\n", sep = "")
  }
}
