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
 names<-c('anylower','anyupper','anypunct','anyxdigit','notalpha','notalnum','notspace')
 if(!(name %in% names) || length(args)<1L || length(args)>2L) stop('arity or name')
 b<-ascii(args[[1]]);start<-if(length(args)==2L) args[[2]] else 1
 if(!identical(class(start),'numeric') || length(start)!=1L || is.nan(start)) stop('start type')
 if(is.na(start)) {if(name=='anypunct') stop('conflicting documented missing start');start<-1}
 if(!is.finite(start) || abs(start)>2147483647 || start!=floor(start)) stop('start domain')
 if(start==0 || start>length(b) || !length(b)) return(0L)
 order<-if(start>0) seq.int(start,length(b)) else seq.int(min(-start,length(b)),1L)
 lower<-b>=97L & b<=122L;upper<-b>=65L & b<=90L;digit<-b>=48L & b<=57L
 punctuation<-(b>=33L & b<=47L)|(b>=58L & b<=64L)|(b>=91L & b<=96L)|(b>=123L & b<=126L)
 selected<-switch(name,anylower=lower,anyupper=upper,anypunct=punctuation,anyxdigit=digit|(b>=65L & b<=70L)|(b>=97L & b<=102L),notalpha=!(lower|upper),notalnum=!(lower|upper|digit),notspace=b!=32L)
 positions<-order[selected[order]];if(length(positions)) positions[1L] else 0L
}
decode<-function(x) {kind<-substr(x,1,1);v<-substring(x,3);switch(kind,c=unhex(v),n=as.numeric(v),m=NA_real_,t=structure(v,class='tagged'),b=TRUE,stop('encoding'))}
encode<-function(x) if(is.character(x)) paste0('c:',hex(x)) else if(is.na(x)) 'm:' else paste0('n:',sprintf('%.17g',x))
store<-function(x,w) paste0(substr(x,1,w),strrep(' ',max(0,w-nchar(x,type='bytes'))))
emit<-function(name,row) cat(paste(c('ROW',name,vapply(row,encode,'')),collapse='|'),'\n',sep='')
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
 cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE)
 for(i in seq_len(nrow(cases))) cat(tryCatch(encode(call_value(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
 source<-paste(readLines(args[2],warn=FALSE),collapse='\n');statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);statements<-statements[nzchar(statements)]
 names<-c('anylower','anyupper','anypunct','anyxdigit','notalpha','notalnum','notspace');cols<-c('lower','upper','punct','hexadecimal','nonalpha','nonalnum','nonspace')
 required<-c('data classified','set raw',paste0(cols,'=',names,'(code)'),'back=anylower(code,-99)','output','put punct','put back','run')
 if(!identical(statements,required)) stop('original sequence')
 input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE);if(!identical(names(input),'code')) stop('schema')
 cat('STATEMENTS|',length(statements),'\n',sep='');records<-character()
 for(i in seq_len(nrow(input))) emit('raw',list(store(input$code[i],8L)))
 for(i in seq_len(nrow(input))) {
  code<-store(input$code[i],8L);values<-c(lapply(names,function(name) call_value(name,list(code))),list(call_value('anylower',list(code,-99))))
  emit('classified',c(list(code),values));records<-c(records,paste0(values[[3]],' '),paste0(values[[8]],' '))
 }
 for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
