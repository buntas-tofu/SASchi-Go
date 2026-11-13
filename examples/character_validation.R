# Independent byte-array oracle and fixed original-program witness.
unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
call_value<-function(name,args) {
  names<-c('anyalpha','anydigit','anyalnum','anyspace','notdigit')
  if(name=='verify') {
    if(length(args)<2L || length(args)>32L) stop('VERIFY arity')
    all<-lapply(args,ascii);allowed<-unlist(all[-1L]);positions<-which(!(all[[1]] %in% allowed))
    return(if(length(positions)) positions[1L] else 0L)
  }
  if(!(name %in% names) || length(args)<1L || length(args)>2L) stop('ANY arity')
  b<-ascii(args[[1]]);start<-if(length(args)==2L) args[[2]] else 1
  if(!identical(class(start),'numeric') || length(start)!=1L) stop('start type')
  if(is.na(start)) start<-1
  if(!is.finite(start) || abs(start)>2147483647 || start!=floor(start)) stop('start domain')
  if(start==0 || start>length(b) || !length(b)) return(0L)
  order<-if(start>0) seq.int(start,length(b)) else seq.int(min(-start,length(b)),1L)
  alpha<-(b>=65L & b<=90L) | (b>=97L & b<=122L);digit<-b>=48L & b<=57L
  selected<-switch(name,anyalpha=alpha,anydigit=digit,anyalnum=alpha|digit,anyspace=b==32L,notdigit=!digit)
  positions<-order[selected[order]]
  if(length(positions)) positions[1L] else 0L
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
  required<-c('data checked','set raw',"verified=verify(code,'0123456789')",'alpha=anyalpha(code)','digit=anydigit(code)','alnum=anyalnum(code)','space=anyspace(code)','other=notdigit(code)','back=anydigit(code,-99)','output',"if code ne '      ' then put code",'put verified','put other','run')
  if(!identical(statements,required)) stop('original sequence')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
  if(!identical(names(input),'code')) stop('input schema')
  cat('STATEMENTS|',length(statements),'\n',sep='')
  for(i in seq_len(nrow(input))) emit('raw',list(store(input$code[i],6L)))
  records<-character()
  for(i in seq_len(nrow(input))) {
    code<-store(input$code[i],6L)
    verified<-call_value('verify',list(code,'0123456789'))
    values<-lapply(c('anyalpha','anydigit','anyalnum','anyspace','notdigit'),function(name) call_value(name,list(code)))
    back<-call_value('anydigit',list(code,-99))
    emit('checked',c(list(code,verified),values,list(back)))
    if(any(ascii(code)!=32L)) records<-c(records,paste0(trimws(code,whitespace=' '),' '))
    records<-c(records,paste0(verified,' '),paste0(values[[5]],' '))
  }
  for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
