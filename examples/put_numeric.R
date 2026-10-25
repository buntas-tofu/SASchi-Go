# DS-027 independent base-R numeric list witness. Original repository fixture,
# not a live SAS capture. CSV type tags preserve ordinary missing and refusals.
render_numeric <- function(fields) {
  if (!nrow(fields)) stop('nonempty value list')
  values <- vapply(seq_len(nrow(fields)), function(i) {
    if (fields$type[i] == 'missing') return('.')
    if (fields$type[i] != 'number') stop('ordinary numeric')
    x <- suppressWarnings(as.numeric(fields$value[i]))
    if (!is.finite(x) || abs(x) > 99999999999 || x != trunc(x))
      stop('whole numbers')
    if (x == 0) '0' else sprintf('%.0f', x)
  }, character(1))
  record <- paste0(paste0(values, ' '), collapse='')
  if (nchar(record, type='bytes') > 64L) stop('LINESIZE')
  record
}

hex <- function(text) paste(sprintf('%02x', as.integer(charToRaw(text))), collapse='')
args <- commandArgs(trailingOnly=TRUE)
if (length(args) != 1L) stop('usage: Rscript put_numeric.R cases.csv')
cases <- read.csv(args[1], colClasses='character', na.strings=NULL, check.names=FALSE)
for (id in unique(cases$id)) {
  fields <- cases[cases$id == id & cases$type != 'empty', , drop=FALSE]
  result <- tryCatch(paste0('OK:', hex(render_numeric(fields))),
                     error=function(e) paste0('ERROR:', conditionMessage(e)))
  cat(result, '\n', sep='')
}
