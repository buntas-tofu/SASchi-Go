# Independent byte-array oracle and fixed original-program witness.
unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
MIN_DAY<--75604
MAX_DAY<-745094
MIN_STAMP<--6532185600
MAX_STAMP<-64376207999
integer_value<-function(x,low,high) {
  if(!identical(class(x),'numeric') || length(x)!=1L || is.nan(x)) stop('numeric type')
  if(is.na(x)) return(NA_real_)
  if(!is.finite(x) || x<low || x>high || x!=floor(x)) stop('numeric domain')
  x
}
origin<-as.POSIXct('1960-01-01 00:00:00',tz='UTC')
call_value<-function(name,args) {
  if(name=='dhms') {
    if(length(args)!=4L) stop('arity')
    values<-c(integer_value(args[[1]],MIN_DAY,MAX_DAY),integer_value(args[[2]],0,23),integer_value(args[[3]],0,59),integer_value(args[[4]],0,59))
    if(anyNA(values)) return(NA_real_)
    civil<-paste(format(as.Date(values[1],origin='1960-01-01'),'%Y-%m-%d'),sprintf('%02d:%02d:%02d',as.integer(values[2]),as.integer(values[3]),as.integer(values[4])))
    return(as.numeric(as.POSIXct(civil,format='%Y-%m-%d %H:%M:%S',tz='UTC'))-as.numeric(origin))
  }
  if(length(args)!=1L) stop('arity')
  if(name=='qtr') {
    value<-integer_value(args[[1]],MIN_DAY,MAX_DAY)
    if(is.na(value)) return(NA_real_)
    month<-as.integer(format(as.Date(value,origin='1960-01-01'),'%m'))
    return(ceiling(month/3))
  }
  if(!(name %in% c('datepart','timepart','hour','minute','second'))) stop('name')
  value<-integer_value(args[[1]],MIN_STAMP,MAX_STAMP)
  if(is.na(value)) return(NA_real_)
  civil<-as.POSIXct(value,origin='1960-01-01',tz='UTC')
  if(name=='datepart') return(as.numeric(as.Date(civil,tz='UTC')-as.Date('1960-01-01')))
  parts<-as.numeric(format(civil,c('%H','%M','%S'),tz='UTC'))
  if(name=='timepart') return(sum(parts*c(3600,60,1)))
  parts[match(name,c('hour','minute','second'))]
}
date9<-function(value) {
  if(is.na(value)) return(paste0(strrep(' ',8),'.'))
  civil<-as.Date(value,origin='1960-01-01');month<-as.integer(format(civil,'%m'))
  paste0(format(civil,'%d'),c('JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC')[month],format(civil,'%Y'))
}
decode<-function(x) {kind<-substr(x,1,1);v<-substring(x,3);switch(kind,c=unhex(v),n=as.numeric(v),m=NA_real_,t=structure(v,class='tagged'),b=TRUE,stop('encoding'))}
encode<-function(x) if(is.character(x)) paste0('c:',hex(x)) else if(is.na(x)) 'm:' else paste0('n:',sprintf('%.17g',x))
store<-function(x,w) paste0(substr(x,1,w),strrep(' ',max(0,w-nchar(x,type='bytes'))))
emit<-function(name,row) cat(paste(c('ROW',name,vapply(row,encode,'')),collapse='|'),'\n',sep='')
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
  for(i in seq_len(nrow(cases))) cat(tryCatch(encode(call_value(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
  source<-gsub('(?s)/\\*.*?\\*/','',paste(readLines(args[2],warn=FALSE),collapse='\n'),perl=TRUE)
  statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);statements<-statements[nzchar(statements)]
  required<-c('data stamps','set raw','quarter=qtr(day)','stamp=dhms(day,hr,mn,sc)','recovered=datepart(stamp)','clock=timepart(stamp)','h=hour(stamp)','m=minute(stamp)','s=second(stamp)','shown=put(recovered,date9.)','output','put shown','run')
  if(!identical(statements,required)) stop('original sequence')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
  if(!identical(names(input),c('day','hr','mn','sc'))) stop('input schema')
  number<-function(x) if(!nzchar(x)) NA_real_ else as.numeric(x)
  rows<-lapply(seq_len(nrow(input)),function(i) lapply(input[i,],number))
  cat('STATEMENTS|',length(statements),'\n',sep='')
  for(row in rows) emit('raw',row)
  records<-character()
  for(row in rows) {
    quarter<-call_value('qtr',row[1]);stamp<-call_value('dhms',row)
    components<-lapply(c('datepart','timepart','hour','minute','second'),function(name) call_value(name,list(stamp)))
    shown<-date9(components[[1]])
    emit('stamps',c(row,list(quarter,stamp),components,list(shown)))
    records<-c(records,paste0(trimws(shown,whitespace=' '),' '))
  }
  for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
