# DS-037 native R truncation outside a conservative fuzz band, no live SAS.
args <- commandArgs(trailingOnly=TRUE)
cases <- read.csv(args[1],colClasses='character',na.strings=NULL)
for(i in seq_len(nrow(cases))) {
  r <- cases[i,]
  answer <- tryCatch({
    if(r$kind!='number') stop('numeric only')
    x <- suppressWarnings(as.numeric(r$value))
    if(!is.finite(x) || abs(x)>2147483647) stop('finite bounded number required')
    if(x!=trunc(x) && abs(x-round(x))<=2e-12) stop('INT fuzz review')
    paste0('OK:',sprintf('%.0f',trunc(x)))
  },error=function(e) 'REFUSE')
  cat(r$id,':',answer,'\n',sep='')
}
