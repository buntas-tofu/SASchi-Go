# Independent source witness entrypoint for the numeric math profile.
args0<-commandArgs(trailingOnly=FALSE)
file0<-sub('^--file=','',args0[grepl('^--file=',args0)][1])
source(file.path(dirname(normalizePath(file0)), 'numeric_math.R'))
