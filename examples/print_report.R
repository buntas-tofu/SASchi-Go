# First-party shared full-source procedure oracle, separate registered PRINT gate.
args<-commandArgs(trailingOnly=FALSE)
file<-sub('^--file=','',args[grepl('^--file=',args)][1])
source(file.path(dirname(normalizePath(file)),'procedures.R'),chdir=FALSE)
