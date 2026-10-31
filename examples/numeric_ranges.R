# DS-062 independent source-witness entrypoint; shares the D2b R interpreter.
args<-commandArgs(trailingOnly=TRUE)
self<-sub('^--file=','',grep('^--file=',commandArgs(),value=TRUE)[1])
source(file.path(dirname(normalizePath(self)),'numeric_exchange.R'))
