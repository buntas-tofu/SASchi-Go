# Original DS-007 executable-slice witness for maintainer review, no live SAS.
# This model addresses prior invoked row indices; it never shifts or mutates queues.
args<-commandArgs(trailingOnly=TRUE)
tok<-function(x) if(is.na(x)) '.' else sprintf('%.17g',x)
read_value<-function(token) {
  if(token=='M') return(NA_real_)
  if(substr(token,1,2)!='N:') stop('numeric type')
  value<-suppressWarnings(as.numeric(substring(token,3)))
  if(length(value)!=1 || !is.finite(value)) stop('finite binary64')
  value
}
if(args[1]=='values') {
  for(token in readLines(args[2],warn=FALSE)) {
    value<-tryCatch({read_value(token);'OK'},error=function(e)'REFUSE')
    cat(value,'\n',sep='')
  }
} else if(args[1]=='cases') {
  rows<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE)
  cat('id,row,x,flag,cond_lag,cond_dif,full_lag,full_dif,used\n')
  for(id in unique(rows$id)) {
    case<-rows[rows$id==id,,drop=FALSE]
    n<-as.integer(case$depth[1]);if(is.na(n)||n<1||n>100)stop('depth')
    values<-vapply(case$x,read_value,0.);flags<-vapply(case$flag,read_value,0.)
    selected<-which(!is.na(flags)&flags!=0);all_rows<-seq_along(values)
    previous<-function(invocations,difference=FALSE) {
      answer<-rep(NA_real_,length(values))
      for(j in seq_along(invocations)) {
        if(j<=n) next
        current<-invocations[j];prior<-invocations[j-n]
        answer[current]<-if(difference) values[current]-values[prior] else values[prior]
        if(!is.na(answer[current])&&!is.finite(answer[current]))stop('DIF overflow')
      }
      answer
    }
    cl<-previous(selected);cd<-previous(selected,TRUE)
    fl<-previous(all_rows);fd<-previous(all_rows,TRUE)
    used<-rep(NA_real_,length(values));used[selected]<-fl[selected]
    for(i in all_rows) cat(paste(c(id,i,vapply(c(values[i],flags[i],cl[i],cd[i],fl[i],fd[i],used[i]),tok,'')),collapse=','),'\n',sep='')
  }
} else stop('unknown witness mode')
