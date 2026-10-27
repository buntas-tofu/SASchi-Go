# DS-033 original base-R calendar witness for maintainer review, no live SAS.
# Native Date construction/weekday formatting is independent of the Python lane.
arity <- c(mdy=3L, weekday=1L)
epoch <- as.Date('1960-01-01')
low <- as.numeric(as.Date('1753-01-01') - epoch)
high <- as.numeric(as.Date('3999-12-31') - epoch)
integer_value <- function(kind, text, lower, upper) {
  if(kind!='number') stop('numeric input required')
  value <- suppressWarnings(as.numeric(text))
  if(length(value)!=1 || !is.finite(value) || value<lower || value>upper || value!=floor(value))
    stop('finite integral calendar range')
  value
}
calendar <- function(name, values) {
  if(!(name %in% names(arity)) || length(values)!=arity[[name]]) stop('exact call arity')
  if(name=='weekday') {
    value <- integer_value(values[[1]]$kind, values[[1]]$text, low, high)
    return(as.integer(format(as.Date(value, origin='1960-01-01'), '%w'))+1L)
  }
  month <- integer_value(values[[1]]$kind, values[[1]]$text, 1, 12)
  day <- integer_value(values[[2]]$kind, values[[2]]$text, 1, 31)
  year <- integer_value(values[[3]]$kind, values[[3]]$text, 1753, 3999)
  text <- sprintf('%04d-%02d-%02d', year, month, day)
  date <- as.Date(text, format='%Y-%m-%d')
  if(is.na(date) || format(date, '%Y-%m-%d')!=text) stop('valid calendar date required')
  as.numeric(date-epoch)
}
number <- function(text) list(kind='number', text=text)
program <- function(path) {
  # Parse the complete pinned external file in place; no source copy is shipped.
  source <- paste(readLines(path, warn=FALSE), collapse='\n')
  source <- gsub('(?s)/\\*.*?\\*/', '', source, perl=TRUE)
  statements <- trimws(strsplit(source, ';', fixed=TRUE)[[1]])
  statements <- tolower(statements[nzchar(statements)])
  if(length(statements)!=6 || statements[1]!='data _null_' || statements[5]!='end' || statements[6]!='run')
    stop('complete bounded calendar program required')
  capture <- function(pattern, text) {
    parts <- regmatches(text, regexec(pattern, text, perl=TRUE))[[1]]
    if(!length(parts)) stop('statement outside calendar witness')
    parts[-1]
  }
  loop <- capture('^do\\s+([a-z_][a-z0-9_]*)\\s*=\\s*([0-9]+)\\s+to\\s+([0-9]+)$', statements[2])
  assign <- capture('^([a-z_][a-z0-9_]*)\\s*=\\s*mdy\\(\\s*([0-9]+)\\s*,\\s*([0-9]+)\\s*,\\s*([a-z_][a-z0-9_]*)\\s*\\)$', statements[3])
  branch <- capture('^if\\s+weekday\\(\\s*([a-z_][a-z0-9_]*)\\s*\\)\\s*=\\s*([1-7])\\s+then\\s+put\\s+([a-z_][a-z0-9_]*)$', statements[4])
  if(assign[4]!=loop[1] || branch[1]!=assign[1] || branch[3]!=loop[1]) stop('program variable identity')
  start <- integer_value('number', loop[2], 1753, 3999)
  end <- integer_value('number', loop[3], start, 3999)
  years <- seq.int(start, end)
  dates <- vapply(years, function(year) calendar('mdy', list(number(assign[2]), number(assign[3]), number(year))), 0)
  weekdays <- vapply(dates, function(date) calendar('weekday', list(number(date))), 0L)
  records <- paste0(years[weekdays==as.integer(branch[2])], ' ')
  cat('STATE:', end+1L, ':', length(records), '\n', sep='')
  for(record in records) cat('RECORD:', paste(sprintf('%02x', as.integer(charToRaw(record))), collapse=''), '\n', sep='')
}
args <- commandArgs(trailingOnly=TRUE)
if(length(args)!=2) stop('mode and path required')
if(args[1]=='program') {
  program(args[2])
} else if(args[1]=='cases') {
  cases <- read.csv(args[2], colClasses='character', na.strings=NULL, check.names=FALSE)
  for(i in seq_len(nrow(cases))) {
    row <- cases[i, ]; count <- as.integer(row$count)
    values <- lapply(seq_len(min(count, 3L)), function(j) {
      field <- c('a', 'b', 'c')[j]
      list(kind=row[[paste0(field, '_kind')]], text=row[[field]])
    })
    answer <- tryCatch({
      if(!(row$name %in% names(arity)) || count!=arity[[row$name]]) stop('call arity')
      paste0('OK:', sprintf('%.0f', calendar(row$name, values)))
    }, error=function(e) 'REFUSE')
    cat(row$id, ':', answer, '\n', sep='')
  }
} else stop('unknown calendar witness mode')
