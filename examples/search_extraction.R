# Independent byte-array oracle and fixed original-program witness.
unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
integer_value<-function(x,missing=FALSE) {
  if(!identical(class(x),'numeric') || length(x)!=1L || is.nan(x)) stop('numeric type')
  if(is.na(x)) {if(missing) return(NA_real_);stop('missing numeric')}
  if(!is.finite(x) || abs(x)>2147483647 || x!=floor(x)) stop('numeric domain')
  x
}
positions<-function(n,start) {
  start<-integer_value(start)
  if(!n || start==0 || start>n) return(integer())
  if(start>0) seq.int(start,n) else seq.int(min(-start,n),1L)
}
fold<-function(b) {chosen<-b>=65L & b<=90L;b[chosen]<-b[chosen]+32L;b}
options<-function(args,allowed) {
  modifier<-NULL;start<-NULL
  for(x in args) {
    if(identical(class(x),'character')) {
      ascii(x)
      if(!is.null(modifier) || !(toupper(x) %in% allowed)) stop('modifier')
      modifier<-toupper(x)
    } else {
      if(!is.null(start)) stop('duplicate start')
      start<-integer_value(x)
    }
  }
  list(modifier=if(is.null(modifier)) '' else modifier,start=if(is.null(start)) 1 else start)
}
word_match<-function(source,word,delimiters,order) {
  n<-length(source);m<-length(word)
  for(i in order) {
    end<-i+m-1L
    if(end>n || !m) next
    if(!identical(source[seq.int(i,end)],word)) next
    if((i==1L || source[i-1L] %in% delimiters) && (end==n || source[end+1L] %in% delimiters)) return(i)
  }
  0L
}
call_value<-function(name,args) {
  if(name=='indexc') {
    if(length(args)<2L || length(args)>32L) stop('arity')
    bytes<-lapply(args,ascii);found<-which(bytes[[1]] %in% unlist(bytes[-1L]))
    return(if(length(found)) found[1L] else 0L)
  }
  if(name=='substrn') {
    if(length(args)<2L || length(args)>3L) stop('arity')
    b<-ascii(args[[1]]);position<-integer_value(args[[2]],TRUE)
    count<-if(length(args)==3L) integer_value(args[[3]],TRUE) else length(b)-position+1
    if(is.na(position) || is.na(count) || count<=0) return('')
    last<-min(length(b),position+count-1);first<-max(1,position)
    if(first>last) return('')
    return(rawToChar(as.raw(b[seq.int(first,last)])))
  }
  if(name=='findc') {
    if(length(args)<2L || length(args)>4L) stop('arity')
    b<-ascii(args[[1]]);chars<-ascii(args[[2]]);if(length(chars)>64L) stop('set bound')
    control<-options(args[-seq_len(2L)],c('','I','K','IK','KI'))
    if(grepl('I',control$modifier,fixed=TRUE)) {b<-fold(b);chars<-fold(chars)}
    selected<-b %in% chars;if(grepl('K',control$modifier,fixed=TRUE)) selected<-!selected
    order<-positions(length(b),control$start);found<-order[selected[order]]
    return(if(length(found)) found[1L] else 0L)
  }
  if(name=='indexw') {
    if(length(args)<2L || length(args)>3L) stop('arity')
    b<-ascii(args[[1]]);word<-ascii(args[[2]])
    if(length(args)==3L && !identical(rawToChar(as.raw(ascii(args[[3]]))),' ')) stop('INDEXW delimiter')
    nonblank<-which(word!=32L)
    word<-if(length(nonblank)) word[seq.int(nonblank[1],tail(nonblank,1L))] else integer()
    if(!length(word)) return(if(all(b==32L)) 1L else 0L)
    return(word_match(b,word,32L,seq_len(length(b))))
  }
  if(name!='findw' || length(args)<3L || length(args)>5L) stop('arity')
  b<-ascii(args[[1]]);word<-ascii(args[[2]]);chars<-ascii(args[[3]])
  if(!length(word) || !length(chars) || length(chars)>64L || any((chars>=65L & chars<=90L) | (chars>=97L & chars<=122L))) stop('word or delimiter domain')
  control<-options(args[-seq_len(3L)],c('','I'))
  if(control$modifier=='I') {b<-fold(b);word<-fold(word)}
  word_match(b,word,chars,positions(length(b),control$start))
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
  required<-c('data located','set raw',"chars=findc(text,'aA')","words=findw(text,'ab',' ,')","indexed=indexc(text,'x','Z')","bounded=indexw(text,'ab')",'piece=substrn(text,position,take)','output',"put 'located'",'run')
  if(!identical(statements,required)) stop('original sequence')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
  if(!identical(names(input),c('text','position','take'))) stop('input schema')
  number<-function(x) if(!nzchar(x)) NA_real_ else as.numeric(x)
  rows<-lapply(seq_len(nrow(input)),function(i) list(store(input$text[i],12L),number(input$position[i]),number(input$take[i])))
  cat('STATEMENTS|',length(statements),'\n',sep='')
  for(row in rows) emit('raw',row)
  for(row in rows) {
    text<-row[[1]];values<-list(call_value('findc',list(text,'aA')),call_value('findw',list(text,'ab',' ,')),call_value('indexc',list(text,'x','Z')),call_value('indexw',list(text,'ab')),store(call_value('substrn',row),12L))
    emit('located',c(row,values))
  }
  for(row in rows) cat('LOG|',hex('located'),'\n',sep='')
} else stop('mode')
