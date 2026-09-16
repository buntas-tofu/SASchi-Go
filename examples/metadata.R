# Original typed metadata witnesses; JSON/SAS-file import is outside this gate.
id <- c('007', '002')
day <- c(0,1)
attr(day, 'format') <- 'DATE9.'
attr(day, 'label') <- 'Day'
text <- c('\u00e9\u00e9', '\u5317 ')
rank <- c('._'=0, '.'=1, '.A'=2, '.Z'=27, '-4'=28, '3'=29)
missing <- c('3', '.Z', '.', '.A', '._', '-4')
fixed_ascii <- function(value, width) {
  bytes <- charToRaw(value)
  rawToChar(c(head(bytes,width), rep(as.raw(32), max(0,width-length(bytes)))))
}
cat(paste(c('id',id),collapse='|'), '\n', sep='')
cat(paste(c('day',day),collapse='|'), '\n', sep='')
cat('format|',attr(day,'format'),'\n',sep='')
cat('label|',attr(day,'label'),'\n',sep='')
cat(paste(c('text_bytes',nchar(text,type='bytes')),collapse='|'), '\n', sep='')
cat(paste(c('missing',missing[order(unname(rank[missing]))]),collapse='|'), '\n', sep='')
cat('width|',fixed_ascii('WXYZ',1),'|',fixed_ascii('WXYZ',5),'\n',sep='')
stopifnot(!identical(id, as.numeric(id)), !identical('.A', '.Z'))
