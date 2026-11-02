# Independent controlled SORT survivor replacement witness for maintainers.
# Reuses only the first-party full-source R oracle; no translator helpers.
script<-sub('^--file=','',grep('^--file=',commandArgs(),value=TRUE)[1L])
source(file.path(dirname(script),'sort_duplicates.R'))
