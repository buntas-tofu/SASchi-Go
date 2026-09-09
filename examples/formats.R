#!/usr/bin/env Rscript
# formats.R : the R half of the PROC FORMAT gate (quirk 18).
#
#   putfmt : fmt:chr, value:chr, type:chr(num|chr) -> label
#
# The format spec rides a mini-DSL, semicolon-joined entries:
#   R:lo:hi:loinc:hiinc=label   range; lo/hi may be L (LOW) or H (HIGH)
#   V:v1,v2=label               exact values (multiple allowed)
#   M=label                     explicit missing
#   O=label                     OTHER
# Rules mirror the reference: inclusive endpoints unless marked, LOW excludes
# numeric missing, missing falls to M then O then '.', fallthrough renders
# the value itself, character keys strip trailing blanks (quirk-9 collation).

args <- commandArgs(trailingOnly = TRUE)
csv <- args[1]

df <- read.csv(csv, colClasses = "character", quote = "\"")
cat("n=", nrow(df), "\n", sep = "")

key <- function(v, num) if (num) as.numeric(v) else sub(" +$", "", v)

put_fmt <- function(spec, raw, num) {
  val <- if (num) suppressWarnings(as.numeric(raw)) else raw
  missing <- num && is.na(val)
  entries <- strsplit(spec, ";", fixed = TRUE)[[1]]
  m_label <- NA; o_label <- NA
  if (!missing) {
    kv <- key(raw, num)
    for (e in entries) {
      kvpair <- strsplit(e, "=", fixed = TRUE)[[1]]
      body <- kvpair[1]; label <- kvpair[2]
      p <- strsplit(body, ":", fixed = TRUE)[[1]]
      if (p[1] == "V") {
        vals <- strsplit(p[2], ",", fixed = TRUE)[[1]]
        for (v in vals) if (identical(key(v, num), kv)) return(label)
      } else if (p[1] == "R") {
        lo <- p[2]; hi <- p[3]
        lo_inc <- p[4] == "1"; hi_inc <- p[5] == "1"
        lo_ok <- lo == "L" || kv > key(lo, num) ||
          (lo_inc && kv == key(lo, num))
        hi_ok <- hi == "H" || kv < key(hi, num) ||
          (hi_inc && kv == key(hi, num))
        if (lo_ok && hi_ok) return(label)
      }
    }
  }
  for (e in entries) {
    kvpair <- strsplit(e, "=", fixed = TRUE)[[1]]
    if (kvpair[1] == "M") m_label <- kvpair[2]
    if (kvpair[1] == "O") o_label <- kvpair[2]
  }
  if (missing) {
    if (!is.na(m_label)) return(m_label)
    if (!is.na(o_label)) return(o_label)
    return(".")
  }
  if (!is.na(o_label)) return(o_label)
  if (num && val == as.integer(val)) return(format(as.integer(val)))
  if (num) return(format(val))
  sub(" +$", "", raw)
}

for (i in seq_len(nrow(df)))
  cat(put_fmt(df$fmt[i], df$value[i], df$type[i] == "num"), "\n", sep = "")
