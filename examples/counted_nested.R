# DS-041 independent base-R schedules and full row witnesses, no live SAS.
args <- commandArgs(trailingOnly=TRUE)
integer_control <- function(x) {
  if (length(x)!=1 || is.na(x) || !is.finite(x) || abs(x)>2147483647 || x!=trunc(x)) stop('control')
  x
}
if (args[1]=='controls') {
  cases <- read.csv(args[2],stringsAsFactors=FALSE)
  for (n in seq_len(nrow(cases))) {
    result <- tryCatch({
      r<-cases[n,]; a<-integer_control(r$start); z<-integer_control(r$stop); b<-integer_control(r$by)
      if (b==0 || r$spent<0 || r$spent>10000 || r$spent!=trunc(r$spent)) stop('control')
      i<-a; visits<-numeric(); used<-r$spent
      while (if(b>0) i<=z else i>=z) {
        used<-used+1
        if(used>10000) stop('budget')
        visits<-c(visits,i); i<-i+b
      }
      paste(length(visits),sprintf('%.0f',i),used,paste(visits,collapse='|'),sep=':')
    },error=function(e) 'REFUSE')
    cat(n-1,':',result,'\n',sep='')
  }
} else if (args[1]=='cases') {
  cases<-read.csv(args[2],stringsAsFactors=FALSE)
  columns<-c('lo','hi','inc','offset','span','stride','total','i','j','tick','after','inner_after')
  cat(paste(c('case',columns),collapse=','),'\n',sep='')
  for(n in seq_len(nrow(cases))) {
    r<-as.list(cases[n,]); r$total<-0; r$i<-NA; r$j<-NA; r$tick<-NA; r$after<-NA; r$inner_after<-NA
    emit<-function() cat(paste(c(n-1,vapply(r[columns],function(x) if(is.na(x)) '' else sprintf('%.0f',x),'')),collapse=','),'\n',sep='')
    # Captured values are ordinary independent R scalars, not translator trees.
    a<-r$lo; z<-r$hi; b<-r$inc; r$i<-a
    while(if(b>0) r$i<=z else r$i>=z) {
      r$lo<-99; r$hi<- -99; r$inc<-7
      c<-r$i+r$offset; d<-r$i+r$span; e<-r$stride; r$j<-c
      while(if(e>0) r$j<=d else r$j>=d) {
        r$total<-r$total+r$j; r$offset<-r$offset+1; r$tick<-1
        emit(); r$j<-r$j+e
      }
      r$i<-r$i+b
    }
    r$after<-r$i; r$inner_after<-r$j; emit()
  }
} else if (args[1]=='program') {
  # Complete independent witness for the original counted_capture.sas.
  columns<-c('first','second','third','start','finish','stride','total','i','j','before','seen','after','inner_after')
  row<-setNames(as.list(rep(NA_real_,length(columns))),columns)
  row$start<-1; row$finish<-3; row$stride<-1; row$total<-0
  cat(paste(columns,collapse=','),'\n',sep='')
  emit<-function() cat(paste(vapply(row,function(x) if(is.na(x)) '' else sprintf('%.0f',x),''),collapse=','),'\n',sep='')
  a<-row$start; z<-row$finish; b<-row$stride; row$i<-a
  while(row$i<=z) {
    row$start<-9; row$finish<-0; row$stride<- -1
    c<-row$i; d<-3; e<-row$i; row$j<-c
    while(row$j<=d) {
      member<-columns[row$j]; row$before<-row[[member]]
      if(is.na(row[[member]])) row[[member]]<-0
      row[[member]]<-row[[member]]+row$i
      row$total<-row$total+row$i; row$seen<-1; emit(); row$j<-row$j+e
    }
    row$i<-row$i+b
  }
  row$after<-row$i; row$inner_after<-row$j; emit()
  cat('LOG:total=8 i=4 j=6\n')
} else stop('unknown witness mode')
