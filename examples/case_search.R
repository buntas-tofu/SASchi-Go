# Original independent ASCII byte and sequential program witness, no live SAS.
unhex <- function(x) {
  if(!nzchar(x)) return('')
  rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))
}
hex <- function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
ascii <- function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character required')
  bytes<-as.integer(charToRaw(x))
  if(length(bytes)<1L || length(bytes)>32767L || any(bytes<32L | bytes>126L)) stop('ASCII bounds')
  x
}
case_bytes <- function(x,upper) {
  bytes<-as.integer(charToRaw(ascii(x)))
  selected<-if(upper) bytes>=97L & bytes<=122L else bytes>=65L & bytes<=90L
  bytes[selected]<-bytes[selected]+if(upper) -32L else 32L
  rawToChar(as.raw(bytes))
}
position <- function(source,needle,start=1) {
  if(start==0 || start>nchar(source,type='bytes')) return(0)
  last<-nchar(source,type='bytes')-nchar(needle,type='bytes')+1L
  if(start>last) return(0)
  for(i in seq.int(start,last)) if(substr(source,i,i+nchar(needle,type='bytes')-1L)==needle) return(i)
  0
}
call_value <- function(name,values) {
  count<-length(values)
  if(name %in% c('upcase','lowcase')) {
    if(count!=1L) stop('arity')
    return(case_bytes(values[[1]],name=='upcase'))
  }
  if(name=='index') {
    if(count!=2L) stop('arity')
    return(position(ascii(values[[1]]),ascii(values[[2]])))
  }
  if(name!='find' || count<2L || count>4L) stop('name or arity')
  source<-ascii(values[[1]]);needle<-ascii(values[[2]])
  modifier<-'';start<-1;have_text<-FALSE;have_number<-FALSE
  if(count>2L) for(v in values[3:count]) {
    if(is.character(v)) {
      if(have_text || !identical(class(v),'character') || length(v)!=1L || is.na(v) || nchar(v)>8L || grepl('[^iItT]',v)) stop('modifier')
      modifier<-v;have_text<-TRUE
    } else {
      if(have_number || !is.numeric(v) || length(v)!=1L || !is.finite(v) || v!=trunc(v) || v<0 || v>2147483647) stop('start')
      start<-v;have_number<-TRUE
    }
  }
  if(grepl('[tT]',modifier)) {source<-sub(' +$','',source);needle<-sub(' +$','',needle)}
  if(!nzchar(needle)) stop('empty trimmed needle')
  if(grepl('[iI]',modifier)) {source<-case_bytes(if(nzchar(source)) source else ' ',TRUE);needle<-case_bytes(needle,TRUE)}
  position(source,needle,start)
}
decode <- function(x) {
  kind<-substr(x,1,1);value<-substring(x,3)
  if(kind=='c') return(unhex(value))
  if(kind=='n') return(as.numeric(value))
  if(kind=='m') return(NA_real_)
  if(kind=='t') return(structure(value,class='tagged'))
  if(kind=='b') return(TRUE)
  stop('encoding')
}
encode <- function(x) {
  if(is.character(x)) paste0('c:',hex(x)) else if(is.na(x)) 'm:' else paste0('n:',sprintf('%.17g',x))
}
store <- function(x,width) paste0(substr(x,1,width),strrep(' ',max(0,width-nchar(x,type='bytes'))))
emit_row <- function(table,row) cat(paste(c('ROW',table,vapply(row,encode,'')),collapse='|'),'\n',sep='')
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE)
  for(i in seq_len(nrow(cases))) {
    values<-lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode)
    result<-tryCatch(encode(call_value(cases$name[i],values)),error=function(e) 'REFUSE')
    cat(result,'\n',sep='')
  }
} else if(args[1]=='program') {
  source<-paste(readLines(args[2],warn=FALSE),collapse='\n')
  source<-gsub('(?s)/\\*.*?\\*/','',source,perl=TRUE)
  statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]])
  statements<-statements[nzchar(statements)]
  required<-c('data clean','length short $3','set raw','upper=upcase(key)','lower=lowcase(key)',
    'short=upcase(key)','first=index(key,needle)',"folded=find(key,needle,'IT')","after=find(key,'a',2,'I')",
    'if first then output','output','put upper','put folded','run','data reset',"key='Q'",'upper=upcase(key)',
    "first=index(key,'q')",'output','run')
  if(!identical(statements,required)) stop('original source sequence changed')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE)
  records<-character()
  cat('STATEMENTS|',length(statements),'\n',sep='')
  for(i in seq_len(nrow(input))) emit_row('raw',list(store(input$key[i],8L),store(input$needle[i],2L)))
  for(i in seq_len(nrow(input))) {
    key<-store(input$key[i],8L);needle<-store(input$needle[i],2L)
    upper<-case_bytes(key,TRUE);lower<-case_bytes(key,FALSE)
    first<-position(key,needle)
    folded<-call_value('find',list(key,needle,'IT'))
    after<-call_value('find',list(key,'a',2,'I'))
    row<-list(store(upper,3L),key,needle,upper,lower,first,folded,after)
    if(first!=0) emit_row('clean',row)
    emit_row('clean',row)
    records<-c(records,paste0(trimws(upper,whitespace=' '),' '),paste0(folded,' '))
  }
  emit_row('reset',list('Q','Q',0))
  for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
