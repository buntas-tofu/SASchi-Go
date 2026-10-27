# DS-038 native pre-test while control, no live SAS.
args <- commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases <- read.csv(args[2],stringsAsFactors=FALSE)
  for(i in seq_len(nrow(cases))) {
    n <- cases$start[i]; count <- 0L; records <- numeric(0)
    active <- function() if(cases$increment[i]<0) n>cases$stop[i] else n<cases$stop[i]
    while(active()) {
      if(count==10000L) {count <- NA_integer_; break}
      records <- c(records,n); n <- n+cases$increment[i]; count <- count+1L
    }
    if(is.na(count)) cat(i-1,':REFUSE\n',sep='') else
      cat(i-1,':OK:',count,':',sprintf('%.17g',n),':',paste(records,collapse='|'),'\n',sep='')
  }
} else if(args[1]=='program') {
  source <- paste(readLines(args[2],warn=FALSE),collapse='\n')
  source <- gsub('(?s)/\\*.*?\\*/','',source,perl=TRUE)
  st <- tolower(trimws(strsplit(source,';',fixed=TRUE)[[1]])); st <- st[nzchar(st)]
  if(length(st)!=7L || st[1]!='data _null_' || st[6]!='end' || st[7]!='run') stop('complete program required')
  capture <- function(pattern,text) {
    p <- regmatches(text,regexec(pattern,text,perl=TRUE))[[1]]
    if(!length(p)) stop('unhandled program statement')
    p[-1]
  }
  init <- capture('^([a-z_][a-z0-9_]*)\\s*=\\s*([0-9]+)$',st[2])
  test <- capture('^do\\s+while\\(\\s*([a-z_][a-z0-9_]*)\\s*>\\s*0\\s*\\)$',st[3])
  put <- capture('^put\\s+([a-z_][a-z0-9_]*)$',st[4])
  halve <- capture('^([a-z_][a-z0-9_]*)\\s*=\\s*int\\(\\s*([a-z_][a-z0-9_]*)\\s*/\\s*([0-9]+)\\s*\\)$',st[5])
  if(any(c(test,put,halve[1:2])!=init[1])) stop('variable identity')
  n <- as.numeric(init[2]); divisor <- as.numeric(halve[3]); count <- 0L; records <- character(0)
  if(n!=1024 || divisor!=2) stop('pinned full-program profile')
  while(n>0) {
    records <- c(records,paste0(sprintf('%.0f',n),' '))
    n <- trunc(n/divisor); count <- count+1L
    if(count>10000L) stop('witness budget')
  }
  cat('STATE:',n,':',count,'\n',sep='')
  for(record in records) cat('RECORD:',paste(sprintf('%02x',as.integer(charToRaw(record))),collapse=''),'\n',sep='')
} else stop('unknown while witness mode')
