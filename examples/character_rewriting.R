# Independent byte selection/mapping and sequential whole-program oracle.
unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
ascii<-function(x,empty=FALSE) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x));if((!empty && !length(b)) || length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  x
}
fold<-function(b) {selected<-b>=65L & b<=90L;b[selected]<-b[selected]+32L;b}
call_value<-function(name,args) {
  if(name=='compress') {
    if(length(args)<1L || length(args)>3L) stop('arity')
    source<-as.integer(charToRaw(ascii(args[[1]])))
    set<-if(length(args)>1L) ascii(args[[2]]) else ' '
    modifier<-if(length(args)>2L) ascii(args[[3]],TRUE) else ''
    if(nchar(set)>64L || !identical(class(modifier),'character') || !(toupper(modifier) %in% c('','I','K','IK','KI'))) stop('options')
    set<-as.integer(charToRaw(set));key<-source
    if(grepl('[iI]',modifier)) {key<-fold(key);set<-fold(set)}
    selected<-key %in% set;if(!grepl('[kK]',modifier)) selected<-!selected
    return(rawToChar(as.raw(source[selected])))
  }
  if(name=='translate') {
    if(length(args)!=3L) stop('arity')
    source<-as.integer(charToRaw(ascii(args[[1]])));to<-as.integer(charToRaw(ascii(args[[2]])));from<-as.integer(charToRaw(ascii(args[[3]])))
    if(length(from)>64L || length(to)!=length(from) || anyDuplicated(from)) stop('mapping')
    positions<-match(source,from);selected<-!is.na(positions);source[selected]<-to[positions[selected]]
    return(rawToChar(as.raw(source)))
  }
  if(name!='tranwrd' || length(args)!=3L) stop('name or arity')
  source<-ascii(args[[1]]);target<-ascii(args[[2]]);replacement<-ascii(args[[3]],TRUE)
  if(nchar(target)>64L || nchar(replacement)>64L) stop('replacement bounds')
  if(!nzchar(replacement)) replacement<-' '
  i<-1L;result<-'';width<-nchar(target)
  while(i<=nchar(source)) {
    if(i+width-1L<=nchar(source) && substr(source,i,i+width-1L)==target) {result<-paste0(result,replacement);i<-i+width}
    else {result<-paste0(result,substr(source,i,i));i<-i+1L}
  }
  if(nchar(result)>200L) stop('result bound')
  result
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
  source<-gsub('(?s)/\\*.*?\\*/','',paste(readLines(args[2],warn=FALSE),collapse='\n'),perl=TRUE)
  statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);statements<-statements[nzchar(statements)]
  required<-c('data edits','set raw','tight=compress(text)',"kept=compress(text,'Ab','IK')","mapped=translate(text,'12','ab')","changed=tranwrd(text,'ab','XY')",'output','put tight','put mapped','run')
  if(!identical(statements,required)) stop('original sequence')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE);cat('STATEMENTS|',length(statements),'\n',sep='')
  for(i in seq_len(nrow(input))) emit('raw',list(store(input$text[i],8L)))
  records<-character()
  for(i in seq_len(nrow(input))) {
    text<-store(input$text[i],8L);tight<-call_value('compress',list(text));kept<-call_value('compress',list(text,'Ab','IK'));mapped<-call_value('translate',list(text,'12','ab'));changed<-call_value('tranwrd',list(text,'ab','XY'))
    emit('edits',list(text,store(tight,8L),store(kept,8L),store(mapped,8L),store(changed,200L)))
    records<-c(records,paste0(trimws(tight,whitespace=' '),' '),paste0(trimws(mapped,whitespace=' '),' '))
  }
  for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
