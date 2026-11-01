# Separate labelled-PRINT registered entry point; shared independent R scheduler.
argument<-grep('^--file=',commandArgs(),value=TRUE)
source(file.path(dirname(normalizePath(sub('^--file=','',argument[1L]))),'informat_reports.R'))
report_main()
