# Independent directed KEEP/DROP source witness for maintainer qualification.
# Reuses first-party R source parsing and pairwise insertion, no translator.
script<-sub('^--file=','',grep('^--file=',commandArgs(),value=TRUE)[1L])
source(file.path(dirname(script),'sort_input_drop.R'))
