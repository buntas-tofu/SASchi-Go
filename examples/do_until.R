# DS-035 independent native repeat/break witness; no live SAS.
args <- commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases <- read.csv(args[2],stringsAsFactors=FALSE)
  for(i in seq_len(nrow(cases))) {
    n <- cases$start[i]; count <- 0L; records <- numeric(0)
    repeat {
      n <- n + cases$increment[i]; count <- count+1L
      records <- c(records,n)
      if(n >= cases$stop[i]) break
      if(count==10000L) { count <- NA_integer_; break }
    }
    if(is.na(count)) cat(i-1,':REFUSE\n',sep='') else
      cat(i-1,':OK:',count,':',sprintf('%.17g',n),':',
          paste(sprintf('%.17g',records),collapse='|'),'\n',sep='')
  }
} else if(args[1]=='program') {
  # Every statement in the pinned external file is parsed in place.
  source <- paste(readLines(args[2],warn=FALSE),collapse='\n')
  source <- gsub('(?s)/\\*.*?\\*/','',source,perl=TRUE)
  statements <- tolower(trimws(strsplit(source,';',fixed=TRUE)[[1]]))
  statements <- statements[nzchar(statements)]
  if(length(statements)!=7L || statements[1]!='data _null_' ||
     statements[6]!='end' || statements[7]!='run') stop('complete program required')
  capture <- function(pattern,text) {
    found <- regmatches(text,regexec(pattern,text,perl=TRUE))[[1]]
    if(!length(found)) stop('unhandled complete-program statement')
    found[-1]
  }
  initial <- capture('^([a-z_][a-z0-9_]*)\\s*=\\s*([0-9]+)$',statements[2])
  test <- capture('^do\\s+until\\(\\s*mod\\(\\s*([a-z_][a-z0-9_]*)\\s*,\\s*([0-9]+)\\s*\\)\\s*=\\s*0\\s*\\)$',statements[3])
  add <- capture('^([a-z_][a-z0-9_]*)\\s*\\+\\s*([0-9]+)$',statements[4])
  put <- capture('^put\\s+([a-z_][a-z0-9_]*)$',statements[5])
  if(any(c(test[1],add[1],put[1])!=initial[1])) stop('variable identity')
  n <- as.numeric(initial[2]); count <- 0L; records <- character(0)
  repeat {
    n <- n + as.numeric(add[2]); count <- count+1L
    records <- c(records,paste0(sprintf('%.0f',n),' '))
    if(n %% as.numeric(test[2])==0) break
    if(count>=10000L) stop('witness budget')
  }
  cat('STATE:',n,':',count,'\n',sep='')
  for(record in records)
    cat('RECORD:',paste(sprintf('%02x',as.integer(charToRaw(record))),collapse=''),'\n',sep='')
} else stop('unknown UNTIL witness mode')
