# DS-046 independent static PDV discovery and scalar scheduling witness.
args <- commandArgs(trailingOnly=TRUE)
cases <- read.csv(args[1],colClasses='character',na.strings=NULL)
render <- function(x) ifelse(is.na(x),'.',sprintf('%.0f',x))
for(i in seq_len(nrow(cases))) {
  r <- cases[i,]; a <- if(r$a=='.') NA_real_ else as.numeric(r$a)
  schema <- if(r$mode=='zero') c('a','i','c','d') else c('a','c','d')
  pdv <- setNames(rep(NA_real_,length(schema)),schema);pdv['a'] <- a
  if(r$mode=='zero') pdv['i'] <- 1
  first <- paste(render(pdv),collapse=',')
  pdv['c'] <- a+1
  last <- paste(render(pdv),collapse=',')
  records <- c(if(r$mode=='direct') '. . ',paste0(paste(render(pdv[c('a','c','d')]),collapse=' '),' '))
  count <- if(r$mode=='else') 3 else 2
  cat(r$id,paste(schema,collapse=','),first,last,count,paste(records,collapse='|'),'\n',sep='\t')
}
