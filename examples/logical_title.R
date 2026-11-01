# The shared independent complete-source witness is mixed_reports.R.
args <- commandArgs(trailingOnly=TRUE)
file <- sub('^--file=','',grep('^--file=',commandArgs(),value=TRUE)[1L])
source(file.path(dirname(normalizePath(file)),'mixed_reports.R'))
paths <- readLines(args[1L],warn=FALSE)
for(i in seq_along(paths)) {
  cat('BEGIN ',i,'\n',sep='')
  answer <- tryCatch(render(execute(paste(readLines(paths[i],warn=FALSE),collapse='\n'))),error=function(e)NULL)
  if(is.null(answer))cat('REFUSED\n') else cat(paste(c('OK',answer),collapse='\n'),'\n',sep='')
  cat('END\n')
}
