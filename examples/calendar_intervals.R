# Independent Gregorian date/boundary arithmetic and original full-source witness.
unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
number<-function(x) {
  if(!is.numeric(x) || length(x)!=1L || is.nan(x)) stop('number')
  if(is.na(x)) return(NA_real_)
  if(!is.finite(x) || x!=trunc(x)) stop('integer');x
}
date_value<-function(x) {
  n<-number(x);d<-as.Date(n,origin='1960-01-01')
  if(!is.na(d) && (d<as.Date('1753-01-01') || d>as.Date('3999-12-31'))) stop('date domain');d
}
control<-function(x,allowed) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x) || !(toupper(x) %in% allowed)) stop('literal control')
  toupper(x)
}
components<-function(d) as.integer(c(format(d,'%Y'),format(d,'%m'),format(d,'%d')))
month_date<-function(index,day=1L) as.Date(sprintf('%04d-%02d-%02d',index%/%12,index%%12+1L,day))
call_value<-function(name,args) {
  if(name %in% c('year','month','day')) {
    if(length(args)!=1L) stop('arity')
    d<-date_value(args[[1]]);if(is.na(d)) return(NA_real_)
    return(components(d)[match(name,c('year','month','day'))])
  }
  if(!(name %in% c('intck','intnx')) || length(args)<3L || length(args)>4L) stop('arity/name')
  interval<-control(args[[1]],c('DAY','MONTH','QTR','YEAR'));d<-date_value(args[[2]])
  if(name=='intck') {
    end<-date_value(args[[3]])
    if(length(args)==4L) control(args[[4]],c('D','DISCRETE'))
    if(is.na(d) || is.na(end)) return(NA_real_)
    if(interval=='DAY') return(as.numeric(end-d))
    a<-components(d);b<-components(end)
    index<-function(x) if(interval=='YEAR') x[1] else if(interval=='QTR') x[1]*4+(x[2]-1L)%/%3 else x[1]*12+x[2]-1L
    return(index(b)-index(a))
  }
  increment<-number(args[[3]]);if(!is.na(increment) && abs(increment)>10000) stop('increment')
  alignment<-if(length(args)==4L) control(args[[4]],c('B','BEGINNING','E','END','S','SAME','SAMEDAY')) else 'B'
  if(is.na(d) || is.na(increment)) return(NA_real_)
  if(interval=='DAY') out<-d+increment else {
    c<-components(d);step<-switch(interval,MONTH=1L,QTR=3L,YEAR=12L);index<-c[1]*12+c[2]-1L
    anchor<-index%/%step*step+increment*step;first<-month_date(anchor);last<-month_date(anchor+step)-1
    if(alignment %in% c('B','BEGINNING')) out<-first else if(alignment %in% c('E','END')) out<-last else {
      offset<-if(interval=='YEAR') c[2]-1L else if(interval=='QTR') (c[2]-1L)%%3L else 0L
      target<-anchor+offset;last_day<-as.integer(format(month_date(target+1L)-1,'%d'))
      out<-month_date(target,min(c[3],last_day))
    }
  }
  if(is.na(out) || out<as.Date('1753-01-01') || out>as.Date('3999-12-31')) stop('result date domain')
  as.numeric(out-as.Date('1960-01-01'))
}
decode<-function(x) {kind<-substr(x,1,1);v<-substring(x,3);switch(kind,c=unhex(v),n=as.numeric(v),m=NA_real_,t=structure(v,class='tagged'),b=TRUE,stop('encoding'))}
encode<-function(x) if(is.character(x)) paste0('c:',hex(x)) else if(is.na(x)) 'm:' else paste0('n:',sprintf('%.17g',x))
emit<-function(name,row) cat(paste(c('ROW',name,vapply(row,encode,'')),collapse='|'),'\n',sep='')
date9<-function(days) {c<-components(date_value(days));paste0(sprintf('%02d',c[3]),c('JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC')[c[2]],sprintf('%04d',c[1]))}
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE)
  for(i in seq_len(nrow(cases))) cat(tryCatch(encode(call_value(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
  source<-gsub('(?s)/\\*.*?\\*/','',paste(readLines(args[2],warn=FALSE),collapse='\n'),perl=TRUE)
  statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);statements<-statements[nzchar(statements)]
  required<-c('data cohorts','set raw','year=year(d)','month=month(d)','day=day(d)',"months=intck('MONTH',d,ending)","back=intck('MONTH',ending,d)","shifted=intnx('MONTH',d,move,'S')","boundary=intnx('MONTH',d,move,'E')",'shown=put(shifted,date9.)','output','put shown','run')
  if(!identical(statements,required)) stop('original sequence')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE);cat('STATEMENTS|',length(statements),'\n',sep='')
  rows<-lapply(seq_len(nrow(input)),function(i) lapply(input[i,],as.numeric));for(row in rows) emit('raw',row)
  records<-character()
  for(row in rows) {
    d<-row[[1]];end<-row[[2]];increment<-row[[3]];shifted<-call_value('intnx',list('MONTH',d,increment,'S'));shown<-date9(shifted)
    emit('cohorts',c(row,list(call_value('year',list(d)),call_value('month',list(d)),call_value('day',list(d)),call_value('intck',list('MONTH',d,end)),call_value('intck',list('MONTH',end,d)),shifted,call_value('intnx',list('MONTH',d,increment,'E')),shown)))
    records<-c(records,paste0(shown,' '))
  }
  for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
