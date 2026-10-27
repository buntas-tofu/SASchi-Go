# DS-034 independent native R sums and prefix witness; no live SAS.
args <- commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases <- read.csv(args[2], colClasses='character', na.strings=NULL)
  value <- function(kind, text) {
    if(kind=='missing') return(NA_real_)
    if(kind!='number') stop('ordinary numeric only')
    n <- suppressWarnings(as.numeric(text))
    if(!is.finite(n)) stop('finite binary64 only')
    n
  }
  for(i in seq_len(nrow(cases))) {
    row <- cases[i, ]
    answer <- tryCatch({
      a <- value(row$a_kind,row$a); b <- value(row$b_kind,row$b)
      n <- sum(c(a,b),na.rm=TRUE)
      if(!is.finite(n)) stop('overflow')
      paste0('OK:',sprintf('%.17g',n))
    },error=function(e) 'REFUSE')
    cat(row$id,':',answer,'\n',sep='')
  }
} else if(args[1]=='program') {
  x <- c(NA,2,-.5,NA,4)
  # Cumulative zero-filled increments, independent of pairwise Python state.
  total <- 10 + cumsum(replace(x,is.na(x),0))
  cat(paste(sprintf('%.17g',total),collapse='|'),'\n',sep='')
} else stop('unknown sum witness mode')
